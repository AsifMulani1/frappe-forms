# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# The single guest-facing write path. submit() validates every visible answer, grades quizzes,
# and inserts/updates the response (Collection or Linked) with ignore_permissions=True — we
# never grant Guest broad create perms. The _insert_*/_update_* helpers do the actual writes.

import base64
import binascii
import json

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, validate_email_address

from forms.api.grading import _grade
from forms.api.notifications import _maybe_notify_admin, _maybe_send_receipt
from forms.api.render import _accepting_status, _field_spec, _published_form, _session_email
from forms.api.uploads import _attach_file
from forms.api.validation import _coerce_and_validate, _visible_specs
from forms.compile import LAYOUT_TYPES, resolve_fieldname
from forms.config import ENC_IDENTITY_MAX_BYTES, SUBMIT_RATE_LIMIT, SUBMIT_RATE_WINDOW


def _validate_enc_identity(blob: str | None):
	"""Confirm a sealed identity envelope is present and well-formed before it's stored.

	The server can't read the ciphertext (only the creator's browser holds the private key), but it
	MUST reject a missing or malformed envelope: otherwise an encrypted response persists with no
	recoverable identity — undecryptable forever, and indistinguishable from a genuine one. We check
	the envelope shape sealIdentity() produces: {v:1, epk, iv, ct} with base64 parts.
	"""
	if not blob:
		frappe.throw("This form encrypts your identity, but none was received. Please retry.")
	if len(blob) > ENC_IDENTITY_MAX_BYTES:
		frappe.throw("Encrypted identity is too large.")
	try:
		env = json.loads(blob)
	except (ValueError, TypeError):
		frappe.throw("Encrypted identity is malformed.")
	if not isinstance(env, dict) or env.get("v") != 1:
		frappe.throw("Encrypted identity is malformed.")
	raw = {}
	for part in ("epk", "iv", "ct"):
		val = env.get(part)
		if not isinstance(val, str) or not val:
			frappe.throw("Encrypted identity is malformed.")
		try:
			raw[part] = base64.b64decode(val, validate=True)
		except (binascii.Error, ValueError):
			frappe.throw("Encrypted identity is malformed.")
	# Decoded lengths must match what the browser's openIdentity() can actually consume, or we'd
	# accept an envelope that is structurally impossible to decrypt: epk is an uncompressed P-256
	# public key (65 bytes, 0x04 prefix), iv is a 12-byte AES-GCM nonce, ct carries at least the
	# 16-byte GCM tag. Base64 validity alone lets wrong-length junk through.
	if len(raw["epk"]) != 65 or raw["epk"][0] != 0x04:
		frappe.throw("Encrypted identity is malformed.")
	if len(raw["iv"]) != 12 or len(raw["ct"]) < 16:
		frappe.throw("Encrypted identity is malformed.")


