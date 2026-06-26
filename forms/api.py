# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Guest-facing endpoints. Submissions are governed records: the public form posts through a
# single whitelisted, rate-limited, honeypot-checked endpoint that validates every field
# server-side and inserts with ignore_permissions=True (we never grant Guest broad perms).

import json
import re

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, validate_email_address

from forms.compile import GRID_TYPES, LAYOUT_TYPES, resolve_fieldname

WORKFLOW_STATES = ("Pending", "Confirmed", "Waitlist")


def _published_form(slug: str):
	name = frappe.db.get_value("FF Form", {"slug": slug, "status": "Published"}, "name")
	if not name:
		frappe.local.response["http_status_code"] = 404
		frappe.throw("Form not found or not published.", frappe.DoesNotExistError)
	return frappe.get_doc("FF Form", name)


def _field_spec(f) -> dict:
	return {
		"fieldname": resolve_fieldname(f),
		"label": f.label,
		"field_type": f.field_type,
		"help_text": f.help_text,
		"reqd": cint(f.reqd),
		"options": [o.strip() for o in (f.options or "").splitlines() if o.strip()],
		"grid_rows": [r.strip() for r in (f.grid_rows or "").splitlines() if r.strip()],
		"mapped_field": f.mapped_field,
		"has_other": cint(f.has_other),
		"shuffle_options": cint(f.shuffle_options),
		"min_value": f.min_value,
		"max_value": f.max_value,
		"max_length": cint(f.max_length),
		"validation_pattern": f.validation_pattern,
		"error_message": f.error_message,
		"scale_min": cint(f.scale_min) or 1,
		"scale_max": cint(f.scale_max) or 5,
		"min_label": f.min_label,
		"max_label": f.max_label,
	}


def _to_number(value):
	"""Parse an optional numeric bound (stored as Data). Blank/unparseable -> None."""
	if value is None or str(value).strip() == "":
		return None
	try:
		return flt(value)
	except (ValueError, TypeError):
		return None


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=120, seconds=60 * 60)
def track_view(slug: str) -> dict:
	"""Count one public open of a published form (drives the completion funnel).

	Atomic counter increment — no row per view, so it stays cheap at any volume.
	"""
	name = frappe.db.get_value("FF Form", {"slug": slug, "status": "Published"}, "name")
	if name:
		frappe.db.sql(
			"UPDATE `tabFF Form` SET views = COALESCE(views, 0) + 1 WHERE name = %s", name
		)
		frappe.db.commit()
	return {"ok": True}


@frappe.whitelist(allow_guest=True)
def session_info() -> dict:
	"""Guest-safe session probe for the SPA. Never errors: returns user=None for guests."""
	user = frappe.session.user
	if not user or user == "Guest":
		return {"user": None, "full_name": None}
	return {"user": user, "full_name": frappe.db.get_value("User", user, "full_name") or user}


def inject_csrf_token(context):
	"""update_website_context hook: ride the CSRF token along on the SPA's boot payload.

	frappe-ui's frappeRequest only sends X-Frappe-CSRF-Token when window.csrf_token is set, and
	the website boot omits it. Guests skip CSRF, but once a user logs in Frappe enforces it -
	without the token every authenticated POST (e.g. session_info) is rejected 400 and the SPA
	renders blank. The website layer has already built context.boot by the time this hook runs,
	so we just append the token; the page template emits it as window.csrf_token.
	"""
	if frappe.session.user and frappe.session.user != "Guest" and isinstance(context.get("boot"), dict):
		context["boot"]["csrf_token"] = frappe.sessions.get_csrf_token()


def public_render_spec(form) -> dict:
	"""The respondent-view render spec for a form. Shared by the public (published-only)
	endpoint and the builder's preview, which renders Drafts too."""
	return {
		"slug": form.slug,
		"title": form.title,
		"description": form.description,
		"accent": form.accent or "blue",
		"cover_image": form.cover_image,
		"collect_email": cint(form.collect_email),
		"user_email": _session_email(),
		"storage_mode": form.storage_mode,
		"allow_multiple": cint(form.allow_multiple),
		"thank_you_message": form.thank_you_message,
		"redirect_url": form.redirect_url,
		"shuffle_questions": cint(form.shuffle_questions),
		"show_progress": cint(form.show_progress),
		"allow_edit": cint(form.allow_edit),
		"show_my_submissions": cint(form.show_my_submissions),
		"allow_delete": cint(form.allow_delete),
		"fields": [_field_spec(f) for f in form.fields],
	}


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=600, seconds=60 * 60)
def get_public_form(slug: str) -> dict:
	"""Render spec for a published form. 404 for drafts / unknown slugs."""
	return public_render_spec(_published_form(slug))


