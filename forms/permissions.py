# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Row-level authorization for FF Form. A Forms Manager may only act on forms they OWN or that
# are SHARED with them (write requires share write=1; delete/share stay owner-only). Templates
# are shared building blocks, readable by every manager. System Managers are unrestricted.
#
# These hooks guard direct Desk/REST access (/api/resource/FF Form). The custom whitelisted
# builder endpoints in admin.py read/write via frappe.get_all / frappe.db.*, which bypass the
# permission layer, so they additionally call admin._require() — keep the two in sync.

import frappe

# Permission types a shared collaborator may NEVER perform (only the owner / System Manager).
OWNER_ONLY = {"delete", "share", "create"}


def _shared(form_name: str, user: str) -> dict | None:
	rows = frappe.get_all(
		"DocShare",
		filters={"share_doctype": "FF Form", "share_name": form_name, "user": user},
		fields=["read", "write"],
		limit=1,
	)
	return rows[0] if rows else None


def has_permission(doc, ptype="read", user=None, **kwargs) -> bool:
	"""Row-level check for FF Form (ANDed with the role grant in ff_form.json)."""
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return True
	if getattr(doc, "owner", None) == user:
		return True
	# Templates are reusable building blocks — any manager may read/duplicate them.
	if ptype == "read" and getattr(doc, "is_template", 0):
		return True
	if ptype in OWNER_ONLY:
		return False
	share = _shared(getattr(doc, "name", doc), user)
	if not share:
		return False
	if ptype in ("write", "submit", "cancel", "email", "print", "export", "report"):
		return bool(share.get("write"))
	return bool(share.get("read"))


def get_permission_query_conditions(user=None) -> str:
	"""Restrict FF Form list/report queries to forms the user may see."""
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	conds = [
		f"`tabFF Form`.owner = {frappe.db.escape(user)}",
		"`tabFF Form`.is_template = 1",
	]
	shared = frappe.get_all(
		"DocShare",
		filters={"share_doctype": "FF Form", "user": user},
		pluck="share_name",
	)
	if shared:
		joined = ", ".join(frappe.db.escape(s) for s in shared)
		conds.append(f"`tabFF Form`.name in ({joined})")
	return "(" + " or ".join(conds) + ")"
