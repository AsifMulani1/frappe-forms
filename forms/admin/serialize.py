# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Turning FF Form docs into the plain dicts the builder SPA consumes, plus the
# live response/completion counts shown on list and summary views.

import frappe
from frappe.utils import cint


def _response_count(form) -> int:
	if form.storage_mode == "Collection" and form.doctype_name and frappe.db.exists("DocType", form.doctype_name):
		return frappe.db.count(form.doctype_name)
	return 0


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
		"notify_on_response": cint(form.notify_on_response),
		"notify_email": form.notify_email,
		"opens_on": form.opens_on,
		"closes_on": form.closes_on,
		"response_limit": cint(form.response_limit),
		"is_quiz": cint(form.is_quiz),
		"show_score": cint(form.show_score),
		"thank_you_message": form.thank_you_message,
		"redirect_url": form.redirect_url,
		"embed_allowed_domains": form.embed_allowed_domains,
		"archived": cint(form.archived),
		"is_template": cint(form.is_template),
		# Encryption status for the builder. The wrapped private key is NEVER sent here — it's fetched
		# on demand (owner-only) by the responses view when the creator unlocks.
		"encrypted": cint(form.encrypted),
		"enc_fingerprint": form.enc_fingerprint,
		"enc_has_key": bool(form.enc_public_key),
		"fields": [
			{
				"name": f.name,
				"label": f.label,
				"fieldname": f.fieldname,
				"field_key": f.field_key,
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
				"condition_field": f.condition_field,
				"condition_operator": f.condition_operator or "equals",
				"condition_value": f.condition_value,
				"points": cint(f.points),
				"correct_answer": f.correct_answer,
			}
			for f in form.fields
		],
	}