def _coerce_and_validate(spec: dict, raw):
	"""Validate one answer server-side and coerce it to a storable value."""
	ft = spec["field_type"]
	label = spec["label"]
	required = spec["reqd"]

	empty = raw is None or raw == "" or (isinstance(raw, list) and not raw)
	if empty:
		if required:
			frappe.throw(f"'{label}' is required.")
		return None

	if ft == "email":
		if not validate_email_address(raw):
			frappe.throw(f"'{label}' must be a valid email address.")
		return raw
	if ft == "number":
		try:
			val = int(raw)
		except (ValueError, TypeError):
			frappe.throw(f"'{label}' must be a whole number.")
		lo, hi = _to_number(spec.get("min_value")), _to_number(spec.get("max_value"))
		if lo is not None and val < lo:
			frappe.throw(spec.get("error_message") or f"'{label}' must be at least {int(lo)}.")
		if hi is not None and val > hi:
			frappe.throw(spec.get("error_message") or f"'{label}' must be at most {int(hi)}.")
		return val
	if ft == "linear_scale":
		try:
			val = int(raw)
		except (ValueError, TypeError):
			frappe.throw(f"'{label}' must be a number.")
		lo, hi = spec.get("scale_min") or 1, spec.get("scale_max") or 5
		if val < lo or val > hi:
			frappe.throw(f"'{label}' must be between {lo} and {hi}.")
		return val
	if ft in ("single_choice", "dropdown"):
		# With an "Other" write-in, any non-empty string is allowed; otherwise enforce membership.
		if not spec.get("has_other") and spec["options"] and raw not in spec["options"]:
			frappe.throw(f"'{raw}' is not an allowed option for '{label}'.")
		return raw
	if ft == "checkboxes":
		values = raw if isinstance(raw, list) else [raw]
		for v in values:
			if spec["options"] and v not in spec["options"]:
				frappe.throw(f"'{v}' is not an allowed option for '{label}'.")
		return values
	if ft in GRID_TYPES:
		if not isinstance(raw, dict):
			frappe.throw(f"'{label}' has an invalid answer.")
		cols, rows = spec["options"], spec.get("grid_rows") or []
		cleaned = {}
		for r, v in raw.items():
			if rows and r not in rows:
				continue  # ignore answers for rows that no longer exist
			if ft == "mc_grid":
				if v in ("", None):
					continue
				if cols and v not in cols:
					frappe.throw(f"'{v}' is not a column for '{label}'.")
				cleaned[r] = v
			else:
				vals = [x for x in (v if isinstance(v, list) else [v]) if x not in ("", None)]
				for x in vals:
					if cols and x not in cols:
						frappe.throw(f"'{x}' is not a column for '{label}'.")
				if vals:
					cleaned[r] = vals
		if required and not cleaned:
			frappe.throw(f"'{label}' is required.")
		return cleaned or None
	if ft == "rating":
		# Frappe Rating stores a fraction of the max (5 stars). Clamp to 1..5.
		n = max(1, min(5, cint(raw)))
		return flt(n) / 5.0
	if ft == "yes_no":
		return 1 if str(raw).strip().lower() in ("1", "yes", "true", "on") else 0
	if ft == "phone":
		if not re.fullmatch(r"[+0-9 ()\-]{3,}", str(raw).strip()):
			frappe.throw(f"'{label}' must be a valid phone number.")
		return str(raw).strip()
	if ft == "time":
		m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?", str(raw).strip())
		if not m:
			frappe.throw(f"'{label}' must be a valid time.")
		return f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3) or '00'}"
	if ft == "file_upload":
		# Value is a Frappe file path returned by upload_submission_file - never raw content.
		if not (isinstance(raw, str) and re.match(r"^/(private/)?files/", raw)):
			frappe.throw(f"'{label}' must be an uploaded file.")
		return raw
	if ft == "signature":
		# Frappe Signature stores a base64 PNG data URL. Cap size to keep records sane.
		if not (isinstance(raw, str) and raw.startswith("data:image/")):
			frappe.throw(f"'{label}' must be a signature.")
		if len(raw) > 500_000:
			frappe.throw(f"'{label}' signature is too large.")
		return raw
	if ft in ("short_answer", "paragraph", "address"):
		text = str(raw)
		max_len = spec.get("max_length")
		if max_len and len(text) > max_len:
			frappe.throw(spec.get("error_message") or f"'{label}' must be at most {max_len} characters.")
		pattern = (spec.get("validation_pattern") or "").strip()
		if pattern:
			try:
				ok = re.fullmatch(pattern, text) is not None
			except re.error:
				ok = True  # a malformed pattern must never block a real answer
			if not ok:
				frappe.throw(spec.get("error_message") or f"'{label}' is not in the expected format.")
		return raw
	# date
	return raw


