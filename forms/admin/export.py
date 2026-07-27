# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Exporting a Collection form's submissions: CSV download and Frappe Sheets sync.

import frappe
import frappe.share  # frappe.share.add for the Sheets export share; not always auto-imported

from forms.admin.access import _guard
from forms.admin.responses import _published_collection
from forms.compile import resolve_fieldname

# Synchronous export ceiling: never load an unbounded result set into memory.
EXPORT_ROW_CAP = 50_000

# Leading characters a spreadsheet may execute as a formula. A submitted answer starting with one
# of these is prefixed with a quote so it exports as literal text (CSV / Sheets injection guard).
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _formula_safe(value) -> str:
	"""Stringify a cell, neutralising a leading formula trigger so it can't execute on open."""
	text = "" if value is None else str(value)
	return "'" + text if text and text[0] in _FORMULA_TRIGGERS else text


def _submission_columns(form) -> list:
	"""Ordered (key, label) columns shared by the CSV and Frappe Sheets exports.

	`key` is the DocType fieldname (or name/creation/workflow_state); `label` is the
	human-readable header. Table-backed answers (checkboxes, grids) have no flat cell,
	so they're omitted from both exports.
	"""
	meta = frappe.get_meta(form.doctype_name)
	cols = [("name", "Response ID")]
	if meta.get_field("respondent_email"):
		cols.append(("respondent_email", "Email"))
	for f in form.fields:
		if f.field_type in ("checkboxes", "mc_grid", "checkbox_grid"):
			continue
		fn = resolve_fieldname(f)
		cols.append((fn, f.label or fn))
	cols.append(("workflow_state", "Status"))
	cols.append(("creation", "Submitted"))
	return cols


def _submission_rows(form, cols: list) -> list:
	"""Fetch submission rows (newest first) for the given columns, enforcing the export cap."""
	dt = form.doctype_name
	meta = frappe.get_meta(dt)
	# Hard cap: a synchronous export must never load an unbounded result set into memory.
	# Forms past this size should export via a background job (future work).
	cap = EXPORT_ROW_CAP
	if frappe.db.count(dt) > cap:
		frappe.throw(f"This form has more than {cap:,} responses — exporting that many at once isn't "
			"supported yet. Filter or contact an administrator for a bulk export.")
	keys = [k for k, _ in cols]
	fetch = [k for k in keys if meta.get_field(k) or k in ("name", "creation")]
	return frappe.get_all(dt, fields=fetch, order_by="creation desc", limit=cap)


@frappe.whitelist()
def export_csv(slug: str) -> str:
	"""Return submissions as CSV text (frontend triggers a download)."""
	_guard()
	import csv
	import io

	form = _published_collection(slug)
	cols = _submission_columns(form)
	rows = _submission_rows(form, cols)
	headers = [k for k, _ in cols]
	buf = io.StringIO()
	writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
	writer.writeheader()
	for r in rows:
		writer.writerow({k: _formula_safe(r.get(k)) for k in headers})
	return buf.getvalue()


def _col_label(idx: int) -> str:
	"""0-based column index -> spreadsheet column letter (0->A, 26->AA)."""
	label = ""
	idx += 1
	while idx:
		idx, rem = divmod(idx - 1, 26)
		label = chr(65 + rem) + label
	return label


def _build_sheets_data(headers: list, data_rows: list) -> str:
	"""Pack a header row + data rows into Frappe Sheets' `sheets_data` JSON string.

	Schema verified empirically against frappe/sheets: the live blob is
	{"sheet": {"v": 2, "current": <tab>, "sheets": {<tab>: {"rows": {<rowIdx>: [cells...]}}}},
	 "formats": {<tab>: {"cells": {...}, "cols": {}, "rows": {}}}}
	with 0-based string row keys and the header row bolded. save_sheet handles
	compression; we pass the plain JSON string.
	"""
	tab = "Responses"
	grid = {"0": [_formula_safe(h) for h in headers]}
	for i, row in enumerate(data_rows, start=1):
		grid[str(i)] = [_formula_safe(v) for v in row]
	bold_header = {f"{_col_label(c)}1": {"bold": True} for c in range(len(headers))}
	payload = {
		"sheet": {"v": 2, "current": tab, "sheets": {tab: {"rows": grid}}},
		"formats": {tab: {"cells": bold_header, "cols": {}, "rows": {}}},
	}
	return frappe.as_json(payload)


@frappe.whitelist()
def open_in_sheet(slug: str) -> dict:
	"""Export this form's responses into Frappe Sheets and return the URL to open.

	One persistent sheet per form: the Sheet id is stored on FF Form.sheet_name.
	First call creates the sheet (and shares it so any Forms Manager can refresh it);
	later calls re-export the latest responses into the same sheet.
	"""
	_guard()
	try:
		from sheets.api import save_sheet
	except ImportError:
		frappe.throw("Frappe Sheets isn't installed on this site. Ask an administrator to install it.")

	form = _published_collection(slug)
	cols = _submission_columns(form)
	rows = _submission_rows(form, cols)
	keys = [k for k, _ in cols]
	labels = [lbl for _, lbl in cols]
	data = [[r.get(k) for k in keys] for r in rows]
	blob = _build_sheets_data(labels, data)

	title = f"{form.title} — Responses"
	existing = form.sheet_name if form.sheet_name and frappe.db.exists("Sheet", form.sheet_name) else ""
	res = save_sheet(title=title, sheets_data=blob, name=existing)
	name = res["name"]
	if name != form.sheet_name:
		frappe.db.set_value("FF Form", form.name, "sheet_name", name, update_modified=False)
	# Grant the sheet to exactly who can already see this form's responses — its owner and anyone
	# it's shared with — never `everyone`: the sheet holds response data (incl. PII). Re-run on
	# every export so collaborators added after the sheet was created still get access.
	_share_sheet_with_form_collaborators(form, name)
	return {"sheet_name": name, "url": f"/sheets?id={name}"}


def _share_sheet_with_form_collaborators(form, sheet_name: str):
	"""Share the responses sheet with the form's owner and its DocShare collaborators (only)."""
	recipients = {form.owner}
	recipients.update(
		frappe.get_all(
			"DocShare",
			filters={"share_doctype": "FF Form", "share_name": form.name},
			pluck="user",
		)
	)
	for user in recipients:
		if user and user not in ("Guest", "Administrator"):
			frappe.share.add("Sheet", sheet_name, user=user, write=1, share=0, notify=False)
