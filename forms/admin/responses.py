# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Read side of a Collection form's submissions: the summary charts, the paginated
# submission list, a single submission, and workflow-state triage.

import frappe
from frappe.utils import cint, flt

from forms.admin.access import _guard, _require, _safe_ident
from forms.admin.serialize import _completion_rate
from forms.compile import resolve_fieldname

# Largest page a client may request from list_submissions.
MAX_PAGE_SIZE = 200


def _published_collection(slug: str, ptype: str = "read"):
	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.local.response["http_status_code"] = 404
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	_require(name, ptype)
	form = frappe.get_doc("FF Form", name)
	if form.storage_mode != "Collection" or not form.doctype_name:
		frappe.throw("Responses are only available for collection forms.")
	return form


@frappe.whitelist()
def responses_summary(slug: str) -> dict:
	"""Live stat cards + per-choice distributions + rating breakdown."""
	_guard()
	form = _published_collection(slug)
	dt = _safe_ident(form.doctype_name)
	meta = frappe.get_meta(dt)
	total = frappe.db.count(dt)

	confirmed = 0
	if meta.get_field("workflow_state"):
		confirmed = frappe.db.count(dt, {"workflow_state": "Confirmed"})

	columns = set(frappe.db.get_table_columns(dt))

	charts = []
	rating = None
	for f in form.fields:
		fn = _safe_ident(resolve_fieldname(f))
		mf = meta.get_field(fn)
		# A field edited into the builder but not yet re-published has no live column/table
		# in the generated DocType. Skip it so one unmaterialised field never blanks the summary.
		if not mf:
			continue
		# Meta can still list a field whose physical column is gone (published before a
		# migrate, or a dropped column). Direct-column charts would 1054 the whole summary,
		# so skip them; child-table types (checkboxes/grids) are guarded separately below.
		if f.field_type in ("single_choice", "dropdown", "linear_scale", "rating") and fn not in columns:
			continue
		if f.field_type in ("single_choice", "dropdown"):
			rows = frappe.db.sql(
				f"SELECT `{fn}` AS label, COUNT(*) AS n FROM `tab{dt}` "
				f"WHERE `{fn}` IS NOT NULL AND `{fn}` != '' GROUP BY `{fn}` ORDER BY n DESC",
				as_dict=True,
			)
			charts.append({"label": f.label, "fieldname": fn, "type": "choice", "data": rows})
		elif f.field_type == "checkboxes":
			if not mf.options or not frappe.db.table_exists(mf.options):
				continue
			child = _safe_ident(mf.options)
			rows = frappe.db.sql(
				f"SELECT `value` AS label, COUNT(*) AS n FROM `tab{child}` "
				f"WHERE parenttype=%s GROUP BY `value` ORDER BY n DESC",
				(dt,), as_dict=True,
			)
			charts.append({"label": f.label, "fieldname": fn, "type": "choice", "data": rows})
		elif f.field_type == "linear_scale":
			rows = frappe.db.sql(
				f"SELECT `{fn}` AS label, COUNT(*) AS n FROM `tab{dt}` "
				f"WHERE `{fn}` IS NOT NULL GROUP BY `{fn}` ORDER BY `{fn}`",
				as_dict=True,
			)
			for r in rows:
				r["label"] = str(r["label"])
			charts.append({"label": f.label, "fieldname": fn, "type": "choice", "data": rows})
		elif f.field_type in ("mc_grid", "checkbox_grid"):
			if not mf.options or not frappe.db.table_exists(mf.options):
				continue
			child = _safe_ident(mf.options)
			rows = frappe.db.sql(
				f"SELECT `row` AS grid_row, `value` AS label, COUNT(*) AS n FROM `tab{child}` "
				f"WHERE parenttype=%s GROUP BY `row`, `value`",
				(dt,), as_dict=True,
			)
			# One mini-chart per grid row, preserving the builder's row order.
			by_row = {}
			for r in rows:
				by_row.setdefault(r["grid_row"], []).append({"label": r["label"], "n": r["n"]})
			for grid_row in [x.strip() for x in (f.grid_rows or "").splitlines() if x.strip()]:
				data = sorted(by_row.get(grid_row, []), key=lambda d: d["n"], reverse=True)
				if data:
					charts.append({"label": f"{f.label} — {grid_row}", "fieldname": f"{fn}__{grid_row}",
						"type": "choice", "data": data})
		elif f.field_type == "rating" and rating is None:
			# Rating stored as fraction of 5; bucket into 1..5 stars.
			buckets = {i: 0 for i in range(1, 6)}
			vals = frappe.db.sql(f"SELECT `{fn}` FROM `tab{dt}` WHERE `{fn}` > 0")
			count = 0
			score_sum = 0.0
			for (v,) in vals:
				stars = max(1, min(5, round(flt(v) * 5)))
				buckets[stars] += 1
				count += 1
				score_sum += stars
			rating = {
				"label": f.label,
				"average": round(score_sum / count, 1) if count else 0,
				"count": count,
				"buckets": buckets,
			}

	return {
		"total": total,
		"confirmed": confirmed,
		"completion": _completion_rate(form, total),
		"views": cint(form.views),
		"charts": charts,
		"rating": rating,
	}