ALLOWED_UPLOAD_EXT = {"png", "jpg", "jpeg", "gif", "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=30, seconds=60 * 60)
def upload_submission_file(slug: str, fieldname: str):
	"""Guest-safe upload for a published form's file_upload field. Saves a PRIVATE File (validated
	for size + extension) and returns its url; the file is linked to the record on submit. We never
	use Frappe's broad upload_file for guests - this endpoint only accepts files for a real field."""
	form = _published_form(slug)
	field = next((f for f in form.fields if (f.fieldname or resolve_fieldname(f)) == fieldname), None)
	if not field or field.field_type != "file_upload":
		frappe.throw("Unknown upload field.")

	files = getattr(frappe.request, "files", None)
	uploaded = files.get("file") if files else None
	if not uploaded:
		frappe.throw("No file provided.")

	content = uploaded.stream.read()
	if not content:
		frappe.throw("Empty file.")
	if len(content) > MAX_UPLOAD_BYTES:
		frappe.throw("File is too large (max 10 MB).")

	filename = uploaded.filename or "upload"
	ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
	if ext not in ALLOWED_UPLOAD_EXT:
		frappe.throw(f"'{ext or filename}' files are not allowed.")

	# Tie the upload to its form so an unsubmitted file is identifiable (and reapable). On submit,
	# _attach_file re-points it to the actual submission record; anything still attached to "FF Form"
	# after a grace period was never submitted and gets cleaned up (see cleanup_orphan_uploads).
	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": filename,
		"content": content,
		"is_private": 1,
		"attached_to_doctype": "FF Form",
		"attached_to_name": form.name,
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"file_url": file_doc.file_url, "file_name": file_doc.file_name}


def cleanup_orphan_uploads():
	"""Scheduled: delete private guest uploads that were never tied to a submission.

	upload_submission_file parks files on their FF Form; a real submission re-points them to the
	response record. Files still parked on "FF Form" after 2h are abandoned uploads — reap them so
	guest uploads can't accumulate unbounded private-file storage."""
	stale = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "FF Form",
			"is_private": 1,
			"creation": ("<", frappe.utils.add_to_date(None, hours=-2)),
		},
		pluck="name",
		limit=500,
	)
	for name in stale:
		try:
			frappe.delete_doc("File", name, ignore_permissions=True, delete_permanently=True)
		except Exception:
			frappe.log_error(title="Forms orphan-upload cleanup failed")
	if stale:
		frappe.db.commit()


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=20, seconds=60 * 60)
def submit(slug: str, data: str, hp: str | None = None, token: str | None = None,
		email: str | None = None, record: str | None = None):
	"""Validate + insert (or, with a valid edit token, update) a submission.

	Returns {name}, plus {token} when the form allows editing and this is a new record.
	"""
	if hp:
		# Honeypot tripped - pretend success without writing anything.
		frappe.throw("Submission rejected.")

	form = _published_form(slug)

	if isinstance(data, str):
		data = json.loads(data)
	if not isinstance(data, dict):
		frappe.throw("Invalid submission payload.")

	# Display-only fields (section headers) carry no data and are never validated/stored.
	specs = {
		(f.fieldname or resolve_fieldname(f)): _field_spec(f)
		for f in form.fields
		if f.field_type not in LAYOUT_TYPES
	}

	# Validate + coerce every defined field (by fieldname).
	clean = {}
	for fieldname, spec in specs.items():
		clean[fieldname] = _coerce_and_validate(spec, data.get(fieldname))

	# Capture the respondent's email when the form collects it (typed, or the logged-in user's).
	respondent_email = None
	if cint(form.collect_email):
		respondent_email = (email or "").strip() or _session_email()
		if not respondent_email:
			frappe.throw("Please provide your email address.")
		if not validate_email_address(respondent_email):
			frappe.throw("Please provide a valid email address.")

	result = {}
	if form.storage_mode == "Linked":
		# Edit an existing target record (login + write permission), else insert a new one.
		if record and cint(form.allow_edit):
			result["name"] = _update_linked(form, clean, specs, record)
		else:
			result["name"] = _insert_linked(form, clean, specs)
	elif token and cint(form.allow_edit):
		result["name"] = _update_collection(form, clean, specs, token, respondent_email)
	else:
		new_token = frappe.generate_hash(length=24) if cint(form.allow_edit) else None
		result["name"] = _insert_collection(form, clean, specs, new_token, respondent_email)
		if new_token:
			result["token"] = new_token

	frappe.db.commit()
	_maybe_send_receipt(form, clean, specs, respondent_email)
	return result


