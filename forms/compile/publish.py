# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# The publish step: freeze fieldnames, then either generate/additively-sync a Collection
# DocType or validate a Linked mapping. compile_preview renders the same output without writing.

import frappe
from frappe.utils import cint

from forms.compile.doctypes import (
	_ensure_grid_doctype,
	_grid_doctype_name,
	_permissions,
	build_docfields,
	ensure_checkbox_doctypes,
)
from forms.compile.naming import (
	GRID_TYPES,
	cint_bool,
	freeze_fieldnames,
	resolve_fieldname,
	scrub_fieldname,
	title_case,
)
from forms.compile.validate import validate_conditional_logic

# DocField attributes we reconcile onto an already-published column on re-publish. Fieldtype is
# deliberately excluded — changing a live column's type risks data loss / DDL failures — except the
# Select<->Data swap a choice field makes when its "Other" write-in is toggled (both are varchar).
_RECONCILE_ATTRS = ("label", "options", "reqd", "description")
_VARCHAR_TYPES = {"Select", "Data"}


def _identity_field(form) -> dict:
	"""The respondent-identity system column. Encrypted forms store a sealed ciphertext blob
	(Long Text) instead of the plaintext email — so the raw DB never reveals who submitted."""
	if cint(form.encrypted):
		return {"fieldname": "enc_identity", "label": "Encrypted Identity", "fieldtype": "Long Text",
			"read_only": 1, "no_copy": 1}
	return {"fieldname": "respondent_email", "label": "Respondent Email", "fieldtype": "Data",
		"options": "Email"}


def publish_collection(form):
	"""Create the generated DocType, or run an additive-only sync if it already exists."""
	# Frappe caps DocType names at 61 chars; a long title must not produce an invalid name.
	doctype_name = (form.doctype_name or title_case(form.slug))[:61].strip()
	form.doctype_name = doctype_name

	# Child DocTypes for checkboxes (option master + link table) and grids must exist first.
	for f in form.fields:
		if f.field_type == "checkboxes":
			ensure_checkbox_doctypes(form, f)
		elif f.field_type in GRID_TYPES:
			_ensure_grid_doctype(_grid_doctype_name(form, resolve_fieldname(f)))

	desired = build_docfields(form)

	if not frappe.db.exists("DocType", doctype_name):
		dt = frappe.new_doc("DocType")
		dt.name = doctype_name
		dt.module = "Forms"
		dt.custom = 1
		dt.naming_rule = "Expression"
		dt.autoname = f"format:{form.slug.upper()}-{{YYYY}}-{{#####}}"
		dt.track_changes = 1
		for df in desired:
			dt.append("fields", df)
		# Workflow state lets the responses board show Pending/Confirmed/Waitlist.
		dt.append("fields", {
			"fieldname": "workflow_state",
			"label": "Workflow State",
			"fieldtype": "Data",
			"hidden": 1,
		})
		# Private per-submission token backing the "edit your response" link.
		dt.append("fields", {
			"fieldname": "edit_token",
			"label": "Edit Token",
			"fieldtype": "Data",
			"hidden": 1,
			"no_copy": 1,
		})
		# Respondent identity. On an encrypted form it's a ciphertext blob sealed to the creator's
		# key (so the DB never holds the plaintext email); otherwise the plain captured email.
		dt.append("fields", _identity_field(form))
		# Quiz score columns (populated on submit only when the form is a quiz).
		for fn, lbl in (("score", "Score"), ("max_score", "Max Score")):
			dt.append("fields", {"fieldname": fn, "label": lbl, "fieldtype": "Float", "read_only": 1})
		for p in _permissions():
			dt.append("permissions", p)
		dt.insert(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype_name)
		return dt.name

	# Additive sync: append new fields, hide removed ones (never drop a column), and reconcile
	# the editable attributes of fields that are still present.
	dt = frappe.get_doc("DocType", doctype_name)
	existing = {df.fieldname: df for df in dt.fields}
	desired_by_name = {df["fieldname"]: df for df in desired}
	desired_names = set(desired_by_name)

	for fieldname, df in desired_by_name.items():
		col = existing.get(fieldname)
		if col is None:
			dt.append("fields", df)
			continue
		# Field still present: reconcile its mutable props so edited options/required/help take
		# effect, and un-hide it if it was previously removed and has now been re-added.
		for attr in _RECONCILE_ATTRS:
			col.set(attr, df.get(attr) or (0 if attr == "reqd" else None))
		if col.fieldtype != df["fieldtype"] and {col.fieldtype, df["fieldtype"]} <= _VARCHAR_TYPES:
			col.fieldtype = df["fieldtype"]  # safe Select<->Data swap (Other write-in toggled)
		col.hidden = 0
		col.read_only = 0

	# Backfill system columns on DocTypes generated before these features existed.
	if "edit_token" not in existing:
		dt.append("fields", {"fieldname": "edit_token", "label": "Edit Token", "fieldtype": "Data",
			"hidden": 1, "no_copy": 1})
	identity = _identity_field(form)
	if identity["fieldname"] not in existing:
		dt.append("fields", identity)
	for fn, lbl in (("score", "Score"), ("max_score", "Max Score")):
		if fn not in existing:
			dt.append("fields", {"fieldname": fn, "label": lbl, "fieldtype": "Float", "read_only": 1})

	system_fields = {"workflow_state", "edit_token", "respondent_email", "enc_identity",
		"score", "max_score"}
	for df in dt.fields:
		if df.fieldname in system_fields:
			continue
		if df.fieldname not in desired_names:
			df.hidden = 1
			df.read_only = 1
			df.reqd = 0  # a removed field must not stay required, or every submit fails validation

	dt.save(ignore_permissions=True)
	frappe.clear_cache(doctype=doctype_name)
	return dt.name


