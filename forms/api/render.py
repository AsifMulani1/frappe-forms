# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# The respondent-view render spec and the guest-safe session/view probes. Everything the
# public form needs to draw itself, minus quiz answer keys.

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from forms.compile import resolve_fieldname
from forms.config import PUBLIC_RENDER_RATE_LIMIT, RATE_WINDOW_HOUR, TRACK_VIEW_RATE_LIMIT

WORKFLOW_STATES = ("Pending", "Confirmed", "Waitlist")


def _published_form(slug: str):
	name = frappe.db.get_value("FF Form", {"slug": slug, "status": "Published"}, "name")
	if not name:
		frappe.local.response["http_status_code"] = 404
		frappe.throw("Form not found or not published.", frappe.DoesNotExistError)
	return frappe.get_doc("FF Form", name)


def _session_email() -> str | None:
	"""Email of the logged-in user, or None for guests."""
	user = frappe.session.user
	if user and user != "Guest":
		return frappe.db.get_value("User", user, "email") or user
	return None


def _field_spec(f) -> dict:
	return {
		"fieldname": resolve_fieldname(f),
		"field_key": f.field_key,
		"label": f.label,
		"field_type": f.field_type,
		"help_text": f.help_text,
		"reqd": cint(f.reqd),
		"options": [o.strip() for o in (f.options or "").splitlines() if o.strip()],
		"grid_rows": [r.strip() for r in (f.grid_rows or "").splitlines() if r.strip()],
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
		# Conditional logic: this field shows only when the controlling field (by field_key) matches.
		"condition_field": f.condition_field,
		"condition_operator": f.condition_operator or "equals",
		"condition_value": f.condition_value,
		# Quiz grading (correct_answer is server-only — never exposed to respondents).
		"points": cint(f.points),
		"correct_answer": [c.strip() for c in (f.correct_answer or "").splitlines() if c.strip()],
	}


def _public_field(f) -> dict:
	"""A field for the respondent view — the full spec minus quiz answer keys."""
	spec = _field_spec(f)
	spec.pop("correct_answer", None)  # respondents must never receive the answer key
	return spec


def _accepting_status(form) -> tuple[bool, str | None]:
	"""Whether the form is currently taking responses: open window + under any response limit."""
	now = frappe.utils.now_datetime()
	if form.opens_on and now < frappe.utils.get_datetime(form.opens_on):
		return False, "This form isn’t open for responses yet."
	if form.closes_on and now > frappe.utils.get_datetime(form.closes_on):
		return False, "This form is no longer accepting responses."
	limit = cint(form.response_limit)
	if limit and form.storage_mode == "Collection" and form.doctype_name and frappe.db.exists("DocType", form.doctype_name):
		if frappe.db.count(form.doctype_name) >= limit:
			return False, "This form has reached its response limit."
	return True, None


def public_render_spec(form, check_state: bool = True) -> dict:
	"""The respondent-view render spec for a form. Shared by the public (published-only)
	endpoint and the builder's preview, which renders Drafts too.

	check_state=False skips the open/close/limit gate so the builder preview always renders.
	"""
	accepting, closed_reason = _accepting_status(form) if check_state else (True, None)
	return {
		"slug": form.slug,
		"title": form.title,
		"description": form.description,
		"accent": form.accent or "blue",
		"cover_image": form.cover_image,
		"collect_email": cint(form.collect_email),
		"user_email": _session_email(),
		"storage_mode": form.storage_mode,
		"allow_multiple": cint(form.allow_multiple),
		"thank_you_message": form.thank_you_message,
		"redirect_url": form.redirect_url,
		"shuffle_questions": cint(form.shuffle_questions),
		"show_progress": cint(form.show_progress),
		"allow_edit": cint(form.allow_edit),
		"show_my_submissions": cint(form.show_my_submissions),
		"allow_delete": cint(form.allow_delete),
		"is_quiz": cint(form.is_quiz),
		"show_score": cint(form.show_score),
		"accepting": accepting,
		"closed_reason": closed_reason,
		"fields": [_public_field(f) for f in form.fields],
	}


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=PUBLIC_RENDER_RATE_LIMIT, seconds=RATE_WINDOW_HOUR)
def get_public_form(slug: str) -> dict:
	"""Render spec for a published form. 404 for drafts / unknown slugs."""
	return public_render_spec(_published_form(slug))


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=TRACK_VIEW_RATE_LIMIT, seconds=RATE_WINDOW_HOUR)
def track_view(slug: str) -> dict:
	"""Count one public open of a published form (drives the completion funnel).

	Atomic counter increment — no row per view, so it stays cheap at any volume.
	"""
	name = frappe.db.get_value("FF Form", {"slug": slug, "status": "Published"}, "name")
	if name:
		frappe.db.sql(
			"UPDATE `tabFF Form` SET views = COALESCE(views, 0) + 1 WHERE name = %s", name
		)
		frappe.db.commit()
	return {"ok": True}


@frappe.whitelist(allow_guest=True)
def session_info() -> dict:
	"""Guest-safe session probe for the SPA. Never errors: returns user=None for guests."""
	user = frappe.session.user
	if not user or user == "Guest":
		return {"user": None, "full_name": None}
	return {"user": user, "full_name": frappe.db.get_value("User", user, "full_name") or user}


def inject_csrf_token(context):
	"""update_website_context hook: ride the CSRF token along on the SPA's boot payload.

	frappe-ui's frappeRequest only sends X-Frappe-CSRF-Token when window.csrf_token is set, and
	the website boot omits it. Guests skip CSRF, but once a user logs in Frappe enforces it -
	without the token every authenticated POST (e.g. session_info) is rejected 400 and the SPA
	renders blank. The website layer has already built context.boot by the time this hook runs,
	so we just append the token; the page template emits it as window.csrf_token.
	"""
	if frappe.session.user and frappe.session.user != "Guest" and isinstance(context.get("boot"), dict):
		context["boot"]["csrf_token"] = frappe.sessions.get_csrf_token()
