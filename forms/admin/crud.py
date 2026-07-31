# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Form CRUD backing the dashboard and builder: list/create/save/archive/delete/duplicate,
# publish + live preview, and the Linked-mode target field lookup.

import base64
import hashlib
import re

import frappe
from frappe.utils import cint

from forms.admin.access import _accessible_filter, _guard, _require, _shared_names
from forms.admin.serialize import _completion_rate, _form_dict, _response_count
from forms.compile import compile_preview as _compile_preview
from forms.compile import publish as _publish


@frappe.whitelist()
def list_forms(view: str = "all") -> list[dict]:
	"""Forms for a sidebar view, with LIVE response counts.

	view: all | published | draft | templates | archived | shared
	"""
	_guard()
	filters = {"archived": 0}
	if view == "published":
		filters["status"] = "Published"
	elif view == "draft":
		filters["status"] = "Draft"
	elif view == "templates":
		filters = {"is_template": 1}
	elif view == "archived":
		filters = {"archived": 1}
	elif view == "shared":
		names = _shared_names()
		if not names:
			return []
		filters = {"name": ("in", list(names)), "archived": 0}

	if view != "shared":
		_accessible_filter(filters)

	out = []
	for f in frappe.get_all(
		"FF Form",
		filters=filters,
		fields=["name", "title", "slug", "status", "storage_mode", "doctype_name",
			"target_doctype", "accent", "description", "cover_image", "category",
			"owner", "modified", "archived", "is_template", "embed_allowed_domains"],
		order_by="modified desc",
	):
		form = frappe.get_doc("FF Form", f.name)
		responses = _response_count(form)
		out.append({
			**f,
			"owner_fullname": frappe.get_cached_value("User", f.owner, "full_name") or f.owner,
			"responses": responses,
			"field_count": len(form.fields),
			"completion": _completion_rate(form, responses),
			# A short, live preview of the first few fields - powers the template gallery cards.
			"preview": [
				{"label": ff.label, "field_type": ff.field_type, "reqd": cint(ff.reqd)}
				for ff in form.fields[:5]
			],
		})
	return out


@frappe.whitelist()
def nav_counts() -> dict:
	"""Live counts for the sidebar nav badges."""
	_guard()
	return {
		"all": frappe.db.count("FF Form", _accessible_filter({"archived": 0})),
		"templates": frappe.db.count("FF Form", {"is_template": 1}),
		"archived": frappe.db.count("FF Form", _accessible_filter({"archived": 1})),
		"shared": len(_shared_names()),
	}


@frappe.whitelist()
def get_form(slug: str) -> dict:
	_guard()
	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.local.response["http_status_code"] = 404
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	_require(name, "read")
	return _form_dict(frappe.get_doc("FF Form", name))


@frappe.whitelist()
def create_form() -> dict:
	"""Create a Draft and return it (frontend routes to the builder)."""
	_guard()
	doc = frappe.new_doc("FF Form")
	doc.title = "Untitled form"
	doc.description = "Add a description to tell respondents what this form is for."
	doc.insert()
	return _form_dict(doc)


