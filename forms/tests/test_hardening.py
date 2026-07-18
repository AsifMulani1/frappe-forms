# Copyright (c) 2026, Acme and contributors
# See license.txt
#
# Adversarial / edge-case coverage for the guest write path and the compile engine: malformed
# payloads, XSS boundaries, dedup, orphan-upload reaping, and the publish-time integrity checks
# (conditional-logic graph, save-time regex, child-DocType collisions).

import json

import frappe
from frappe.tests import IntegrationTestCase

from forms import api
from forms.api.uploads import cleanup_orphan_uploads
from forms.compile import publish, validate_conditional_logic
from forms.compile.doctypes import _grid_doctype_name
from forms.tests.test_api import published_form


class TestHardening(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.form = published_form(
			"hard-test",
			[
				{"label": "Full name", "field_type": "short_answer", "reqd": 1},
				{"label": "Diet", "field_type": "checkboxes", "options": "Veg\nVegan"},
			],
			"Hard Test Rec",
		)

	# --- 1. Malformed payloads ------------------------------------------------------------------
	def test_container_rejected_for_scalar_field(self):
		spec = {"field_type": "short_answer", "label": "Name", "reqd": 0, "options": []}
		for bad in ({"x": 1}, ["a", "b"]):
			with self.assertRaises(frappe.ValidationError):
				api._coerce_and_validate(spec, bad)
		# email / number are just as guarded.
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate({"field_type": "email", "label": "E", "reqd": 0, "options": []}, ["a@b.com"])
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate({"field_type": "number", "label": "N", "reqd": 0, "options": []}, {"n": 1})

	def test_non_object_payload_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			api.submit("hard-test", json.dumps(["not", "an", "object"]))
		with self.assertRaises(frappe.ValidationError):
			api.submit("hard-test", json.dumps("a string"))

	# --- 2. XSS in label / help text ------------------------------------------------------------
	def test_xss_label_does_not_reach_fieldname_or_spec(self):
		# A hostile label must never (a) leak markup into the generated column name, or (b) carry a
		# live <script> into the public spec. Frappe sanitises the stored label; we compile a safe
		# snake_case fieldname regardless of what characters the label contained.
		form = published_form("hard-xss", [
			{"label": "Notes <script>alert(1)</script>", "field_type": "short_answer",
				"help_text": '"><img src=x onerror=alert(1)>'},
		], "Hard Xss Rec")
		meta = frappe.get_meta(form.doctype_name)
		user_cols = [df.fieldname for df in meta.fields if df.fieldname not in
			("workflow_state", "edit_token", "respondent_email", "score", "max_score")]
		self.assertTrue(user_cols)
		for fn in user_cols:
			self.assertRegex(fn, r"^[a-z][a-z0-9_]*$")
		spec = api.get_public_form("hard-xss")
		self.assertNotIn("<script", spec["fields"][0]["label"].lower())

	# --- 3. Grid row-removal truncation ---------------------------------------------------------
	def test_grid_answer_for_removed_row_dropped(self):
		# R3 is not a current row -> its answer is silently dropped, R1 kept.
		mc = {"field_type": "mc_grid", "label": "M", "reqd": 0, "options": ["A", "B"], "grid_rows": ["R1", "R2"]}
		self.assertEqual(api._coerce_and_validate(mc, {"R1": "A", "R3": "B"}), {"R1": "A"})

	# --- 4. Dedup guard (guest by email) --------------------------------------------------------
	def test_one_response_per_guest_email(self):
		form = published_form("hard-once-email", [
			{"label": "Comment", "field_type": "short_answer"},
		], "Hard Once Email Rec")
		frappe.db.set_value("FF Form", form.name, {"allow_multiple": 0, "collect_email": 1})
		frappe.db.commit()
		frappe.db.delete("Hard Once Email Rec")
		frappe.db.commit()
		frappe.set_user("Guest")
		try:
			api.submit("hard-once-email", json.dumps({"comment": "hi"}), email="dup@example.com")
			with self.assertRaises(frappe.ValidationError):
				api.submit("hard-once-email", json.dumps({"comment": "again"}), email="dup@example.com")
		finally:
			frappe.set_user("Administrator")

	# --- 5. Orphan-upload reaping ---------------------------------------------------------------
	def test_orphan_upload_cleanup_respects_grace(self):
		def parked_file(name_hint):
			return frappe.get_doc({
				"doctype": "File", "file_name": name_hint, "content": b"x", "is_private": 1,
				"attached_to_doctype": "FF Form", "attached_to_name": self.form.name,
			}).insert(ignore_permissions=True)

		aged = parked_file("aged.txt")
		fresh = parked_file("fresh.txt")
		# Backdate the aged file past the 2h grace window (creation isn't set via set_value).
		frappe.db.sql("update `tabFile` set creation=%s where name=%s",
			(frappe.utils.add_to_date(None, hours=-3), aged.name))
		frappe.db.commit()

		cleanup_orphan_uploads()

		self.assertFalse(frappe.db.exists("File", aged.name))
		self.assertTrue(frappe.db.exists("File", fresh.name))
		frappe.delete_doc("File", fresh.name, ignore_permissions=True, force=True)

	# --- 6. LinkedMode permission-denied --------------------------------------------------------
	def test_linked_guest_cannot_submit_or_load(self):
		if frappe.db.exists("FF Form", {"slug": "hard-linked"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "hard-linked"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Hard Linked"; doc.slug = "hard-linked"; doc.storage_mode = "Linked"
		doc.target_doctype = "ToDo"; doc.apply_doc_perms = 1; doc.collect_email = 0; doc.allow_edit = 1
		doc.append("fields", {"label": "Task", "field_type": "short_answer", "mapped_field": "description"})
		doc.insert(ignore_permissions=True)
		publish(doc.name)
		created = api.submit("hard-linked", json.dumps({"task": "seed"}))["name"]
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.submit("hard-linked", json.dumps({"task": "from guest"}))
			with self.assertRaises(frappe.PermissionError):
				api.get_linked_record("hard-linked", created)
		finally:
			frappe.set_user("Administrator")

	# --- 7. Conditional-logic graph integrity ---------------------------------------------------
	def _form_with_rules(self, rows):
		doc = frappe.new_doc("FF Form")
		doc.title = "Graph Probe"
		for r in rows:
			doc.append("fields", r)
		return doc

	def test_circular_condition_rejected(self):
		doc = self._form_with_rules([
			{"label": "A", "field_type": "single_choice", "options": "x\ny", "field_key": "a",
				"condition_field": "b", "condition_operator": "equals", "condition_value": "x"},
			{"label": "B", "field_type": "single_choice", "options": "x\ny", "field_key": "b",
				"condition_field": "a", "condition_operator": "equals", "condition_value": "x"},
		])
		with self.assertRaises(frappe.ValidationError):
			validate_conditional_logic(doc)

	def test_dangling_condition_rejected(self):
		doc = self._form_with_rules([
			{"label": "A", "field_type": "short_answer", "field_key": "a",
				"condition_field": "ghost", "condition_operator": "equals", "condition_value": "x"},
		])
		with self.assertRaises(frappe.ValidationError):
			validate_conditional_logic(doc)

	def test_valid_condition_chain_passes(self):
		doc = self._form_with_rules([
			{"label": "A", "field_type": "single_choice", "options": "x\ny", "field_key": "a"},
			{"label": "B", "field_type": "short_answer", "field_key": "b",
				"condition_field": "a", "condition_operator": "equals", "condition_value": "x"},
		])
		validate_conditional_logic(doc)  # no raise

	# --- 8. Save-time regex validation ----------------------------------------------------------
	def test_bad_regex_rejected_at_save(self):
		if frappe.db.exists("FF Form", {"slug": "hard-badre"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "hard-badre"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Hard Badre"
		doc.append("fields", {"label": "Code", "field_type": "short_answer",
			"validation_pattern": r"([unclosed"})
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	# --- 9. Child-DocType collision guard -------------------------------------------------------
	def test_grid_child_names_disambiguated(self):
		# Two forms whose (parent + field) grid names share a 61-char prefix must not collapse onto
		# one child DocType (which would bleed one form's rows into the other).
		long_a = "Very Long Organisation Wide Employee Feedback Programme Alpha"
		long_b = "Very Long Organisation Wide Employee Feedback Programme Beta"
		name_a = _grid_doctype_name(frappe._dict(doctype_name=long_a, slug="a"), "ratings_grid")
		name_b = _grid_doctype_name(frappe._dict(doctype_name=long_b, slug="b"), "ratings_grid")
		self.assertLessEqual(len(name_a), 61)
		self.assertLessEqual(len(name_b), 61)
		self.assertNotEqual(name_a, name_b)