@frappe.whitelist()
def list_submissions(slug: str, limit: int = 50, start: int = 0) -> dict:
	_guard()
	form = _published_collection(slug)
	dt = form.doctype_name
	meta = frappe.get_meta(dt)

	# Pick a sensible set of display fields: name/email-ish + first few.
	display = []
	for f in form.fields:
		fn = resolve_fieldname(f)
		if f.field_type in ("short_answer", "email", "single_choice", "dropdown") and meta.get_field(fn):
			display.append({"fieldname": fn, "label": f.label, "field_type": f.field_type})
		if len(display) >= 3:
			break

	encrypted = cint(form.encrypted)
	fields = ["name", "creation"] + [d["fieldname"] for d in display]
	# Encrypted forms carry the respondent identity as a ciphertext blob — ship it so the creator's
	# browser can decrypt the "who" column locally (the server can't).
	if encrypted and meta.get_field("enc_identity"):
		fields.append("enc_identity")
	# Only surface the triage State column once it's actually in use: some submission has been
	# moved off the default "Pending" (or an ERPNext workflow is driving a non-Pending state). A
	# form that never triages shouldn't show a column of identical "Pending" badges.
	has_workflow = bool(meta.get_field("workflow_state")) and bool(
		frappe.db.exists(dt, {"workflow_state": ["not in", ["", "Pending"]]})
	)
	if has_workflow:
		fields.append("workflow_state")

	rows = frappe.get_all(dt, fields=fields, limit=min(cint(limit) or 50, MAX_PAGE_SIZE), start=cint(start),
		order_by="creation desc")
	return {
		"doctype": dt,
		"display_fields": display,
		"has_workflow": has_workflow,
		"encrypted": encrypted,
		"rows": rows,
		"total": frappe.db.count(dt),
	}


@frappe.whitelist()
def get_submission(slug: str, name: str) -> dict:
	_guard()
	form = _published_collection(slug)
	doc = frappe.get_doc(form.doctype_name, name)
	fields = []
	multi = {}
	for f in form.fields:
		fn = resolve_fieldname(f)
		if f.field_type == "checkboxes":
			multi[f.label] = [r.value for r in (doc.get(fn) or [])]
		elif f.field_type in ("mc_grid", "checkbox_grid"):
			multi[f.label] = [f"{r.row}: {r.value}" for r in (doc.get(fn) or [])]
		else:
			val = doc.get(fn)
			if f.field_type == "rating" and val:
				val = f"{round(flt(val) * 5)} / 5"
			fields.append({"label": f.label, "fieldname": fn, "value": val})

	# Plaintext email only for unencrypted forms. Encrypted forms return the sealed blob instead —
	# the creator's browser decrypts it into the "who" the server itself can never read.
	if not cint(form.encrypted):
		email = doc.get("respondent_email")
		if email:
			fields.insert(0, {"label": "Email", "fieldname": "respondent_email", "value": email})

	if cint(form.is_quiz) and doc.get("max_score"):
		fields.insert(0, {"label": "Score", "fieldname": "score",
			"value": f"{flt(doc.get('score')):g} / {flt(doc.get('max_score')):g}"})

	return {
		"name": doc.name,
		"doctype": form.doctype_name,
		"creation": str(doc.creation),
		"workflow_state": doc.get("workflow_state"),
		"encrypted": cint(form.encrypted),
		"enc_identity": doc.get("enc_identity") if cint(form.encrypted) else None,
		"fields": fields,
		"multi": multi,
	}


@frappe.whitelist()
def set_workflow_state(slug: str, name: str, state: str) -> dict:
	_guard()
	from forms.api import WORKFLOW_STATES
	if state not in WORKFLOW_STATES:
		frappe.throw("Invalid workflow state.")
	form = _published_collection(slug, "write")
	frappe.db.set_value(form.doctype_name, name, "workflow_state", state)
	frappe.db.commit()
	return {"name": name, "workflow_state": state}
