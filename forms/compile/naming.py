# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Field-type vocabulary and fieldname derivation: the stable snake_case names a friendly
# FF Form field turns into on the generated DocType, plus the collision/reserved-name rules.

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
	"linear_scale": "Int",
	"mc_grid": "Table",
	"checkbox_grid": "Table",
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
GRID_TYPES = ("mc_grid", "checkbox_grid")  # rows x columns -> a child table of {row, value}
TEXT_TYPES = ("short_answer", "paragraph", "address")  # free text; accept an optional regex pattern

# Fieldnames a generated column may NEVER take: Frappe's own system columns (overwriting `owner`
# or `name` corrupts ownership/identity), the child-table link columns, and this app's reserved
# submission columns. A field whose label slugifies to one of these is suffixed (e.g. name_2).
from frappe.model import default_fields as _DEFAULT_FIELDS  # noqa: E402

RESERVED_FIELDNAMES = frozenset(_DEFAULT_FIELDS) | {
	"parent", "parentfield", "parenttype", "idx",
	"workflow_state", "edit_token", "respondent_email", "score", "max_score",
	"value", "row",  # child-table columns generated for checkboxes / grids
}


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


def _dedupe(base: str, seen: set) -> str:
	"""Return `base` (or base_2, base_3, …) avoiding `seen` and any reserved system column."""
	candidate, n = base, 1
	while candidate in seen or candidate in RESERVED_FIELDNAMES:
		n += 1
		candidate = f"{base}_{n}"
	seen.add(candidate)
	return candidate


def freeze_fieldnames(form):
	"""Set fieldname on any field lacking one, de-duped, and persist."""
	seen = set()
	for f in form.fields:
		name = f.fieldname or scrub_fieldname(f.label, f.name or "field")
		# A frozen name that collides with a reserved column (e.g. an old form pre-dating this
		# guard) is re-derived; an unfrozen one is deduped normally.
		f.fieldname = _dedupe(name, seen)
	form.save(ignore_permissions=True)


def cap_doctype_name(full: str) -> str:
	"""Cap a generated child-DocType name at Frappe's 61-char limit without letting the truncation
	collide two different forms onto one DocType.

	Two unrelated forms with long names can share a 61-char prefix; because the child-DocType
	ensure-helpers early-return on an existing name, a naive truncation would make the second form
	silently reuse the first form's child table (cross-form data bleed). When we must truncate, we
	reserve the last chars for a deterministic hash of the *full* (untruncated) name, so distinct
	inputs stay distinct while the same input is stable across re-publishes.
	"""
	import hashlib

	full = (full or "").strip()
	if len(full) <= 61:
		return full
	digest = hashlib.md5(full.encode("utf-8")).hexdigest()[:4]
	return f"{full[:56].strip()} {digest}"


def newline_options(options: str) -> str:
	"""Normalise newline-joined option text (already stored that way on FF Form Field)."""
	if not options:
		return ""
	lines = [ln.strip() for ln in str(options).splitlines() if ln.strip()]
	return "\n".join(lines)


def cint_bool(value) -> int:
	from frappe.utils import cint

	return 1 if cint(value) else 0