@frappe.whitelist()
def save_form(name: str, data: str) -> dict:
	"""Persist builder edits. Frozen fieldnames are never overwritten by the client."""
	_guard()
	_require(name, "write")
	payload = frappe.parse_json(data)
	# Reject a redirect target that isn't an http(s) URL or a site-relative path (open-redirect guard).
	redirect = (payload.get("redirect_url") or "").strip()
	if redirect and not re.match(r"^(https?://|/)", redirect):
		frappe.throw("Redirect URL must start with http://, https://, or /.")
	doc = frappe.get_doc("FF Form", name)

	for key in ("title", "description", "accent", "cover_image", "category", "storage_mode",
			"target_doctype", "login_required", "allow_multiple", "collect_email",
			"apply_doc_perms", "shuffle_questions", "show_progress", "email_receipt", "allow_edit",
			"show_my_submissions", "allow_delete", "notify_on_response", "notify_email",
			"opens_on", "closes_on", "response_limit", "is_quiz", "show_score",
			"thank_you_message", "redirect_url", "embed_allowed_domains", "is_template"):
		if key in payload:
			doc.set(key, payload[key])

	if "fields" in payload:
		existing = {f.name: f for f in doc.fields}
		doc.set("fields", [])
		for row in payload["fields"]:
			frozen = existing.get(row.get("name"))
			doc.append("fields", {
				"label": row.get("label"),
				"field_type": row.get("field_type"),
				"reqd": cint(row.get("reqd")),
				"help_text": row.get("help_text"),
				"options": row.get("options"),
				"grid_rows": row.get("grid_rows"),
				"mapped_field": row.get("mapped_field"),
				"has_other": cint(row.get("has_other")),
				"shuffle_options": cint(row.get("shuffle_options")),
				"min_value": row.get("min_value"),
				"max_value": row.get("max_value"),
				"max_length": cint(row.get("max_length")),
				"validation_pattern": row.get("validation_pattern"),
				"error_message": row.get("error_message"),
				"scale_min": cint(row.get("scale_min")) or 1,
				"scale_max": cint(row.get("scale_max")) or 5,
				"min_label": row.get("min_label"),
				"max_label": row.get("max_label"),
				"condition_field": row.get("condition_field"),
				"condition_operator": row.get("condition_operator") or "equals",
				"condition_value": row.get("condition_value"),
				"points": cint(row.get("points")),
				"correct_answer": row.get("correct_answer"),
				# Keep the stable field_key (and frozen fieldname); otherwise let the controller/publish derive them.
				"field_key": (frozen.field_key if frozen else row.get("field_key")) or "",
				"fieldname": (frozen.fieldname if (frozen and frozen.fieldname) else row.get("fieldname")),
			})

	doc.save()
	frappe.db.commit()
	return _form_dict(doc)


@frappe.whitelist()
def set_archived(name: str, archived: int = 1) -> dict:
	_guard()
	_require(name, "write")
	frappe.db.set_value("FF Form", name, "archived", cint(archived))
	frappe.db.commit()
	return {"name": name, "archived": cint(archived)}


@frappe.whitelist()
def delete_form(name: str) -> dict:
	"""Permanently delete a form. For a Collection form this also drops its generated DocType,
	every submitted record, and any child link tables. Linked forms leave their target untouched."""
	_guard()
	_require(name, "delete")
	form = frappe.get_doc("FF Form", name)
	dt = form.doctype_name
	frappe.delete_doc("FF Form", name, force=True, ignore_permissions=True)
	if form.storage_mode == "Collection" and dt and frappe.db.exists("DocType", dt):
		# Drop generated records, child link tables, option masters, then the doctype.
		meta = frappe.get_meta(dt)
		child_doctypes = [f.options for f in meta.fields if f.fieldtype == "Table MultiSelect"]
		frappe.db.delete(dt)
		frappe.delete_doc("DocType", dt, force=True, ignore_permissions=True)
		for cd in child_doctypes:
			if cd and frappe.db.exists("DocType", cd):
				frappe.delete_doc("DocType", cd, force=True, ignore_permissions=True)
			master = cd.replace(" Item", " Option") if cd else None
			if master and frappe.db.exists("DocType", master):
				frappe.delete_doc("DocType", master, force=True, ignore_permissions=True)
	frappe.db.commit()
	return {"name": name, "deleted": True}


@frappe.whitelist()
def delete_forms(names: str) -> dict:
	"""Bulk delete. Each form is removed with the same cleanup as a single delete."""
	_guard()
	names = frappe.parse_json(names) if isinstance(names, str) else names
	for n in names:
		delete_form(n)
	return {"deleted": len(names)}


@frappe.whitelist()
def set_archived_bulk(names: str, archived: int = 1) -> dict:
	"""Bulk archive/restore the given forms."""
	_guard()
	names = frappe.parse_json(names) if isinstance(names, str) else names
	for n in names:
		_require(n, "write")
		frappe.db.set_value("FF Form", n, "archived", cint(archived))
	frappe.db.commit()
	return {"updated": len(names), "archived": cint(archived)}


