# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# The compile engine: the bridge between a friendly FF Form and a real Frappe DocType.
# Ported faithfully from design-reference/src/fieldmodel.jsx.

import re

import frappe

# Authoritative field-type -> Frappe fieldtype map.
FIELD_TYPE_MAP = {
	"short_answer": "Data",
	"paragraph": "Small Text",
	"email": "Data",
	"number": "Int",
	"single_choice": "Select",
	"dropdown": "Select",
	"checkboxes": "Table MultiSelect",
	"date": "Date",
	"rating": "Rating",
	"yes_no": "Check",
	"phone": "Data",
	"time": "Time",
	"address": "Small Text",
	"file_upload": "Attach",
	"signature": "Signature",
}

# Display-only field types that produce no column on the generated DocType.
LAYOUT_TYPES = ("section_header",)

CHOICE_TYPES = ("single_choice", "dropdown")  # newline-joined string options


def scrub_fieldname(label: str, fallback: str = "field") -> str:
	"""snake_case ascii fieldname derived from a label."""
	base = re.sub(r"[^a-z0-9]+", "_", (label or "").lower())
	base = re.sub(r"^_+|_+$", "", base)
	return base or fallback


def title_case(text: str) -> str:
	cleaned = re.sub(r"_", " ", text or "")
	return " ".join(w.capitalize() for w in cleaned.split())


def resolve_fieldname(field) -> str:
	"""Frozen fieldname wins; otherwise derive from the label."""
	return field.fieldname or scrub_fieldname(field.label, field.name or "field")


def freeze_fieldnames(form):
	"""Set fieldname on any field lacking one, de-duped, and persist."""
	seen = set()
	for f in form.fields:
		name = f.fieldname or scrub_fieldname(f.label, f.name or "field")
		candidate, n = name, 1
		while candidate in seen:
			n += 1
			candidate = f"{name}_{n}"
		seen.add(candidate)
		f.fieldname = candidate
	form.save(ignore_permissions=True)


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
		base = resolve_fieldname(f)
		candidate, n = base, 1
		while candidate in seen:
			n += 1
			candidate = f"{base}_{n}"
		seen.add(candidate)

		df = {
			"fieldname": candidate,
			"label": f.label,
			"fieldtype": FIELD_TYPE_MAP[f.field_type],
		}
		if f.field_type == "email":
			df["options"] = "Email"
		elif f.field_type in CHOICE_TYPES:
			df["options"] = newline_options(f.options)
		elif f.field_type == "checkboxes":
			df["options"] = _child_doctype_name(form, candidate)

		if f.reqd:
			df["reqd"] = 1
		if f.help_text:
			df["description"] = f.help_text
		docfields.append(df)
	return docfields


def newline_options(options: str) -> str:
	"""Normalise newline-joined option text (already stored that way on FF Form Field)."""
	if not options:
		return ""
	lines = [ln.strip() for ln in str(options).splitlines() if ln.strip()]
	return "\n".join(lines)


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


def publish_collection(form):
	"""Create the generated DocType, or run an additive-only sync if it already exists."""
	doctype_name = form.doctype_name or title_case(form.slug)
	form.doctype_name = doctype_name

	# Option master + child link table for any checkboxes fields must exist first.
	for f in form.fields:
		if f.field_type == "checkboxes":
			ensure_checkbox_doctypes(form, f)

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
		for p in _permissions():
			dt.append("permissions", p)
		dt.insert(ignore_permissions=True)
		return dt.name

	# Additive-only sync: append new fields, hide removed ones, never drop a column.
	dt = frappe.get_doc("DocType", doctype_name)
	existing = {df.fieldname: df for df in dt.fields}
	desired_names = {df["fieldname"] for df in desired}

	for df in desired:
		if df["fieldname"] not in existing:
			dt.append("fields", df)

	for df in dt.fields:
		if df.fieldname == "workflow_state":
			continue
		if df.fieldname not in desired_names:
			df.hidden = 1
			df.read_only = 1

	dt.save(ignore_permissions=True)
	return dt.name


def publish_linked(form):
	"""Validate the mapping against the target DocType; make NO schema change."""
	if not form.target_doctype:
		frappe.throw("Linked forms must select a target DocType.")

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
	form = frappe.get_doc("FF Form", form_name)

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
			"apply_document_permissions": 1,
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


def cint_bool(value) -> int:
	from frappe.utils import cint

	return 1 if cint(value) else 0
