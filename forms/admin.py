# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Authenticated endpoints backing the builder SPA (dashboard, builder, responses).
# All data is read LIVE from the database - no hardcoded values anywhere.

import re

import frappe
import frappe.share  # ensure frappe.share is loaded for add/remove (not always auto-imported)
from frappe.utils import cint, flt

from forms.compile import compile_preview as _compile_preview
from forms.compile import publish as _publish
from forms.compile import resolve_fieldname, title_case

FIELD_FIELDS = ["name", "label", "fieldname", "field_type", "reqd", "help_text", "options", "mapped_field"]


def _guard():
	if frappe.session.user == "Guest":
		frappe.throw("Not permitted.", frappe.PermissionError)


def _response_count(form) -> int:
	if form.storage_mode == "Collection" and form.doctype_name and frappe.db.exists("DocType", form.doctype_name):
		return frappe.db.count(form.doctype_name)
	return 0


def _shared_names() -> set:
	"""FF Form names shared with the current user via Frappe DocShare."""
	rows = frappe.get_all(
		"DocShare",
		filters={"share_doctype": "FF Form", "user": frappe.session.user},
		pluck="share_name",
	)
	return set(rows)


@frappe.whitelist()
def list_forms(view: str = "all") -> list[dict]:
	"""Forms for a sidebar view, with LIVE response counts.

	view: all | published | draft | templates | archived | shared
	"""
	_guard()
	filters = {"archived": 0}
	if view == "published":
		filters["status"] = "Published"
	elif view == "draft":
		filters["status"] = "Draft"
	elif view == "templates":
		filters = {"is_template": 1}
	elif view == "archived":
		filters = {"archived": 1}
	elif view == "shared":
		names = _shared_names()
		if not names:
			return []
		filters = {"name": ("in", list(names)), "archived": 0}

	out = []
	for f in frappe.get_all(
		"FF Form",
		filters=filters,
		fields=["name", "title", "slug", "status", "storage_mode", "doctype_name",
			"target_doctype", "accent", "description", "cover_image", "category",
			"owner", "modified", "archived", "is_template"],
		order_by="modified desc",
	):
		form = frappe.get_doc("FF Form", f.name)
		responses = _response_count(form)
		out.append({
			**f,
			"owner_fullname": frappe.get_cached_value("User", f.owner, "full_name") or f.owner,
			"responses": responses,
			"field_count": len(form.fields),
			"completion": _completion_rate(form, responses),
			# A short, live preview of the first few fields - powers the template gallery cards.
			"preview": [
				{"label": ff.label, "field_type": ff.field_type, "reqd": cint(ff.reqd)}
				for ff in form.fields[:5]
			],
		})
	return out


@frappe.whitelist()
def nav_counts() -> dict:
	"""Live counts for the sidebar nav badges."""
	_guard()
	return {
		"all": frappe.db.count("FF Form", {"archived": 0}),
		"templates": frappe.db.count("FF Form", {"is_template": 1}),
		"archived": frappe.db.count("FF Form", {"archived": 1}),
		"shared": len(_shared_names()),
	}


def _completion_rate(form, responses) -> int:
	"""Completion funnel: submitted ÷ opened (views), as a live percentage.

	Returns 0 when the form hasn't been opened yet. Capped at 100 (a respondent
	can submit without us having counted their open, e.g. seeded/API inserts).
	"""
	views = cint(form.views)
	if not views:
		return 0
	return min(100, round((responses / views) * 100))


