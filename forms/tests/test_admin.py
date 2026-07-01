# Copyright (c) 2026, Acme and contributors
# See license.txt
#
# Authorization tests for the builder endpoints: a Forms Manager may only act on forms they own
# or that are shared with them. These guard against the cross-tenant access holes.

import frappe
from frappe.tests import IntegrationTestCase

from forms import admin


def _manager(email):
	if not frappe.db.exists("User", email):
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = email.split("@")[0]
		user.user_type = "System User"
		user.append("roles", {"role": "Forms Manager"})
		user.insert(ignore_permissions=True)
	elif "Forms Manager" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Forms Manager")
	return email


class TestAdminAuth(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = _manager("forms_alice@example.com")
		cls.bob = _manager("forms_bob@example.com")
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _alice_form(self):
		frappe.set_user(self.alice)
		form = admin.create_form()
		frappe.db.commit()
		return form

	def test_non_owner_cannot_read_form(self):
		form = self._alice_form()
		frappe.set_user(self.bob)
		with self.assertRaises(frappe.PermissionError):
			admin.get_form(form["slug"])

	def test_non_owner_cannot_delete_form(self):
		form = self._alice_form()
		frappe.set_user(self.bob)
		with self.assertRaises(frappe.PermissionError):
			admin.delete_form(form["name"])
		# The form must still exist.
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("FF Form", form["name"]))

	def test_owner_can_read_own_form(self):
		form = self._alice_form()
		frappe.set_user(self.alice)
		self.assertEqual(admin.get_form(form["slug"])["name"], form["name"])

	def test_shared_user_can_read_but_not_delete(self):
		form = self._alice_form()
		frappe.set_user(self.alice)
		admin.share_form(form["name"], self.bob, write=0)
		frappe.db.commit()
		frappe.set_user(self.bob)
		# Read is allowed once shared…
		self.assertEqual(admin.get_form(form["slug"])["name"], form["name"])
		# …but delete (owner-only) is still refused.
		with self.assertRaises(frappe.PermissionError):
			admin.delete_form(form["name"])

	def test_list_forms_scoped_to_owner(self):
		form = self._alice_form()
		frappe.set_user(self.bob)
		names = [f["name"] for f in admin.list_forms("all")]
		self.assertNotIn(form["name"], names, "Bob must not see Alice's form in his list")

	def test_redirect_url_must_be_safe(self):
		form = self._alice_form()
		frappe.set_user(self.alice)
		with self.assertRaises(frappe.ValidationError):
			admin.save_form(form["name"], frappe.as_json({"redirect_url": "javascript:alert(1)"}))

	def test_summary_skips_fields_not_yet_republished(self):
		"""A choice/rating field edited into a published form but not re-published has no live
		column; the summary must skip it instead of 500-ing and blanking the tab."""
		form = self._alice_form()
		frappe.set_user(self.alice)
		base = {
			"title": "Summary mismatch",
			"storage_mode": "Collection",
			"fields": [{"label": "Full Name", "field_type": "short_answer", "reqd": 1}],
		}
		admin.save_form(form["name"], frappe.as_json(base))
		admin.publish_form(form["name"])
		# Add an unpublished single_choice + checkboxes field -> their columns/tables don't exist yet.
		base["fields"].append({"label": "Pick One", "field_type": "single_choice", "options": "A\nB"})
		base["fields"].append({"label": "Pick Many", "field_type": "checkboxes", "options": "X\nY"})
		admin.save_form(form["name"], frappe.as_json(base))
		frappe.db.commit()
		# Draft slug tracks the title, so it changed from the create-time "untitled-form-N".
		form["slug"] = frappe.db.get_value("FF Form", form["name"], "slug")
		# Must not raise; the unmaterialised fields are simply absent from the charts.
		result = admin.responses_summary(form["slug"])
		self.assertEqual(result["charts"], [])
		self.assertEqual(result["total"], 0)


