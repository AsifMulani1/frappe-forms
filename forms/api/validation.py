# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Server-side answer validation: conditional-logic visibility (which fields count) and
# per-field coercion of a raw answer into a storable value. Never trusts client data.

import re

import frappe
from frappe.utils import cint, flt, validate_email_address

from forms.compile import GRID_TYPES, LAYOUT_TYPES, resolve_fieldname
from forms.config import SIGNATURE_MAX_BYTES


def _answer_values(actual) -> list[str]:
	"""Flatten any answer (scalar / checkbox list / grid dict) to a list of comparable strings."""
	if actual is None or actual == "":
		return []
	if isinstance(actual, list):
		return [str(x) for x in actual]
	if isinstance(actual, dict):
		out = []
		for v in actual.values():
			out.extend(v if isinstance(v, list) else [v])
		return [str(x) for x in out]
	return [str(actual)]


def _condition_met(operator: str, expected, actual) -> bool:
	"""Evaluate one visibility/skip condition. Shared shape with the SPA's evaluator."""
	expected = (expected or "").strip()
	values = _answer_values(actual)
	present = expected in values
	if operator == "not_equals":
		return not present
	if operator == "contains":
		return any(expected in v for v in values) if expected else bool(values)
	return present  # "equals" (default)


def _visible_specs(form, specs: dict, data: dict) -> dict:
	"""Drop fields whose conditional-logic rule isn't satisfied by the submitted answers.

	Hidden fields are skipped entirely — not validated (a hidden required field can't block a
	submit) and not stored. Evaluated against raw answers, keyed by the controlling field_key.
	"""
	key_to_fn = {
		f.field_key: (f.fieldname or resolve_fieldname(f))
		for f in form.fields
		if f.field_type not in LAYOUT_TYPES and f.field_key
	}
	visible = {}
	for fieldname, spec in specs.items():
		controlling = spec.get("condition_field")
		if controlling:
			ctrl_fn = key_to_fn.get(controlling)
			actual = data.get(ctrl_fn) if ctrl_fn else None
			if not _condition_met(spec.get("condition_operator"), spec.get("condition_value"), actual):
				continue
		visible[fieldname] = spec
	return visible


def _to_number(value):
	"""Parse an optional numeric bound (stored as Data). Blank/unparseable -> None."""
	if value is None or str(value).strip() == "":
		return None
	try:
		return flt(value)
	except (ValueError, TypeError):
		return None


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

	# Structural guard: only checkboxes (list) and grids (dict) accept containers. Any other type
	# handed a dict/list is a malformed or hostile payload — reject it cleanly instead of str()-ing
	# it into "['x']" and silently storing that.
	if ft not in ("checkboxes", *GRID_TYPES) and isinstance(raw, (dict, list)):
		frappe.throw(f"'{label}' has an invalid answer.")

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
		if len(raw) > SIGNATURE_MAX_BYTES:
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
	if ft == "date":
		# Frappe's Date column is forgiving on insert; validate the shape here so a bad date is
		# rejected with a clear message instead of being silently coerced or erroring in the ORM.
		try:
			parsed = frappe.utils.getdate(str(raw).strip())
		except Exception:
			parsed = None
		if not parsed:
			frappe.throw(f"'{label}' must be a valid date.")
		return str(parsed)
	return raw
