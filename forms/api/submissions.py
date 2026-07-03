# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Respondent-facing reads of their own responses: load a submission for editing (by edit
# token or Linked record), list "my submissions", and delete one.

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from forms.api.render import _published_form
from forms.compile import LAYOUT_TYPES, resolve_fieldname


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
