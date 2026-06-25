# Copyright (c) 2026, Acme and contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from forms import api
from forms.compile import publish


def published_form(slug, fields, doctype_name):
	if frappe.db.exists("FF Form", {"slug": slug}):
		frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": slug}, "name"),
			force=True, ignore_permissions=True)
	doc = frappe.new_doc("FF Form")
	doc.title = slug.replace("-", " ").title()
	doc.slug = slug
	doc.storage_mode = "Collection"
	doc.doctype_name = doctype_name
	for f in fields:
		doc.append("fields", f)
	doc.insert(ignore_permissions=True)
	publish(doc.name)
	return doc


class TestApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.form = published_form(
			"api-test",
			[
				{"label": "Full name", "field_type": "short_answer", "reqd": 1},
				{"label": "Email", "field_type": "email", "reqd": 1},
				{"label": "Track", "field_type": "single_choice", "options": "A\nB"},
				{"label": "Diet", "field_type": "checkboxes", "options": "Veg\nVegan"},
			],
			"Api Test Collection",
		)

	def test_get_public_form_published_only(self):
		spec = api.get_public_form("api-test")
		self.assertEqual(spec["title"], "Api Test")
		self.assertEqual(len(spec["fields"]), 4)

	def test_guest_submit_creates_record(self):
		frappe.set_user("Guest")
		try:
			res = api.submit("api-test", json.dumps({
				"full_name": "Neha Verma",
				"email": "neha@example.com",
				"track": "A",
				"diet": ["Veg"],
			}))
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(res["name"])
		doc = frappe.get_doc("Api Test Collection", res["name"])
		self.assertEqual(doc.full_name, "Neha Verma")
		self.assertEqual(doc.email, "neha@example.com")
		self.assertEqual(len(doc.diet), 1)
		self.assertEqual(doc.diet[0].value, "Veg")
		self.assertEqual(doc.workflow_state, "Pending")

	def test_missing_required_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-test", json.dumps({"email": "x@example.com"}))

	def test_bad_email_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-test", json.dumps({"full_name": "X", "email": "not-an-email"}))

	def test_option_outside_choices_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-test", json.dumps({
				"full_name": "X", "email": "x@example.com", "track": "Z",
			}))

	def test_draft_form_404(self):
		with self.assertRaises(frappe.DoesNotExistError):
			api.get_public_form("no-such-slug")

	def test_new_type_validation(self):
		def spec(ft):
			return {"field_type": ft, "label": "X", "reqd": 0, "options": []}

		self.assertEqual(api._coerce_and_validate(spec("phone"), "+1 555-0100"), "+1 555-0100")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec("phone"), "abc")
		self.assertEqual(api._coerce_and_validate(spec("time"), "09:30"), "09:30:00")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec("time"), "99:99")
		self.assertEqual(api._coerce_and_validate(spec("address"), "1 Main St"), "1 Main St")
		self.assertEqual(api._coerce_and_validate(spec("file_upload"), "/private/files/x.pdf"), "/private/files/x.pdf")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec("file_upload"), "http://evil/x")
		self.assertTrue(api._coerce_and_validate(spec("signature"), "data:image/png;base64,AAAA").startswith("data:image/"))
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec("signature"), "notasig")

	def test_section_header_not_stored(self):
		form = published_form("api-sec-test", [
			{"label": "Intro", "field_type": "section_header"},
			{"label": "Comment", "field_type": "paragraph"},
		], "Api Sec Rec")
		res = api.submit("api-sec-test", json.dumps({}))
		self.assertTrue(frappe.db.exists(form.doctype_name, res["name"]))