# Form-level settings copied verbatim on duplicate. status/slug/doctype_name/sheet_name/views and
# is_template are intentionally NOT copied — a duplicate is a fresh, non-template Draft of its own.
_DUPLICATE_META = (
	"description", "accent", "cover_image", "category", "storage_mode", "target_doctype",
	"apply_doc_perms", "thank_you_message", "redirect_url", "collect_email", "allow_multiple",
	"login_required", "shuffle_questions", "show_progress", "email_receipt", "allow_edit",
	"show_my_submissions", "allow_delete", "notify_on_response", "notify_email",
	"opens_on", "closes_on", "response_limit", "is_quiz", "show_score",
)
_DUPLICATE_FIELD_ATTRS = (
	"label", "field_type", "reqd", "help_text", "options", "grid_rows", "mapped_field",
	"has_other", "shuffle_options", "min_value", "max_value", "max_length",
	"validation_pattern", "error_message", "scale_min", "scale_max", "min_label", "max_label",
	"condition_operator", "condition_value", "points", "correct_answer",
)


@frappe.whitelist()
def duplicate_form(name: str) -> dict:
	"""Copy a form (used by 'Use template' and plain duplicate). Always a fresh Draft.

	Carries every form-level setting and field attribute. Fieldnames are NOT copied (they
	re-derive/freeze on the new form's own publish). field_keys are regenerated, and conditional-logic
	references are remapped onto the new keys so skip logic keeps pointing at the copied field.
	"""
	_guard()
	_require(name, "read")
	src = frappe.get_doc("FF Form", name)
	doc = frappe.new_doc("FF Form")
	doc.title = f"{src.title} (copy)"
	for key in _DUPLICATE_META:
		doc.set(key, src.get(key))

	# Fresh keys + a map from the source keys, so a field's condition_field points at the COPY of
	# its controlling field rather than the original form's field.
	key_map = {f.field_key: frappe.generate_hash(length=10) for f in src.fields if f.field_key}
	for f in src.fields:
		row = {attr: f.get(attr) for attr in _DUPLICATE_FIELD_ATTRS}
		row["field_key"] = key_map.get(f.field_key) or frappe.generate_hash(length=10)
		row["condition_field"] = key_map.get(f.condition_field, "")
		doc.append("fields", row)
	doc.insert()
	frappe.db.commit()
	return _form_dict(doc)


def _fingerprint(public_key_b64: str) -> str:
	"""Server-side twin of crypto.js fingerprint(): SHA-256 of the raw public key, first 8 bytes as
	colon-separated hex. Used to verify the client-supplied fingerprint really matches the key."""
	try:
		raw = base64.b64decode(public_key_b64, validate=True)
	except (ValueError, TypeError):
		frappe.throw("Invalid public key.")
	return ":".join(f"{b:02x}" for b in hashlib.sha256(raw).digest()[:8])


@frappe.whitelist()
def setup_encryption(name: str, public_key: str, wrapped_key: str, kdf_salt: str,
		key_iv: str, fingerprint: str) -> dict:
	"""Arm identity encryption for a form with a keypair generated in the creator's browser.

	Only the form's creator may do this: the whole promise is that even other Forms Managers and
	System Managers can't unmask respondents, so the private key (wrapped under the creator's
	passphrase) is bound to the owner.
	"""
	_guard()
	_require(name, "write")
	form = frappe.get_doc("FF Form", name)
	if form.owner != frappe.session.user:
		frappe.throw("Only the form's creator can enable encryption.", frappe.PermissionError)
	if form.status == "Published":
		# Arming after publish would flip form.encrypted without adding the enc_identity column
		# (the schema is fixed at publish), so every sealed identity would be silently dropped on
		# submit. Encryption must be enabled before publishing, and is frozen once it is.
		frappe.throw("Encryption must be enabled before the form is published.")
	if form.storage_mode != "Collection":
		# Linked forms write straight into a target DocType (owner = the real respondent) and have no
		# enc_identity column to hold the sealed blob — encryption there would store identity in clear.
		frappe.throw("Encryption is only available for Collection forms.")
	if not all([public_key, wrapped_key, kdf_salt, key_iv, fingerprint]):
		frappe.throw("Incomplete key material.")
	# The fingerprint the creator will eyeball is only meaningful if it actually derives from the
	# stored public key. Recompute it (SHA-256(pubkey)[:8], matching crypto.js fingerprint()) and
	# reject a mismatch, so a buggy/tampered client can't store an inconsistent pair.
	if fingerprint != _fingerprint(public_key):
		frappe.throw("Key fingerprint doesn't match the public key.")
	form.encrypted = 1
	form.enc_public_key = public_key
	form.enc_wrapped_key = wrapped_key
	form.enc_kdf_salt = kdf_salt
	form.enc_key_iv = key_iv
	form.enc_fingerprint = fingerprint
	form.save()
	frappe.db.commit()
	return {"encrypted": 1, "fingerprint": fingerprint}


