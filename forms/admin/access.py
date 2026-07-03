# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Authorization guards and identifier safety shared by every builder endpoint.

import re

import frappe


def _guard():
	"""Every builder endpoint requires a logged-in Forms Manager (or System Manager).
	The SPA router check is client-side only — this is the real gate."""
	if frappe.session.user == "Guest":
		frappe.throw("Not permitted.", frappe.PermissionError)
	if not (set(frappe.get_roles()) & {"Forms Manager", "System Manager"}):
		frappe.throw("Not permitted.", frappe.PermissionError)


def _require(form_name: str, ptype: str = "read"):
	"""Per-record authorization for the custom builder endpoints. These read/write via
	frappe.get_all / frappe.db.* (which bypass the DocType permission layer), so we enforce
	access explicitly via the same hook that guards Desk/REST (forms.permissions)."""
	if not form_name or not frappe.has_permission("FF Form", ptype, doc=form_name):
		frappe.local.response["http_status_code"] = 403
		frappe.throw("You don't have access to this form.", frappe.PermissionError)


def _accessible_filter(filters: dict) -> dict:
	"""Restrict a FF Form list query to forms the current user may see (owner + shared +
	templates). System Managers are unrestricted. Mutates and returns `filters`."""
	if "System Manager" in frappe.get_roles():
		return filters
	own = set(frappe.get_all("FF Form", filters={"owner": frappe.session.user}, pluck="name"))
	tmpl = set(frappe.get_all("FF Form", filters={"is_template": 1}, pluck="name"))
	accessible = own | _shared_names() | tmpl
	filters["name"] = ("in", list(accessible) or [""])
	return filters


def _shared_names() -> set:
	"""FF Form names shared with the current user via Frappe DocShare."""
	rows = frappe.get_all(
		"DocShare",
		filters={"share_doctype": "FF Form", "user": frappe.session.user},
		pluck="share_name",
	)
	return set(rows)


def _safe_ident(name: str) -> str:
	"""Guard a table/column name before it is interpolated into a backtick-quoted raw SQL identifier.
	DocType names and frozen fieldnames are system-derived (scrubbed to snake_case at publish), but we
	validate defensively so a malformed name can never break out of the backtick quoting."""
	if not name or not re.fullmatch(r"[A-Za-z0-9_ ]+", name):
		frappe.throw("Invalid identifier.")
	return name


@frappe.whitelist()
def has_app_permission():
	"""Gate the /apps screen tile - Forms Managers and System Managers only."""
	roles = set(frappe.get_roles())
	return bool(roles & {"Forms Manager", "System Manager"})