def _form_dict(form) -> dict:
	return {
		"name": form.name,
		"title": form.title,
		"slug": form.slug,
		"description": form.description,
		"status": form.status,
		"cover_image": form.cover_image,
		"category": form.category,
		"owner": form.owner,
		"owner_fullname": frappe.get_cached_value("User", form.owner, "full_name") or form.owner,
		"storage_mode": form.storage_mode,
		"target_doctype": form.target_doctype,
		"doctype_name": form.doctype_name,
		"accent": form.accent or "blue",
		"login_required": cint(form.login_required),
		"allow_multiple": cint(form.allow_multiple),
		"collect_email": cint(form.collect_email),
		"apply_doc_perms": cint(form.apply_doc_perms),
		"shuffle_questions": cint(form.shuffle_questions),
		"show_progress": cint(form.show_progress),
		"email_receipt": cint(form.email_receipt),
		"allow_edit": cint(form.allow_edit),
		"show_my_submissions": cint(form.show_my_submissions),
		"allow_delete": cint(form.allow_delete),
		"thank_you_message": form.thank_you_message,
		"redirect_url": form.redirect_url,
		"archived": cint(form.archived),
		"is_template": cint(form.is_template),
		"fields": [
			{
				"name": f.name,
				"label": f.label,
				"fieldname": f.fieldname,
				"field_type": f.field_type,
				"reqd": cint(f.reqd),
				"help_text": f.help_text,
				"options": f.options,
				"grid_rows": f.grid_rows,
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
			for f in form.fields
		],
	}


@frappe.whitelist()
def get_form(slug: str) -> dict:
	_guard()
	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.local.response["http_status_code"] = 404
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	return _form_dict(frappe.get_doc("FF Form", name))


@frappe.whitelist()
def create_form() -> dict:
	"""Create a Draft and return it (frontend routes to the builder)."""
	_guard()
	doc = frappe.new_doc("FF Form")
	doc.title = "Untitled form"
	doc.description = "Add a description to tell respondents what this form is for."
	doc.insert()
	return _form_dict(doc)


@frappe.whitelist()
def save_form(name: str, data: str) -> dict:
	"""Persist builder edits. Frozen fieldnames are never overwritten by the client."""
	_guard()
	payload = frappe.parse_json(data)
	doc = frappe.get_doc("FF Form", name)

	for key in ("title", "description", "accent", "cover_image", "category", "storage_mode",
			"target_doctype", "login_required", "allow_multiple", "collect_email",
			"apply_doc_perms", "shuffle_questions", "show_progress", "email_receipt", "allow_edit",
			"show_my_submissions", "allow_delete",
			"thank_you_message", "redirect_url", "is_template"):
		if key in payload:
			doc.set(key, payload[key])

	if "fields" in payload:
		existing = {f.name: f for f in doc.fields}
		doc.set("fields", [])
		for row in payload["fields"]:
			frozen = existing.get(row.get("name"))
			doc.append("fields", {
				"label": row.get("label"),
				"field_type": row.get("field_type"),
				"reqd": cint(row.get("reqd")),
				"help_text": row.get("help_text"),
				"options": row.get("options"),
				"grid_rows": row.get("grid_rows"),
				"mapped_field": row.get("mapped_field"),
				"has_other": cint(row.get("has_other")),
				"shuffle_options": cint(row.get("shuffle_options")),
				"min_value": row.get("min_value"),
				"max_value": row.get("max_value"),
				"max_length": cint(row.get("max_length")),
				"validation_pattern": row.get("validation_pattern"),
				"error_message": row.get("error_message"),
				"scale_min": cint(row.get("scale_min")) or 1,
				"scale_max": cint(row.get("scale_max")) or 5,
				"min_label": row.get("min_label"),
				"max_label": row.get("max_label"),
				# Keep a frozen fieldname; otherwise let publish derive it.
				"fieldname": (frozen.fieldname if (frozen and frozen.fieldname) else row.get("fieldname")),
			})

	doc.save()
	frappe.db.commit()
	return _form_dict(doc)


@frappe.whitelist()
def set_archived(name: str, archived: int = 1) -> dict:
	_guard()
	frappe.db.set_value("FF Form", name, "archived", cint(archived))
	frappe.db.commit()
	return {"name": name, "archived": cint(archived)}


@frappe.whitelist()
def delete_form(name: str) -> dict:
	"""Permanently delete a form. For a Collection form this also drops its generated DocType,
	every submitted record, and any child link tables. Linked forms leave their target untouched."""
	_guard()
	form = frappe.get_doc("FF Form", name)
	dt = form.doctype_name
	frappe.delete_doc("FF Form", name, force=True, ignore_permissions=True)
	if form.storage_mode == "Collection" and dt and frappe.db.exists("DocType", dt):
		# Drop generated records, child link tables, option masters, then the doctype.
		meta = frappe.get_meta(dt)
		child_doctypes = [f.options for f in meta.fields if f.fieldtype == "Table MultiSelect"]
		frappe.db.delete(dt)
		frappe.delete_doc("DocType", dt, force=True, ignore_permissions=True)
		for cd in child_doctypes:
			if cd and frappe.db.exists("DocType", cd):
				frappe.delete_doc("DocType", cd, force=True, ignore_permissions=True)
			master = cd.replace(" Item", " Option") if cd else None
			if master and frappe.db.exists("DocType", master):
				frappe.delete_doc("DocType", master, force=True, ignore_permissions=True)
	frappe.db.commit()
	return {"name": name, "deleted": True}


@frappe.whitelist()
def delete_forms(names: str) -> dict:
	"""Bulk delete. Each form is removed with the same cleanup as a single delete."""
	_guard()
	names = frappe.parse_json(names) if isinstance(names, str) else names
	for n in names:
		delete_form(n)
	return {"deleted": len(names)}


@frappe.whitelist()
def set_archived_bulk(names: str, archived: int = 1) -> dict:
	"""Bulk archive/restore the given forms."""
	_guard()
	names = frappe.parse_json(names) if isinstance(names, str) else names
	for n in names:
		frappe.db.set_value("FF Form", n, "archived", cint(archived))
	frappe.db.commit()
	return {"updated": len(names), "archived": cint(archived)}


@frappe.whitelist()
def duplicate_form(name: str) -> dict:
	"""Copy a form (used by 'Use template' and plain duplicate). Always a fresh Draft."""
	_guard()
	src = frappe.get_doc("FF Form", name)
	doc = frappe.new_doc("FF Form")
	doc.title = f"{src.title} (copy)"
	doc.description = src.description
	doc.accent = src.accent
	doc.storage_mode = src.storage_mode
	doc.target_doctype = src.target_doctype
	doc.thank_you_message = src.thank_you_message
	doc.collect_email = src.collect_email
	doc.allow_multiple = src.allow_multiple
	doc.login_required = src.login_required
	# New form: fieldnames are NOT carried over (they re-derive/freeze on its own publish).
	for f in src.fields:
		doc.append("fields", {
			"label": f.label, "field_type": f.field_type, "reqd": f.reqd,
			"help_text": f.help_text, "options": f.options, "mapped_field": f.mapped_field,
		})
	doc.insert()
	frappe.db.commit()
	return _form_dict(doc)


@frappe.whitelist()
def list_users() -> list[dict]:
	"""Enabled users to share a form with (excludes self and system users)."""
	_guard()
	rows = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ("not in", [frappe.session.user, "Administrator", "Guest"])},
		fields=["name", "full_name"],
		order_by="full_name asc",
		limit=50,
	)
	return rows