def _block_if_duplicate(form, respondent_email: str | None):
	"""Enforce 'one response per user' (when allow_multiple is off) for Collection forms.

	Identifies a repeat by record owner (signed-in) or captured email (guest). Pure anonymous
	guests with no email can't be deduped server-side — that case relies on login/email.
	"""
	if cint(form.allow_multiple) or form.storage_mode != "Collection":
		return
	dt = form.doctype_name
	if not dt or not frappe.db.exists("DocType", dt):
		return
	user = frappe.session.user
	if user and user != "Guest":
		if frappe.db.exists(dt, {"owner": user}):
			frappe.throw("You’ve already responded to this form.")
	elif respondent_email:
		if frappe.db.exists(dt, {"respondent_email": respondent_email}):
			frappe.throw("A response has already been submitted with this email address.")


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=SUBMIT_RATE_LIMIT, seconds=SUBMIT_RATE_WINDOW)
def submit(slug: str, data: str, hp: str | None = None, token: str | None = None,
		email: str | None = None, record: str | None = None, enc_identity: str | None = None):
	"""Validate + insert (or, with a valid edit token, update) a submission.

	Returns {name}, plus {token} when the form allows editing and this is a new record.
	"""
	if hp:
		# Honeypot tripped: a real user never fills this hidden field. Return a plausible success
		# (a fake record name) without writing anything, so a bot can't tell it was rejected.
		return {"name": frappe.generate_hash(length=12)}

	form = _published_form(slug)

	if isinstance(data, str):
		data = json.loads(data)
	if not isinstance(data, dict):
		frappe.throw("Invalid submission payload.")

	# Editing an existing response (valid token / record) is distinct from a new submission:
	# the open/close window, response limit, and one-per-user rule gate new responses only.
	allow_edit = cint(form.allow_edit)
	is_edit = bool((record and allow_edit and form.storage_mode == "Linked")
		or (token and allow_edit and form.storage_mode != "Linked"))

	# Capture the respondent's email when the form collects it (typed, or the logged-in user's).
	# On an encrypted form the email never reaches the server in the clear — the browser sealed it
	# into enc_identity — so we don't capture, validate, or store a plaintext address here.
	respondent_email = None
	encrypted = cint(form.encrypted)
	if cint(form.collect_email) and not encrypted:
		respondent_email = (email or "").strip() or _session_email()
		if not respondent_email:
			frappe.throw("Please provide your email address.")
		if not validate_email_address(respondent_email):
			frappe.throw("Please provide a valid email address.")

	# On an encrypted form the identity lives only in the sealed blob. Require it (and check its
	# shape) on a new response; on an edit, validate only a blob that's actually being re-sent, so a
	# metadata-only edit doesn't wipe the identity already on the row.
	if encrypted and (enc_identity or not is_edit):
		_validate_enc_identity(enc_identity)

	if not is_edit:
		accepting, closed_reason = _accepting_status(form)
		if not accepting:
			frappe.throw(closed_reason or "This form is not accepting responses.")
		# One-per-user dedup keys off the plaintext email or the record owner. Encrypted forms have
		# neither (the email is sealed, the owner is anonymised), so the rule can't be enforced.
		if not encrypted:
			_block_if_duplicate(form, respondent_email)

	# Display-only fields (section headers) carry no data; fields hidden by conditional logic are
	# dropped here so a hidden required field can't block the submit and hidden answers aren't stored.
	specs = {
		(f.fieldname or resolve_fieldname(f)): _field_spec(f)
		for f in form.fields
		if f.field_type not in LAYOUT_TYPES
	}
	specs = _visible_specs(form, specs, data)

	# Validate + coerce every visible field (by fieldname).
	clean = {}
	for fieldname, spec in specs.items():
		clean[fieldname] = _coerce_and_validate(spec, data.get(fieldname))

	score = max_score = None
	if cint(form.is_quiz):
		score, max_score = _grade(specs, clean)

	result = {}
	if form.storage_mode == "Linked":
		# Edit an existing target record (login + write permission), else insert a new one.
		if record and allow_edit:
			result["name"] = _update_linked(form, clean, specs, record)
		else:
			result["name"] = _insert_linked(form, clean, specs)
	elif token and allow_edit:
		result["name"] = _update_collection(form, clean, specs, token, respondent_email, enc_identity)
	else:
		new_token = frappe.generate_hash(length=24) if allow_edit else None
		result["name"] = _insert_collection(form, clean, specs, new_token, respondent_email, enc_identity)
		if new_token:
			result["token"] = new_token

	if score is not None:
		# Persist the graded score on the Collection record (system columns); always return it.
		if form.storage_mode == "Collection" and frappe.get_meta(form.doctype_name).get_field("score"):
			frappe.db.set_value(form.doctype_name, result["name"],
				{"score": score, "max_score": max_score}, update_modified=False)
		result["score"] = score
		result["max_score"] = max_score
		if cint(form.show_score):
			result["show_score"] = 1

	frappe.db.commit()
	_maybe_send_receipt(form, clean, specs, respondent_email)
	_maybe_notify_admin(form, clean, specs, result["name"], respondent_email)
	return result


def _apply_value(doc, fieldname: str, spec: dict, value):
	"""Set one answer onto a record, replacing child-table rows for table-backed types."""
	ft = spec["field_type"]
	if ft == "checkboxes":
		doc.set(fieldname, [])
		for opt in (value or []):
			doc.append(fieldname, {"value": opt})
	elif ft == "mc_grid":
		doc.set(fieldname, [])
		for row, col in (value or {}).items():
			doc.append(fieldname, {"row": row, "value": col})
	elif ft == "checkbox_grid":
		doc.set(fieldname, [])
		for row, cols in (value or {}).items():
			for col in cols:
				doc.append(fieldname, {"row": row, "value": col})
	else:
		doc.set(fieldname, value)