def _session_email() -> str | None:
	"""Email of the logged-in user, or None for guests."""
	user = frappe.session.user
	if user and user != "Guest":
		return frappe.db.get_value("User", user, "email") or user
	return None


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
		respondent_email: str | None = None) -> str:
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

	doc.insert(ignore_permissions=True)

	# Own the files uploaded for this submission (they were created unattached).
	for fieldname, spec in specs.items():
		if spec["field_type"] == "file_upload" and clean.get(fieldname):
			_attach_file(clean[fieldname], doc.doctype, doc.name)

	return doc.name


def _update_collection(form, clean: dict, specs: dict, token: str,
		respondent_email: str | None = None) -> str:
	"""Re-save an existing submission addressed by its private edit token."""
	name = frappe.db.get_value(form.doctype_name, {"edit_token": token}, "name")
	if not name:
		frappe.throw("This response can no longer be edited.")
	doc = frappe.get_doc(form.doctype_name, name)
	for fieldname, spec in specs.items():
		_apply_value(doc, fieldname, spec, clean.get(fieldname))
	if respondent_email and doc.meta.get_field("respondent_email"):
		doc.respondent_email = respondent_email
	doc.save(ignore_permissions=True)

	for fieldname, spec in specs.items():
		if spec["field_type"] == "file_upload" and clean.get(fieldname):
			_attach_file(clean[fieldname], doc.doctype, doc.name)

	return doc.name


def _receipt_recipient(specs: dict, clean: dict, captured: str | None) -> str | None:
	"""Recipient for a receipt: the captured email, then any email answer, then the session user."""
	if captured:
		return captured
	for fieldname, spec in specs.items():
		if spec["field_type"] == "email" and clean.get(fieldname):
			return clean[fieldname]
	return _session_email()


def _format_answer(value) -> str:
	if isinstance(value, dict):
		return "; ".join(f"{r}: {', '.join(v) if isinstance(v, list) else v}" for r, v in value.items())
	if isinstance(value, list):
		return ", ".join(str(v) for v in value)
	return str(value)


def _maybe_send_receipt(form, clean: dict, specs: dict, captured_email: str | None = None):
	"""Email the respondent a copy of their answers (best-effort; never blocks submission)."""
	if not cint(form.email_receipt):
		return
	recipient = _receipt_recipient(specs, clean, captured_email)
	if not recipient:
		return
	rows = "".join(
		f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>{frappe.utils.escape_html(spec['label'])}</td>"
		f"<td style='padding:4px 0'>{frappe.utils.escape_html(_format_answer(clean[fn]))}</td></tr>"
		for fn, spec in specs.items()
		if clean.get(fn) is not None
	)
	message = (
		f"<p>Thanks for your response to <b>{frappe.utils.escape_html(form.title)}</b>. "
		f"Here's a copy for your records:</p><table>{rows}</table>"
	)
	try:
		# Enqueued (not now=True): a slow/down mail server must never block or fail the submission.
		frappe.sendmail(recipients=[recipient], subject=f"Your response to {form.title}",
			message=message)
	except Exception:
		frappe.log_error(title="Forms receipt email failed")


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=60, seconds=60 * 60)
def get_submission(slug: str, token: str) -> dict:
	"""Load a prior submission's answers for editing, addressed by its private edit token."""
	form = _published_form(slug)
	if not cint(form.allow_edit) or form.storage_mode == "Linked":
		frappe.throw("This form does not allow editing responses.")
	name = frappe.db.get_value(form.doctype_name, {"edit_token": token}, "name")
	if not name:
		frappe.local.response["http_status_code"] = 404
		frappe.throw("Response not found.", frappe.DoesNotExistError)
	doc = frappe.get_doc(form.doctype_name, name)

	answers = {}
	for f in form.fields:
		if f.field_type in LAYOUT_TYPES:
			continue
		fn = f.fieldname or resolve_fieldname(f)
		ft = f.field_type
		if ft == "checkboxes":
			answers[fn] = [r.value for r in doc.get(fn) or []]
		elif ft == "mc_grid":
			answers[fn] = {r.row: r.value for r in doc.get(fn) or []}
		elif ft == "checkbox_grid":
			grid = {}
			for r in doc.get(fn) or []:
				grid.setdefault(r.row, []).append(r.value)
			answers[fn] = grid
		elif ft == "rating":
			answers[fn] = round((doc.get(fn) or 0) * 5)
		else:
			answers[fn] = doc.get(fn)
	return {"name": name, "answers": answers, "respondent_email": doc.get("respondent_email")}