@frappe.whitelist()
def disable_encryption(name: str) -> dict:
	"""Turn encryption off (creator only). Blocked once the form is published: responses only exist
	for published forms, their identities are already ciphertext, and un-arming can't decrypt them."""
	_guard()
	_require(name, "write")
	form = frappe.get_doc("FF Form", name)
	if form.owner != frappe.session.user:
		frappe.throw("Only the form's creator can change encryption.", frappe.PermissionError)
	if form.status == "Published":
		frappe.throw("Encryption is frozen once a form is published.")
	form.encrypted = 0
	form.enc_public_key = form.enc_wrapped_key = form.enc_kdf_salt = None
	form.enc_key_iv = form.enc_fingerprint = None
	form.save()
	frappe.db.commit()
	return {"encrypted": 0}


@frappe.whitelist()
def get_encryption_key(slug: str) -> dict:
	"""Hand the creator their wrapped private key so their browser can unlock responses.

	Owner-only: other managers (even System Managers) are refused at this endpoint. Note the wrapped
	key is by-design safe at rest — it's sealed under the creator's passphrase (PBKDF2 210k), which
	never leaves their browser, so the scheme holds even against a DB/backup reader who obtains it.
	This endpoint binding is defense-in-depth, not the security boundary; the passphrase is."""
	_guard()
	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	_require(name, "read")
	form = frappe.get_doc("FF Form", name)
	if form.owner != frappe.session.user:
		frappe.throw("Only the form's creator can unlock responses.", frappe.PermissionError)
	if not form.enc_wrapped_key:
		frappe.throw("This form isn't encrypted.")
	return {
		"public_key": form.enc_public_key,
		"wrapped_key": form.enc_wrapped_key,
		"kdf_salt": form.enc_kdf_salt,
		"key_iv": form.enc_key_iv,
		"fingerprint": form.enc_fingerprint,
	}


@frappe.whitelist()
def publish_form(name: str) -> dict:
	_guard()
	_require(name, "write")
	result = _publish(name)
	return result


@frappe.whitelist()
def preview(slug: str) -> dict:
	_guard()
	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	_require(name, "read")
	return _compile_preview(name)


@frappe.whitelist()
def preview_form(slug: str) -> dict:
	"""Respondent-view render spec for the builder's live preview - works on Drafts too.
	Auth-only (Forms Managers); guests never reach unpublished forms."""
	_guard()
	from forms.api import public_render_spec

	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	_require(name, "read")
	return public_render_spec(frappe.get_doc("FF Form", name))


@frappe.whitelist()
def target_doctype_fields(doctype: str) -> list[dict]:
	"""Plain mappable fields on a target DocType (Linked mode)."""
	_guard()
	if not doctype or not frappe.db.exists("DocType", doctype):
		return []
	meta = frappe.get_meta(doctype)
	allowed = ("Data", "Small Text", "Text", "Select", "Int", "Float", "Date", "Phone")
	return [
		{"fieldname": f.fieldname, "label": f.label or f.fieldname, "fieldtype": f.fieldtype}
		for f in meta.fields
		if f.fieldtype in allowed and not f.hidden and f.fieldname
	]
