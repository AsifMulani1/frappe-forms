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

from forms.compile import LAYOUT_TYPES, resolve_fieldname

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
		"mapped_field": f.mapped_field,
	}


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


@frappe.whitelist(allow_guest=True)
def get_public_form(slug: str) -> dict:
	"""Render spec for a published form. 404 for drafts / unknown slugs."""
	form = _published_form(slug)
	return {
		"slug": form.slug,
		"title": form.title,
		"description": form.description,
		"accent": form.accent or "blue",
		"cover_image": form.cover_image,
		"collect_email": cint(form.collect_email),
		"allow_multiple": cint(form.allow_multiple),
		"thank_you_message": form.thank_you_message,
		"redirect_url": form.redirect_url,
		"fields": [_field_spec(f) for f in form.fields],
	}


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
			return int(raw)
		except (ValueError, TypeError):
			frappe.throw(f"'{label}' must be a whole number.")
	if ft in ("single_choice", "dropdown"):
		if spec["options"] and raw not in spec["options"]:
			frappe.throw(f"'{raw}' is not an allowed option for '{label}'.")
		return raw
	if ft == "checkboxes":
		values = raw if isinstance(raw, list) else [raw]
		for v in values:
			if spec["options"] and v not in spec["options"]:
				frappe.throw(f"'{v}' is not an allowed option for '{label}'.")
		return values
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
	# short_answer / paragraph / address / date
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

	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": filename,
		"content": content,
		"is_private": 1,
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"file_url": file_doc.file_url, "file_name": file_doc.file_name}


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=20, seconds=60 * 60)
def submit(slug: str, data: str, hp: str | None = None):
	"""Validate + insert a submission. Returns {name} of the created record."""
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

	if form.storage_mode == "Linked":
		name = _insert_linked(form, clean, specs)
	else:
		name = _insert_collection(form, clean, specs)

	frappe.db.commit()
	return {"name": name}


def _insert_collection(form, clean: dict, specs: dict) -> str:
	doc = frappe.new_doc(form.doctype_name)
	for fieldname, spec in specs.items():
		value = clean.get(fieldname)
		if value is None:
			continue
		if spec["field_type"] == "checkboxes":
			for opt in value:
				doc.append(fieldname, {"value": opt})
		else:
			doc.set(fieldname, value)

	if doc.meta.get_field("workflow_state"):
		doc.workflow_state = "Pending"

	doc.insert(ignore_permissions=True)

	# Own the files uploaded for this submission (they were created unattached).
	for fieldname, spec in specs.items():
		if spec["field_type"] == "file_upload" and clean.get(fieldname):
			_attach_file(clean[fieldname], doc.doctype, doc.name)

	return doc.name


def _attach_file(file_url: str, dt: str, dn: str):
	"""Link an already-uploaded File to the submission record it belongs to."""
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if name:
		frappe.db.set_value("File", name, {"attached_to_doctype": dt, "attached_to_name": dn})


def _insert_linked(form, clean: dict, specs: dict) -> str:
	doc = frappe.new_doc(form.target_doctype)
	target_meta = frappe.get_meta(form.target_doctype)
	for f in form.fields:
		if not f.mapped_field:
			continue
		fieldname = f.fieldname or resolve_fieldname(f)
		value = clean.get(fieldname)
		if value is None:
			continue
		if not target_meta.get_field(f.mapped_field):
			continue
		# Linked mode never maps checkboxes onto a single docfield; join if it happens.
		if isinstance(value, list):
			value = ", ".join(value)
		doc.set(f.mapped_field, value)
	doc.insert(ignore_permissions=True)
	return doc.name