@frappe.whitelist()
def share_form(name: str, user: str, write: int = 0) -> dict:
	"""Share a form with another user via Frappe DocShare (shows in their 'Shared with me')."""
	_guard()
	frappe.share.add("FF Form", name, user, read=1, write=cint(write), share=0)
	frappe.db.commit()
	return {"name": name, "shared_with": user}


@frappe.whitelist()
def list_shares(name: str) -> list[dict]:
	"""People who currently have access to a form (drives the share dialog's access list)."""
	_guard()
	shares = frappe.get_all(
		"DocShare",
		filters={"share_doctype": "FF Form", "share_name": name},
		fields=["user", "read", "write"],
		order_by="creation asc",
	)
	if shares:
		names = [s.user for s in shares]
		full = {
			u.name: u.full_name
			for u in frappe.get_all("User", filters={"name": ("in", names)}, fields=["name", "full_name"])
		}
		for s in shares:
			s["full_name"] = full.get(s.user) or s.user
	return shares


@frappe.whitelist()
def unshare_form(name: str, user: str) -> dict:
	"""Revoke a user's access to a form."""
	_guard()
	frappe.share.remove("FF Form", name, user)
	frappe.db.commit()
	return {"name": name, "unshared": user}


@frappe.whitelist()
def publish_form(name: str) -> dict:
	_guard()
	result = _publish(name)
	return result


@frappe.whitelist()
def preview(slug: str) -> dict:
	_guard()
	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	return _compile_preview(name)


@frappe.whitelist()
def preview_form(slug: str) -> dict:
	"""Respondent-view render spec for the builder's live preview - works on Drafts too.
	Auth-only (Forms Managers); guests never reach unpublished forms."""
	_guard()
	from forms.api import public_render_spec

	name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
	if not name:
		frappe.throw("Form not found.", frappe.DoesNotExistError)
	return public_render_spec(frappe.get_doc("FF Form", name))


@frappe.whitelist()
def target_doctype_fields(doctype: str) -> list[dict]:
	"""Plain mappable fields on a target DocType (Linked mode)."""
	_guard()
	if not doctype or not frappe.db.exists("DocType", doctype):
		return []
	meta = frappe.get_meta(doctype)
	allowed = ("Data", "Small Text", "Text", "Select", "Int", "Float", "Date", "Phone")
	return [
		{"fieldname": f.fieldname, "label": f.label or f.fieldname, "fieldtype": f.fieldtype}
		for f in meta.fields
		if f.fieldtype in allowed and not f.hidden and f.fieldname
	]