def publish_linked(form):
	"""Validate the mapping against the target DocType; make NO schema change."""
	if not form.target_doctype:
		frappe.throw("Linked forms must select a target DocType.")

	# Guardrail: with apply_doc_perms off, submissions insert with ignore_permissions (the guest
	# path), so a form must only feed a DocType its owner could create records in directly. Without
	# this a Forms Manager could route unauthenticated inserts into ANY DocType, bypassing the
	# permission system. When apply_doc_perms is on, the submitter's own create permission is
	# enforced at submit time, so the owner's access isn't the boundary.
	if not cint(form.apply_doc_perms) and not frappe.has_permission(
		form.target_doctype, "create", user=form.owner
	):
		frappe.throw(
			f"This form inserts records without applying permissions, so it can only target a "
			f"DocType you're allowed to create. You don't have create access to {form.target_doctype}."
		)

	meta = frappe.get_meta(form.target_doctype)
	valid = {df.fieldname for df in meta.fields}

	problems = []
	mapped = 0
	for f in form.fields:
		if not f.mapped_field:
			continue
		mapped += 1
		if f.mapped_field not in valid:
			problems.append(f"'{f.label}' -> '{f.mapped_field}' (no such field on {form.target_doctype})")

	if problems:
		frappe.throw(
			"Some fields are mapped to invalid target fields:<br>" + "<br>".join(problems)
		)
	if not mapped:
		frappe.throw("Map at least one field to a target DocType field before publishing.")

	return form.target_doctype


def publish(form_name: str):
	"""Freeze names, dispatch by storage mode, set status Published."""
	form = frappe.get_doc("FF Form", form_name)

	# The title becomes the form's public slug and its generated DocType name, both permanent once
	# published. Refuse to publish while it's still unnamed, so we never create an "Untitled Form N"
	# DocType that's impossible to find on Desk.
	title = (form.title or "").strip()
	if not title or title.casefold() == "untitled form":
		frappe.throw(
			"Give your form a name before publishing — it becomes the form's link and its DocType name.",
			title="Name your form",
		)

	# Fail fast on a broken conditional-logic graph before we write any schema.
	validate_conditional_logic(form)

	freeze_fieldnames(form)
	form.reload()

	if form.storage_mode == "Linked":
		publish_linked(form)
	else:
		publish_collection(form)

	form.status = "Published"
	form.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "Published", "form": form.name, "storage_mode": form.storage_mode,
		"doctype_name": form.doctype_name, "target_doctype": form.target_doctype}


@frappe.whitelist()
def compile_preview(form_name: str) -> dict:
	"""Return the would-be DocType (Collection) or Web Form (Linked) JSON without writing."""
	if not frappe.has_permission("FF Form", "read", doc=form_name):
		frappe.throw("You don't have access to this form.", frappe.PermissionError)
	form = frappe.get_doc("FF Form", form_name)
	validate_conditional_logic(form)

	if form.storage_mode == "Linked":
		fields = []
		for f in form.fields:
			if not f.mapped_field:
				continue
			ft = "Data"
			if form.target_doctype and frappe.db.exists("DocType", form.target_doctype):
				meta = frappe.get_meta(form.target_doctype)
				df = meta.get_field(f.mapped_field)
				ft = df.fieldtype if df else "Data"
			row = {"fieldname": f.mapped_field, "label": f.label, "fieldtype": ft}
			if f.reqd:
				row["reqd"] = 1
			fields.append(row)
		return {
			"doctype": "Web Form",
			"name": scrub_fieldname(form.title),
			"title": form.title,
			"doc_type": form.target_doctype,
			"module": "Forms",
			"login_required": cint_bool(form.login_required),
			"anonymous": 0 if form.login_required else 1,
			"allow_multiple": cint_bool(form.allow_multiple),
			"apply_document_permissions": cint_bool(form.apply_doc_perms),
			"web_form_fields": fields,
		}

	return {
		"doctype": "DocType",
		"name": form.doctype_name or title_case(form.slug),
		"module": "Forms",
		"custom": 1,
		"naming_rule": "Expression",
		"autoname": f"format:{(form.slug or '').upper()}-{{YYYY}}-{{#####}}",
		"track_changes": 1,
		"fields": build_docfields(form),
		"permissions": _permissions(),
	}