@frappe.whitelist()
def get_linked_record(slug: str, name: str) -> dict:
	"""Load a target record's mapped values for editing (Linked mode; login + write permission)."""
	form = _published_form(slug)
	if form.storage_mode != "Linked":
		frappe.throw("This form is not linked to an existing DocType.")
	if not cint(form.allow_edit):
		frappe.throw("This form does not allow editing responses.")
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in to edit this response.", frappe.PermissionError)
	if not frappe.has_permission(form.target_doctype, "write", doc=name):
		frappe.throw("You do not have permission to edit this record.", frappe.PermissionError)

	doc = frappe.get_doc(form.target_doctype, name)
	answers = {}
	for f in form.fields:
		if not f.mapped_field:
			continue
		fn = f.fieldname or resolve_fieldname(f)
		val = doc.get(f.mapped_field)
		# Checkboxes were stored as a joined string on insert; split back for the UI.
		if f.field_type == "checkboxes" and isinstance(val, str) and val:
			val = [v.strip() for v in val.split(",") if v.strip()]
		answers[fn] = val
	return {"name": name, "answers": answers}


def _submission_storage(form) -> str | None:
	"""The DocType a form's submissions live in (target for Linked, generated for Collection)."""
	return form.target_doctype if form.storage_mode == "Linked" else form.doctype_name


def _row_label(form, dt: str, name: str) -> str:
	"""A human label for a submission row in the 'my submissions' list."""
	if form.storage_mode == "Linked":
		title_field = frappe.get_meta(dt).title_field
		if title_field:
			return frappe.db.get_value(dt, name, title_field) or name
		return name
	# Collection: first text-ish answer makes a recognisable label.
	for f in form.fields:
		if f.field_type in ("short_answer", "email", "single_choice", "dropdown"):
			val = frappe.db.get_value(dt, name, resolve_fieldname(f))
			if val:
				return val
	return name


@frappe.whitelist()
def list_my_submissions(slug: str) -> dict:
	"""Signed-in respondent's own past submissions (records they own)."""
	form = _published_form(slug)
	if not cint(form.show_my_submissions):
		frappe.throw("This form does not list submissions.")
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in to see your submissions.", frappe.PermissionError)
	dt = _submission_storage(form)
	if not dt or not frappe.db.exists("DocType", dt):
		return {"rows": [], "can_edit": 0, "can_delete": 0}

	has_token = form.storage_mode != "Linked" and cint(form.allow_edit)
	fields = ["name", "creation"] + (["edit_token"] if has_token else [])
	records = frappe.get_all(dt, filters={"owner": frappe.session.user}, fields=fields,
		order_by="creation desc", limit=50)

	rows = []
	for r in records:
		if form.storage_mode == "Linked":
			edit_param = f"name={frappe.utils.quote(r.name)}" if cint(form.allow_edit) else None
		else:
			edit_param = f"edit={r.edit_token}" if (has_token and r.get("edit_token")) else None
		rows.append({"name": r.name, "creation": str(r.creation),
			"label": _row_label(form, dt, r.name), "edit_param": edit_param})
	return {"rows": rows, "can_edit": cint(form.allow_edit), "can_delete": cint(form.allow_delete)}


@frappe.whitelist()
def delete_my_submission(slug: str, name: str) -> dict:
	"""Delete a submission the signed-in respondent owns (when the form allows it)."""
	form = _published_form(slug)
	if not cint(form.allow_delete):
		frappe.throw("This form does not allow deleting responses.")
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in to delete your submission.", frappe.PermissionError)
	dt = _submission_storage(form)
	owner = frappe.db.get_value(dt, name, "owner")
	if owner != frappe.session.user and not frappe.has_permission(dt, "delete", doc=name):
		frappe.throw("You can only delete your own submissions.", frappe.PermissionError)
	frappe.delete_doc(dt, name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name}


def _attach_file(file_url: str, dt: str, dn: str):
	"""Link an already-uploaded File to the submission record it belongs to."""
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if name:
		frappe.db.set_value("File", name, {"attached_to_doctype": dt, "attached_to_name": dn})


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