def _insert_collection(form, clean: dict, specs: dict, token: str | None = None,
		respondent_email: str | None = None, enc_identity: str | None = None) -> str:
	doc = frappe.new_doc(form.doctype_name)
	for fieldname, spec in specs.items():
		value = clean.get(fieldname)
		if value is None:
			continue
		_apply_value(doc, fieldname, spec, value)

	if doc.meta.get_field("workflow_state"):
		doc.workflow_state = "Pending"
	if token and doc.meta.get_field("edit_token"):
		doc.edit_token = token
	if respondent_email and doc.meta.get_field("respondent_email"):
		doc.respondent_email = respondent_email
	if cint(form.encrypted):
		# Store the sealed identity blob and keep no identifying trace on the row itself: skip the
		# version log (its owner would be the respondent) so it can't be undone below.
		if enc_identity and doc.meta.get_field("enc_identity"):
			doc.enc_identity = enc_identity
		doc.flags.ignore_version = True

	doc.insert(ignore_permissions=True)

	if cint(form.encrypted):
		# The row's owner/modified_by are set to the session user on insert — for a signed-in
		# respondent that unmasks them to anyone reading the DB. Neutralise both so identity lives
		# ONLY inside the ciphertext blob, decryptable by the creator alone.
		frappe.db.set_value(form.doctype_name, doc.name,
			{"owner": "Guest", "modified_by": "Guest"}, update_modified=False)

	# Own the files uploaded for this submission (they were created unattached).
	for fieldname, spec in specs.items():
		if spec["field_type"] == "file_upload" and clean.get(fieldname):
			_attach_file(clean[fieldname], doc.doctype, doc.name)

	return doc.name


def _update_collection(form, clean: dict, specs: dict, token: str,
		respondent_email: str | None = None, enc_identity: str | None = None) -> str:
	"""Re-save an existing submission addressed by its private edit token."""
	name = frappe.db.get_value(form.doctype_name, {"edit_token": token}, "name")
	if not name:
		frappe.throw("This response can no longer be edited.")
	doc = frappe.get_doc(form.doctype_name, name)
	for fieldname, spec in specs.items():
		_apply_value(doc, fieldname, spec, clean.get(fieldname))
	encrypted = cint(form.encrypted)
	if respondent_email and doc.meta.get_field("respondent_email"):
		doc.respondent_email = respondent_email
	if encrypted and enc_identity and doc.meta.get_field("enc_identity"):
		doc.enc_identity = enc_identity
	# ignore_version MUST travel through save(): _save() overwrites doc.flags.ignore_version with its
	# own parameter (defaulting to frappe.in_test), so a flag set here is silently dropped in
	# production — and the resulting Version record's owner/modified_by would unmask the respondent.
	save_kwargs = {"ignore_permissions": True}
	if encrypted:
		save_kwargs["ignore_version"] = True
	doc.save(**save_kwargs)

	if encrypted:
		# save() stamps modified_by with the session user — for a signed-in respondent that re-exposes
		# them on every edit. Re-neutralise owner/modified_by so identity lives only in the ciphertext.
		frappe.db.set_value(form.doctype_name, doc.name,
			{"owner": "Guest", "modified_by": "Guest"}, update_modified=False)

	for fieldname, spec in specs.items():
		if spec["field_type"] == "file_upload" and clean.get(fieldname):
			_attach_file(clean[fieldname], doc.doctype, doc.name)

	return doc.name


def _insert_linked(form, clean: dict, specs: dict) -> str:
	# When the form enforces target permissions, the submitter must be a real, authorised user;
	# otherwise we insert as the system (guest forms that feed a DocType without granting perms).
	apply_perms = cint(form.apply_doc_perms)
	if apply_perms:
		if frappe.session.user == "Guest":
			frappe.throw("Please sign in to submit this form.", frappe.PermissionError)
		if not frappe.has_permission(form.target_doctype, "create"):
			frappe.throw(
				f"You do not have permission to create {form.target_doctype} records.",
				frappe.PermissionError,
			)

	doc = frappe.new_doc(form.target_doctype)
	_apply_linked_values(doc, form, clean, frappe.get_meta(form.target_doctype))
	doc.insert(ignore_permissions=True)
	return doc.name


def _apply_linked_values(doc, form, clean: dict, target_meta):
	"""Set mapped answers onto a target-DocType record (insert or update)."""
	for f in form.fields:
		if not f.mapped_field or not target_meta.get_field(f.mapped_field):
			continue
		fieldname = f.fieldname or resolve_fieldname(f)
		value = clean.get(fieldname)
		if value is None:
			continue
		# Grids have no single-field representation in Linked mode - skip them.
		if isinstance(value, dict):
			continue
		# Linked mode never maps checkboxes onto a single docfield; join if it happens.
		if isinstance(value, list):
			value = ", ".join(value)
		doc.set(f.mapped_field, value)


def _update_linked(form, clean: dict, specs: dict, record: str) -> str:
	"""Update an existing target record the signed-in user is allowed to edit (Web Forms parity)."""
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in to edit this response.", frappe.PermissionError)
	if not frappe.has_permission(form.target_doctype, "write", doc=record):
		frappe.throw("You do not have permission to edit this record.", frappe.PermissionError)
	doc = frappe.get_doc(form.target_doctype, record)
	_apply_linked_values(doc, form, clean, frappe.get_meta(form.target_doctype))
	doc.save(ignore_permissions=True)
	return doc.name
