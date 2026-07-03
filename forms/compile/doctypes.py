# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Materialising a form's fields into Frappe schema: the DocField list for the parent, and the
# child DocTypes (option masters + link tables for checkboxes, {row, value} tables for grids).

import frappe

from forms.compile.naming import (
	CHOICE_TYPES,
	FIELD_TYPE_MAP,
	GRID_TYPES,
	LAYOUT_TYPES,
	_dedupe,
	newline_options,
	resolve_fieldname,
	title_case,
)


def _child_doctype_name(form, fieldname: str) -> str:
	"""Child (link table) DocType name for a checkboxes (Table MultiSelect) field.

	Frappe DocType names are capped at 61 chars, so trim the parent prefix if needed.
	"""
	parent = form.doctype_name or title_case(form.slug)
	name = f"{parent} {title_case(fieldname)} Item"
	return name[:61].strip()


def _option_master_name(form, fieldname: str) -> str:
	"""Master DocType holding the allowed option values for a checkboxes field."""
	parent = form.doctype_name or title_case(form.slug)
	name = f"{parent} {title_case(fieldname)} Option"
	return name[:61].strip()


def _grid_doctype_name(form, fieldname: str) -> str:
	"""Child (table) DocType name for a grid field - one row per answered grid-row."""
	parent = form.doctype_name or title_case(form.slug)
	name = f"{parent} {title_case(fieldname)} Grid"
	return name[:61].strip()


def _ensure_grid_doctype(name: str):
	"""istable DocType with {row, value} Data columns backing a grid field."""
	if frappe.db.exists("DocType", name):
		return
	child = frappe.new_doc("DocType")
	child.name = name
	child.module = "Forms"
	child.custom = 1
	child.istable = 1
	child.append("fields", {"fieldname": "row", "label": "Row", "fieldtype": "Data", "in_list_view": 1})
	child.append("fields", {"fieldname": "value", "label": "Value", "fieldtype": "Data", "in_list_view": 1})
	child.insert(ignore_permissions=True)


def build_docfields(form) -> list[dict]:
	"""Translate FF Form fields into a list of Frappe DocField dicts.

	De-dupes derived fieldnames. For checkboxes, the caller is responsible for ensuring the
	child DocType exists (see _ensure_child_doctype); here we only point ``options`` at it.
	"""
	docfields = []
	seen = set()
	for f in form.fields:
		if f.field_type in LAYOUT_TYPES:
			continue  # display-only (e.g. section header) - no column
		candidate = _dedupe(resolve_fieldname(f), seen)

		df = {
			"fieldname": candidate,
			"label": f.label,
			"fieldtype": FIELD_TYPE_MAP[f.field_type],
		}
		if f.field_type == "email":
			df["options"] = "Email"
		elif f.field_type in CHOICE_TYPES:
			# An "Other" write-in means an arbitrary string can land here, so we can't compile to a
			# constrained Select (Frappe would reject the free-text value). Store as plain Data and
			# let the submission API enforce membership-or-other. Frozen at publish like the schema.
			if f.get("has_other"):
				df["fieldtype"] = "Data"
			else:
				df["options"] = newline_options(f.options)
		elif f.field_type == "checkboxes":
			df["options"] = _child_doctype_name(form, candidate)
		elif f.field_type in GRID_TYPES:
			df["options"] = _grid_doctype_name(form, candidate)

		# A conditionally-shown field can't be a hard DocType-level mandatory: when its rule isn't
		# met it's legitimately empty. Its "required when visible" rule is enforced in the submit API.
		if f.reqd and not f.get("condition_field"):
			df["reqd"] = 1
		if f.help_text:
			df["description"] = f.help_text
		docfields.append(df)
	return docfields


def _ensure_option_master(name: str, options: list[str]):
	"""Master DocType holding the allowed option values (named by the value itself).

	Frappe requires a Table MultiSelect child to carry a Link field, so the options live
	in a real master and each selection becomes a governed link row.
	"""
	if not frappe.db.exists("DocType", name):
		master = frappe.new_doc("DocType")
		master.name = name
		master.module = "Forms"
		master.custom = 1
		master.autoname = "field:value"
		master.append("fields", {"fieldname": "value", "label": "Value", "fieldtype": "Data",
			"reqd": 1, "unique": 1, "in_list_view": 1})
		master.append("permissions", {"role": "System Manager", "read": 1, "write": 1,
			"create": 1, "delete": 1})
		master.append("permissions", {"role": "Forms Manager", "read": 1})
		master.insert(ignore_permissions=True)

	for opt in options:
		if opt and not frappe.db.exists(name, opt):
			frappe.get_doc({"doctype": name, "value": opt}).insert(ignore_permissions=True)


def _ensure_child_doctype(child_name: str, master_name: str):
	"""istable DocType with a single Link field 'value' -> the option master."""
	if frappe.db.exists("DocType", child_name):
		return
	child = frappe.new_doc("DocType")
	child.name = child_name
	child.module = "Forms"
	child.custom = 1
	child.istable = 1
	child.append("fields", {"fieldname": "value", "label": "Value", "fieldtype": "Link",
		"options": master_name, "in_list_view": 1, "reqd": 1})
	child.insert(ignore_permissions=True)


def ensure_checkbox_doctypes(form, field):
	"""Create the option master (seeded) + child link table for a checkboxes field."""
	fieldname = resolve_fieldname(field)
	master = _option_master_name(form, fieldname)
	child = _child_doctype_name(form, fieldname)
	_ensure_option_master(master, [o.strip() for o in (field.options or "").splitlines() if o.strip()])
	_ensure_child_doctype(child, master)
	return child


def _permissions() -> list[dict]:
	return [
		{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
		{"role": "Forms Manager", "read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1},
	]
