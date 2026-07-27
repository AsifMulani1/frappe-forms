# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Best-effort submission emails: a receipt to the respondent and a notification to the
# form owner. Both are enqueued and swallow errors — mail must never block a submission.

import frappe
from frappe.utils import cint

from forms.api.render import _session_email


def _receipt_recipient(captured: str | None) -> str | None:
	"""Recipient for a receipt: the collected email, else the signed-in user's own address.

	Deliberately NOT an arbitrary email-type answer — routing the receipt to any address a
	submitter types would turn the form into an email relay for its branded receipt.
	"""
	return captured or _session_email()


def _format_answer(value) -> str:
	if isinstance(value, dict):
		return "; ".join(f"{r}: {', '.join(v) if isinstance(v, list) else v}" for r, v in value.items())
	if isinstance(value, list):
		return ", ".join(str(v) for v in value)
	return str(value)


def _answers_table(clean: dict, specs: dict) -> str:
	"""An HTML table of label -> answer for the response, used in receipt and notification emails."""
	return "".join(
		f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>{frappe.utils.escape_html(spec['label'])}</td>"
		f"<td style='padding:4px 0'>{frappe.utils.escape_html(_format_answer(clean[fn]))}</td></tr>"
		for fn, spec in specs.items()
		if clean.get(fn) is not None
	)


def _maybe_send_receipt(form, clean: dict, specs: dict, captured_email: str | None = None):
	"""Email the respondent a copy of their answers (best-effort; never blocks submission)."""
	if not cint(form.email_receipt):
		return
	recipient = _receipt_recipient(captured_email)
	if not recipient:
		return
	message = (
		f"<p>Thanks for your response to <b>{frappe.utils.escape_html(form.title)}</b>. "
		f"Here's a copy for your records:</p><table>{_answers_table(clean, specs)}</table>"
	)
	try:
		# Enqueued (not now=True): a slow/down mail server must never block or fail the submission.
		frappe.sendmail(recipients=[recipient], subject=f"Your response to {form.title}",
			message=message)
	except Exception:
		frappe.log_error(title="Forms receipt email failed")


def _maybe_notify_admin(form, clean: dict, specs: dict, record_name: str, respondent_email: str | None):
	"""Email the form owner (or a configured address) when a new response arrives."""
	if not cint(form.notify_on_response):
		return
	recipient = (form.notify_email or "").strip() or frappe.db.get_value("User", form.owner, "email") or form.owner
	if not recipient or recipient == "Guest":
		return
	site = frappe.utils.get_url()
	link = f"{site}/forms/{form.slug}/responses"
	who = f" from {frappe.utils.escape_html(respondent_email)}" if respondent_email else ""
	message = (
		f"<p>New response{who} to <b>{frappe.utils.escape_html(form.title)}</b> "
		f"(<code>{frappe.utils.escape_html(record_name)}</code>).</p>"
		f"<table>{_answers_table(clean, specs)}</table>"
		f"<p><a href='{link}'>View all responses</a></p>"
	)
	try:
		frappe.sendmail(recipients=[recipient], subject=f"New response: {form.title}", message=message)
	except Exception:
		frappe.log_error(title="Forms response notification failed")
