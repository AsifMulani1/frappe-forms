# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Sharing a form with other Forms Managers via Frappe DocShare (the share dialog).

import frappe
import frappe.share  # ensure frappe.share is loaded for add/remove (not always auto-imported)
from frappe.utils import cint

from forms.admin.access import _guard, _require


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
	_require(name, "share")
	frappe.share.add("FF Form", name, user, read=1, write=cint(write), share=0)
	frappe.db.commit()
	return {"name": name, "shared_with": user}


@frappe.whitelist()
def list_shares(name: str) -> list[dict]:
	"""People who currently have access to a form (drives the share dialog's access list)."""
	_guard()
	_require(name, "share")
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
	_require(name, "share")
	frappe.share.remove("FF Form", name, user)
	frappe.db.commit()
	return {"name": name, "unshared": user}
