# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# DEV-ONLY seed. Writes REAL records through the app's own code paths so the UI reads them
# live. Idempotent: deletes prior seed forms + their generated DocTypes + records, then
# recreates. Run with:  bench --site forms.localhost execute forms.seed.run
# NOT wired into after_install - dev command only.

import random

import frappe
from faker import Faker
from frappe.utils import add_to_date, now_datetime

from forms.compile import publish, resolve_fieldname

fake = Faker()


def fn_map(form):
	"""Map each field's label to its real (scrubbed/frozen) Frappe fieldname."""
	return {f.label: resolve_fieldname(f) for f in form.fields}


def by_label(form, values, multi=None):
	"""Translate label-keyed values into the doctype's real fieldnames."""
	m = fn_map(form)
	vals = {m[label]: v for label, v in values.items() if label in m}
	ms = {m[label]: v for label, v in (multi or {}).items() if label in m}
	return vals, ms

SEED_SLUGS = ["devcon-2026", "q1-nps", "support-csat", "contact-us", "eng-application-2026",
	"tpl-event-registration", "tpl-customer-feedback",
	"tpl-bug-report", "tpl-it-request", "tpl-creative-request", "tpl-product-feedback"]

TRACKS = ["Platform & APIs", "Frontend & UI", "Data & Insights"]
DIET = ["Vegetarian", "Vegan", "Gluten-free", "Nut allergy"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
CSAT_REASONS = ["Resolved quickly", "Agent was helpful", "Took too long", "Issue not solved"]
WF = ["Confirmed", "Pending", "Waitlist"]


def _spread_creation(doctype, name, days_back):
	"""Backdate creation/modified so the dashboard timeline looks realistic."""
	ts = add_to_date(now_datetime(), days=-days_back, hours=-random.randint(0, 23),
		minutes=-random.randint(0, 59))
	frappe.db.set_value(doctype, name, "creation", ts, update_modified=False)
	frappe.db.set_value(doctype, name, "modified", ts, update_modified=False)


def _cleanup():
	for slug in SEED_SLUGS:
		name = frappe.db.get_value("FF Form", {"slug": slug}, "name")
		if not name:
			continue
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


def _make_form(slug, title, fields, *, storage="Collection", target=None, doctype_name=None,
		description="", accent="blue", publish_it=True, thank_you="", is_template=0, category=""):
	doc = frappe.new_doc("FF Form")
	doc.title = title
	doc.slug = slug
	doc.description = description
	doc.accent = accent
	doc.storage_mode = storage
	doc.target_doctype = target
	doc.thank_you_message = thank_you
	doc.is_template = is_template
	doc.category = category
	if doctype_name:
		doc.doctype_name = doctype_name
	for f in fields:
		doc.append("fields", f)
	doc.insert(ignore_permissions=True)
	if publish_it:
		publish(doc.name)
		doc.reload()
	return doc


def _insert_record(doctype, values, multiselect=None, workflow_state=None, days_back=0):
	doc = frappe.new_doc(doctype)
	for k, v in values.items():
		doc.set(k, v)
	for field, opts in (multiselect or {}).items():
		for opt in opts:
			doc.append(field, {"value": opt})
	if workflow_state and doc.meta.get_field("workflow_state"):
		doc.workflow_state = workflow_state
	doc.insert(ignore_permissions=True)
	_spread_creation(doctype, doc.name, days_back)
	return doc.name


def _ensure_forms_manager_user():
	email = "forms.manager@example.com"
	if not frappe.db.exists("User", email):
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = "Riya"
		user.last_name = "Shah"
		user.send_welcome_email = 0
		user.new_password = "Espresso-Forms-2026!"
		user.append("roles", {"role": "Forms Manager"})
		user.insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
		if "Forms Manager" not in [r.role for r in user.roles]:
			user.append("roles", {"role": "Forms Manager"})
			user.save(ignore_permissions=True)
	return email


def run():
	if not frappe.conf.get("developer_mode") and frappe.local.site not in ("forms.localhost",):
		# Light guard: only seed dev sites.
		print("Refusing to seed a non-dev site.")
		return

	print("Cleaning up prior seed data ...")
	_cleanup()

	manager = _ensure_forms_manager_user()
	summary = {"forms": 0, "doctypes": [], "submissions": 0, "contacts": 0}

	# 1) DevCon 2026 - Registration (Collection)
	devcon = _make_form(
		"devcon-2026", "DevCon 2026 - Registration",
		[
			{"label": "Full name", "field_type": "short_answer", "reqd": 1},
			{"label": "Email address", "field_type": "email", "reqd": 1,
				"help_text": "We'll send your ticket here."},
			{"label": "Which track will you attend?", "field_type": "single_choice", "reqd": 1,
				"options": "\n".join(TRACKS)},
			{"label": "Dietary requirements", "field_type": "checkboxes",
				"options": "\n".join(DIET), "help_text": "Select all that apply."},
			{"label": "T-shirt size", "field_type": "dropdown", "options": "\n".join(SIZES)},
			{"label": "How was last year's event?", "field_type": "rating",
				"help_text": "Optional - skip if first time."},
			{"label": "Number of guests", "field_type": "number", "help_text": "Max 2 per attendee."},
			{"label": "Subscribe to event updates", "field_type": "yes_no"},
			{"label": "Anything else we should know?", "field_type": "paragraph"},
		],
		doctype_name="DevCon Registration", accent="blue",
		description="Reserve your seat for our annual developer conference. Submissions are saved as records in the Frappe workspace.",
		thank_you="You're registered! We've emailed your ticket - see you at DevCon 2026.",
	)
	summary["forms"] += 1
	summary["doctypes"].append(devcon.doctype_name)
	for i in range(248):
		vals, ms = by_label(
			devcon,
			{
				"Full name": fake.name(),
				"Email address": fake.email(),
				"Which track will you attend?": random.choice(TRACKS),
				"T-shirt size": random.choice(SIZES),
				"How was last year's event?": random.choice([0.6, 0.8, 0.8, 1.0, 1.0, 1.0, 0.4]),
				"Number of guests": random.choice([0, 0, 1, 1, 2]),
				"Subscribe to event updates": random.choice([0, 1, 1]),
				"Anything else we should know?": random.choice(
					["", "", "Looking forward to it!", "Please seat me near the front.",
					 "First time attending."]),
			},
			multi={"Dietary requirements": random.sample(DIET, random.randint(0, 2))},
		)
		_insert_record(devcon.doctype_name, vals, multiselect=ms,
			workflow_state=random.choice(WF), days_back=random.randint(0, 27))
	summary["submissions"] += 248

	# 2) Q1 Product NPS survey (Collection)
	nps = _make_form(
		"q1-nps", "Q1 Product NPS survey",
		[
			{"label": "How likely are you to recommend us?", "field_type": "number", "reqd": 1,
				"help_text": "0 = not at all, 10 = extremely likely."},
			{"label": "What's the main reason for your score?", "field_type": "paragraph"},
		],
		doctype_name="Q1 NPS Response", accent="green",
		description="A quick pulse check on how our product is doing this quarter.",
		thank_you="Thanks for the feedback - it genuinely shapes what we build next.",
	)
	summary["forms"] += 1
	summary["doctypes"].append(nps.doctype_name)
	for i in range(1040):
		vals, _ = by_label(nps, {
			"How likely are you to recommend us?": random.choices(
				range(0, 11), weights=[1, 1, 1, 2, 2, 4, 5, 8, 12, 14, 10])[0],
			"What's the main reason for your score?": random.choice(
				["", "", "Great product", "Could be faster", "Love the new UI",
				 "Support is excellent", "Pricing is steep"]),
		})
		_insert_record(nps.doctype_name, vals, days_back=random.randint(0, 27))
		if i % 250 == 0:
			frappe.db.commit()
	summary["submissions"] += 1040

	# 3) Support CSAT - weekly (Collection)
	csat = _make_form(
		"support-csat", "Support CSAT - weekly",
		[
			{"label": "How satisfied were you?", "field_type": "rating", "reqd": 1},
			{"label": "How did we do?", "field_type": "single_choice",
				"options": "\n".join(CSAT_REASONS)},
			{"label": "Tell us more", "field_type": "paragraph"},
		],
		doctype_name="Support CSAT Response", accent="blue",
		description="Help us improve support - this takes under a minute.",
	)
	summary["forms"] += 1
	summary["doctypes"].append(csat.doctype_name)
	for i in range(76):
		vals, _ = by_label(csat, {
			"How satisfied were you?": random.choice([0.4, 0.6, 0.8, 0.8, 1.0, 1.0]),
			"How did we do?": random.choice(CSAT_REASONS),
			"Tell us more": random.choice(["", "Thanks!", "Quick and easy", "Still waiting on a fix"]),
		})
		_insert_record(csat.doctype_name, vals, days_back=random.randint(0, 13))
	summary["submissions"] += 76

	# 4) New lead - contact us (Linked -> Contact)
	contact = _make_form(
		"contact-us", "New lead - contact us",
		[
			{"label": "Full name", "field_type": "short_answer", "reqd": 1, "mapped_field": "first_name"},
			{"label": "Work email", "field_type": "email", "reqd": 1, "mapped_field": "email_id"},
			{"label": "Phone", "field_type": "short_answer", "mapped_field": "mobile_no"},
			{"label": "Company", "field_type": "short_answer", "mapped_field": "company_name"},
			{"label": "How can we help?", "field_type": "paragraph"},  # intentionally unmapped
		],
		storage="Linked", target="Contact", accent="violet",
		description="Tell us about your project and we'll get back to you.",
	)
	summary["forms"] += 1
	for i in range(30):
		first = fake.first_name()
		nm = _insert_record("Contact", {
			"first_name": f"{first} {fake.last_name()}",
			"email_id": fake.email(),
			"mobile_no": fake.numerify("+1-###-###-####"),
			"company_name": fake.company(),
		}, days_back=random.randint(0, 27))
		summary["contacts"] += 1

	# 5) Engineering application 2026 (Draft - unpublished, 0 responses)
	_make_form(
		"eng-application-2026", "Engineering application 2026",
		[
			{"label": "Full name", "field_type": "short_answer", "reqd": 1},
			{"label": "Email", "field_type": "email", "reqd": 1},
			{"label": "Which role?", "field_type": "dropdown",
				"options": "Backend\nFrontend\nFull-stack\nSRE"},
			{"label": "Years of experience", "field_type": "number"},
			{"label": "Tell us about yourself", "field_type": "paragraph"},
		],
		accent="violet", publish_it=False,
		description="We're hiring across the engineering org. Applications open soon.",
	)
	summary["forms"] += 1

	# Templates (unpublished blueprints, shown as the Templates gallery). Ready-made
	# blueprints a Forms Manager can start from with one click ("Use template").
	_make_form(
		"tpl-bug-report", "Bug report",
		[
			{"label": "Summary", "field_type": "short_answer", "reqd": 1,
				"help_text": "Describe the bug in a few words"},
			{"label": "Details", "field_type": "paragraph", "reqd": 1,
				"help_text": "Steps to reproduce, what you expected, and what happened"},
			{"label": "Priority", "field_type": "single_choice",
				"options": "Low\nMedium\nHigh\nCritical", "help_text": "How severe is this issue?"},
			{"label": "Area", "field_type": "dropdown", "options": "Web\nMobile\nAPI\nBilling"},
		],
		accent="violet", publish_it=False, is_template=1,
		description="Capture reproducible bug reports with severity so engineering can triage fast.",
		category="Support",
	)
	_make_form(
		"tpl-it-request", "IT request",
		[
			{"label": "Request category", "field_type": "single_choice",
				"options": "Hardware\nSoftware\nAccess\nOther", "reqd": 1,
				"help_text": "Pick the category that best matches your request"},
			{"label": "Priority", "field_type": "single_choice",
				"options": "Low\nMedium\nHigh", "reqd": 1, "help_text": "How urgent is this request?"},
			{"label": "Request details", "field_type": "paragraph", "reqd": 1,
				"help_text": "Please describe your request"},
		],
		accent="blue", publish_it=False, is_template=1,
		description="Streamline IT support requests so teams can track issues and prioritise work.",
		category="Support",
	)
	_make_form(
		"tpl-creative-request", "Creative request",
		[
			{"label": "Your email address", "field_type": "email", "reqd": 1},
			{"label": "Request", "field_type": "short_answer", "reqd": 1,
				"help_text": "Describe the request in a few words"},
			{"label": "Type", "field_type": "dropdown",
				"options": "Design\nCopy\nVideo\nWeb", "reqd": 1,
				"help_text": "Choose what type of request this is"},
			{"label": "Description", "field_type": "paragraph",
				"help_text": "Add more detail about your request"},
		],
		accent="green", publish_it=False, is_template=1,
		description="Organise incoming creative requests and manage design workflows in one place.",
		category="Other",
	)
	_make_form(
		"tpl-event-registration", "Event registration",
		[
			{"label": "First name", "field_type": "short_answer", "reqd": 1},
			{"label": "Last name", "field_type": "short_answer", "reqd": 1},
			{"label": "Your email address", "field_type": "email", "reqd": 1},
			{"label": "Number of people attending", "field_type": "number"},
			{"label": "Dietary restrictions", "field_type": "checkboxes", "options": "\n".join(DIET)},
		],
		accent="blue", publish_it=False, is_template=1,
		description="Manage event registrations, confirmations, and attendee details in one form.",
		category="Events",
	)
	_make_form(
		"tpl-product-feedback", "Product feedback",
		[
			{"label": "Feedback type", "field_type": "single_choice",
				"options": "Bug\nIdea\nPraise\nOther", "reqd": 1,
				"help_text": "Please describe the type of product feedback you have"},
			{"label": "Feedback", "field_type": "paragraph", "reqd": 1,
				"help_text": "Be as specific as possible"},
			{"label": "How satisfied are you?", "field_type": "rating"},
		],
		accent="green", publish_it=False, is_template=1,
		description="Collect suggestions and feedback on the experience to enhance product features.",
		category="Feedback",
	)
	summary["forms"] += 5

	# Seed realistic "opens" so the completion funnel (submitted / opened) isn't 100%.
	# Each published form gets opens slightly above its submission count.
	for form_doc, rate in ((devcon, 0.86), (nps, 0.71), (csat, 0.92)):
		subs = frappe.db.count(form_doc.doctype_name)
		views = round(subs / rate)
		frappe.db.set_value("FF Form", form_doc.name, "views", views, update_modified=False)

	# Share one form with the Forms Manager so the "Shared with me" view has content.
	frappe.share.add("FF Form", devcon.name, manager, read=1, write=1, share=0)

	frappe.db.commit()

	print("\n=== Seed complete ===")
	print(f"Forms created:        {summary['forms']}")
	print(f"DocTypes generated:   {', '.join(summary['doctypes'])}")
	print(f"Submissions inserted: {summary['submissions']}")
	print(f"Contacts (linked):    {summary['contacts']}")
	print(f"Forms Manager login:  {manager} / Espresso-Forms-2026!")