class TestOpenInSheet(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.alice = _manager("forms_alice@example.com")
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _published_form_with_responses(self):
		from forms.compile import resolve_fieldname

		frappe.set_user(self.alice)
		form = admin.create_form()
		base = {
			"title": "Sheet export",
			"storage_mode": "Collection",
			"collect_email": 1,
			"fields": [{"label": "Full Name", "field_type": "short_answer", "reqd": 1}],
		}
		admin.save_form(form["name"], frappe.as_json(base))
		admin.publish_form(form["name"])
		doc = frappe.get_doc("FF Form", form["name"])
		fn = resolve_fieldname(doc.fields[0])
		for i in range(2):
			frappe.get_doc({
				"doctype": doc.doctype_name,
				fn: f"Person {i}",
				"respondent_email": f"person{i}@example.com",
			}).insert(ignore_permissions=True)
		frappe.db.commit()
		# Draft slug tracks the title, so it changed from the create-time "untitled-form-N".
		form["slug"] = doc.slug
		return form

	def test_open_in_sheet_creates_sheet_with_data(self):
		from sheets.api import get_sheet

		form = self._published_form_with_responses()
		frappe.set_user(self.alice)
		res = admin.open_in_sheet(form["slug"])
		name = res["sheet_name"]
		# A real Sheet was created and recorded on the form.
		self.assertTrue(frappe.db.exists("Sheet", name))
		self.assertEqual(res["url"], f"/sheets?id={name}")
		self.assertEqual(frappe.db.get_value("FF Form", form["name"], "sheet_name"), name)
		# The blob round-trips a header row + one row per response.
		data = get_sheet(name)["sheets_data"]
		if isinstance(data, str):
			data = frappe.parse_json(data)
		rows = data["sheet"]["sheets"]["Responses"]["rows"]
		self.assertEqual(rows["0"][:2], ["Response ID", "Email"])
		self.assertIn("Full Name", rows["0"])
		self.assertEqual(len([k for k in rows if k != "0"]), 2)

	def test_open_in_sheet_reuses_same_sheet(self):
		form = self._published_form_with_responses()
		frappe.set_user(self.alice)
		first = admin.open_in_sheet(form["slug"])["sheet_name"]
		second = admin.open_in_sheet(form["slug"])["sheet_name"]
		# Persistent: refreshing exports into the same sheet, never a new one.
		self.assertEqual(first, second)
		self.assertEqual(frappe.db.count("Sheet", {"name": first}), 1)


class TestDuplicate(IntegrationTestCase):
	def test_duplicate_carries_config_and_remaps_conditions(self):
		slug = "api-dup-src"
		if frappe.db.exists("FF Form", {"slug": slug}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": slug}, "name"),
				force=True, ignore_permissions=True)
		src = frappe.new_doc("FF Form")
		src.title = "Api Dup Src"
		src.slug = slug
		src.storage_mode = "Collection"
		src.is_quiz = 1
		src.response_limit = 5
		src.append("fields", {"label": "Has pet", "field_type": "single_choice",
			"options": "Yes\nNo", "field_key": "ctrl"})
		src.append("fields", {"label": "Pet name", "field_type": "short_answer", "field_key": "dep",
			"condition_field": "ctrl", "condition_operator": "equals", "condition_value": "Yes",
			"points": 2, "correct_answer": "Rex"})
		src.insert(ignore_permissions=True)

		dup = admin.duplicate_form(src.name)
		fields = dup["fields"]
		# Form-level settings copied; the duplicate is its own Draft (never a template).
		self.assertEqual(dup["is_quiz"], 1)
		self.assertEqual(dup["response_limit"], 5)
		self.assertEqual(dup["status"], "Draft")
		# Field config copied.
		self.assertEqual(fields[1]["points"], 2)
		self.assertEqual(fields[1]["correct_answer"], "Rex")
		self.assertEqual(fields[1]["condition_value"], "Yes")
		# Keys are regenerated, and the condition points at the COPIED controlling field's new key.
		self.assertNotEqual(fields[0]["field_key"], "ctrl")
		self.assertEqual(fields[1]["condition_field"], fields[0]["field_key"])
