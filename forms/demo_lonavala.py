# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Demo Day (Lonavala) live-audience form. Creates ONE published Collection form the audience
# fills from a QR code, then the responses are opened in Frappe Sheets on stage.
#
# Reproducible + idempotent: re-running deletes the prior demo form (and its generated DocType
# + records) and recreates it cleanly. Runs on any site (incl. Frappe Cloud):
#
#   bench --site <your-site> execute forms.demo_lonavala.run
#
# Optional fallback data for rehearsal (so the sheet isn't empty):
#   bench --site <your-site> execute forms.demo_lonavala.seed_samples --kwargs "{'n': 8}"
# Wipe it before going live so only the real audience shows up:
#   bench --site <your-site> execute forms.demo_lonavala.clear_responses

import random

import frappe

from forms.compile import publish, resolve_fieldname

SLUG = "demo-day"          # derived from the title below; keep the title in sync
DOCTYPE_NAME = "Demo Day Vibe Check"

FUEL = ["Cutting chai", "Filter coffee", "Vada pav, obviously",
	"Just the mountain air", "Running on zero sleep"]

FIELDS = [
	{
		"label": "It's a monsoon morning in Lonavala. What's fueling you right now?",
		"fieldname": "fuel",
		"field_type": "single_choice", "reqd": 1, "options": "\n".join(FUEL),
	},
	{
		"label": "How much would you trust an AI agent to ship your work while you grab a chai?",
		"fieldname": "trust_ai",
		"field_type": "linear_scale", "reqd": 1,
		"scale_min": 1, "scale_max": 5,
		"min_label": "I'm watching every keystroke", "max_label": "Go forth, my child",
	},
	{
		"label": "Agentic AI in one word — go.",
		"fieldname": "ai_one_word",
		"field_type": "short_answer", "reqd": 1, "max_length": 24,
	},
]


def _delete_existing():
	"""Idempotency: remove any prior demo form(s) + the generated DocType and its records.

	Matches by slug AND by the generated DocType name, so re-runs stay clean even if an
	earlier attempt produced a title-derived slug variant.
	"""
	names = set(frappe.get_all("FF Form", filters={"slug": SLUG}, pluck="name"))
	names |= set(frappe.get_all("FF Form", filters={"doctype_name": DOCTYPE_NAME}, pluck="name"))
	for name in names:
		frappe.delete_doc("FF Form", name, force=True, ignore_permissions=True)
	if frappe.db.exists("DocType", DOCTYPE_NAME):
		frappe.db.delete(DOCTYPE_NAME)
		frappe.delete_doc("DocType", DOCTYPE_NAME, force=True, ignore_permissions=True)
	frappe.db.commit()


def run():
	"""Create + publish the guest demo form. Returns the public fill URL."""
	_delete_existing()

	doc = frappe.new_doc("FF Form")
	doc.title = "Demo Day"          # slugifies to "demo-day" (SLUG) while Draft, frozen on publish
	doc.description = "Three quick taps. Then look up at the screen."
	doc.accent = "teal"
	doc.storage_mode = "Collection"
	doc.doctype_name = DOCTYPE_NAME
	doc.thank_you_message = "You're in — now look up at the screen."
	# Live-audience settings: anyone can fill, no login, no email friction, resubmits allowed.
	doc.login_required = 0
	doc.collect_email = 0
	doc.allow_multiple = 1
	doc.show_progress = 0
	doc.shuffle_questions = 0
	for f in FIELDS:
		doc.append("fields", f)
	doc.insert(ignore_permissions=True)
	publish(doc.name)
	doc.reload()
	frappe.db.commit()

	url = f"/forms/f/{SLUG}"
	print("\n=== Demo form ready ===")
	print(f"Title:        {doc.title}")
	print(f"DocType:      {doc.doctype_name}")
	print(f"Fill URL:     {url}   (prefix with your site, e.g. https://<site>{url})")
	print("Access:       guest, no email, multiple submissions allowed")
	return url


def seed_samples(n=8):
	"""Add a few fun fallback responses so rehearsal / a thin crowd still charts well."""
	form = frappe.get_doc("FF Form", {"slug": SLUG})
	dt = form.doctype_name
	m = {f.label: resolve_fieldname(f) for f in form.fields}
	words = ["magic", "inevitable", "scary", "overhyped", "wild", "chai", "fast",
		"finally", "unreal", "help", "future", "spicy"]
	for _ in range(n):
		rec = frappe.new_doc(dt)
		rec.set(m[FIELDS[0]["label"]], random.choice(FUEL))
		rec.set(m[FIELDS[1]["label"]], random.choice([2, 3, 3, 4, 4, 4, 5]))
		rec.set(m[FIELDS[2]["label"]], random.choice(words))
		rec.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Inserted {n} sample responses into {dt}.")


def clear_responses():
	"""Wipe all responses (keep the form) — run before going live so only real answers show."""
	form = frappe.get_doc("FF Form", {"slug": SLUG})
	frappe.db.delete(form.doctype_name)
	frappe.db.commit()
	print(f"Cleared all responses from {form.doctype_name}.")