# ---- Responses -------------------------------------------------------------

def _safe_ident(name: str) -> str:
	"""Guard a table/column name before it is interpolated into a backtick-quoted raw SQL identifier.
	DocType names and frozen fieldnames are system-derived (scrubbed to snake_case at publish), but we
	validate defensively so a malformed name can never break out of the backtick quoting."""
	if not name or not re.fullmatch(r"[A-Za-z0-9_ ]+", name):
		frappe.throw("Invalid identifier.")
	return name


def _published_collection(slug: str):
	form = frappe.get_doc("FF Form", frappe.db.get_value("FF Form", {"slug": slug}, "name"))
	if form.storage_mode != "Collection" or not form.doctype_name:
		frappe.throw("Responses are only available for collection forms.")
	return form


@frappe.whitelist()
def responses_summary(slug: str) -> dict:
	"""Live stat cards + per-choice distributions + rating breakdown."""
	_guard()
	form = _published_collection(slug)
	dt = _safe_ident(form.doctype_name)
	total = frappe.db.count(dt)

	confirmed = 0
	if frappe.get_meta(dt).get_field("workflow_state"):
		confirmed = frappe.db.count(dt, {"workflow_state": "Confirmed"})

	charts = []
	rating = None
	for f in form.fields:
		fn = _safe_ident(resolve_fieldname(f))
		if f.field_type in ("single_choice", "dropdown"):
			rows = frappe.db.sql(
				f"SELECT `{fn}` AS label, COUNT(*) AS n FROM `tab{dt}` "
				f"WHERE `{fn}` IS NOT NULL AND `{fn}` != '' GROUP BY `{fn}` ORDER BY n DESC",
				as_dict=True,
			)
			charts.append({"label": f.label, "fieldname": fn, "type": "choice", "data": rows})
		elif f.field_type == "checkboxes":
			child = _safe_ident(frappe.get_meta(dt).get_field(fn).options)
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
			child = _safe_ident(frappe.get_meta(dt).get_field(fn).options)
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

	fields = ["name", "creation"] + [d["fieldname"] for d in display]
	if meta.get_field("workflow_state"):
		fields.append("workflow_state")

	rows = frappe.get_all(dt, fields=fields, limit=cint(limit), start=cint(start),
		order_by="creation desc")
	return {
		"doctype": dt,
		"display_fields": display,
		"has_workflow": bool(meta.get_field("workflow_state")),
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

	email = doc.get("respondent_email")
	if email:
		fields.insert(0, {"label": "Email", "fieldname": "respondent_email", "value": email})

	return {
		"name": doc.name,
		"doctype": form.doctype_name,
		"creation": str(doc.creation),
		"workflow_state": doc.get("workflow_state"),
		"fields": fields,
		"multi": multi,
	}


@frappe.whitelist()
def set_workflow_state(slug: str, name: str, state: str) -> dict:
	_guard()
	form = _published_collection(slug)
	frappe.db.set_value(form.doctype_name, name, "workflow_state", state)
	frappe.db.commit()
	return {"name": name, "workflow_state": state}


@frappe.whitelist()
def export_csv(slug: str) -> str:
	"""Return submissions as CSV text (frontend triggers a download)."""
	_guard()
	import csv
	import io

	form = _published_collection(slug)
	dt = form.doctype_name
	# Table-backed answers (checkboxes, grids) have no flat cell; they're omitted from the CSV.
	cols = [resolve_fieldname(f) for f in form.fields
		if f.field_type not in ("checkboxes", "mc_grid", "checkbox_grid")]
	if frappe.get_meta(dt).get_field("respondent_email"):
		cols = ["respondent_email"] + cols
	headers = ["name"] + cols + ["workflow_state", "creation"]
	rows = frappe.get_all(dt, fields=[h for h in headers if frappe.get_meta(dt).get_field(h) or h in ("name", "creation")],
		order_by="creation desc")
	buf = io.StringIO()
	writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
	writer.writeheader()
	for r in rows:
		writer.writerow(r)
	return buf.getvalue()


@frappe.whitelist()
def has_app_permission():
	"""Gate the /apps screen tile - Forms Managers and System Managers only."""
	roles = set(frappe.get_roles())
	return bool(roles & {"Forms Manager", "System Manager"})


@frappe.whitelist()
def can_open_in_desk() -> bool:
	"""Only System Managers can open the native Desk spreadsheet (Report) view."""
	return "System Manager" in frappe.get_roles()
