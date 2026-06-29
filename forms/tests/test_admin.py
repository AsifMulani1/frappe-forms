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
		# Must not raise; the unmaterialised fields are simply absent from the charts.
		result = admin.responses_summary(form["slug"])
		self.assertEqual(result["charts"], [])
		self.assertEqual(result["total"], 0)
