# Copyright (c) 2026, Acme and contributors
# See license.txt

import json
from unittest.mock import patch

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
	doc.collect_email = 0  # email capture is exercised by its own test
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

	def test_linear_scale_validation(self):
		spec = {"field_type": "linear_scale", "label": "NPS", "reqd": 0, "options": [],
			"scale_min": 1, "scale_max": 5}
		self.assertEqual(api._coerce_and_validate(spec, "3"), 3)
		self.assertEqual(api._coerce_and_validate(spec, 5), 5)
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec, 6)
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec, 0)

	def test_number_bounds(self):
		spec = {"field_type": "number", "label": "Age", "reqd": 0, "options": [],
			"min_value": "18", "max_value": "60"}
		self.assertEqual(api._coerce_and_validate(spec, "30"), 30)
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec, "17")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec, "61")

	def test_text_max_length_and_pattern(self):
		spec = {"field_type": "short_answer", "label": "Code", "reqd": 0, "options": [],
			"max_length": 4}
		self.assertEqual(api._coerce_and_validate(spec, "abcd"), "abcd")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec, "abcde")
		pat = {"field_type": "short_answer", "label": "Zip", "reqd": 0, "options": [],
			"validation_pattern": r"\d{5}"}
		self.assertEqual(api._coerce_and_validate(pat, "12345"), "12345")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(pat, "abc")

	def test_other_write_in_accepted(self):
		# With has_other, a value outside the option list is allowed (free text).
		spec = {"field_type": "single_choice", "label": "Source", "reqd": 0,
			"options": ["A", "B"], "has_other": 1}
		self.assertEqual(api._coerce_and_validate(spec, "Word of mouth"), "Word of mouth")
		# Without has_other, the same value is rejected.
		strict = {**spec, "has_other": 0}
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(strict, "Word of mouth")

	def test_grid_validation(self):
		mc = {"field_type": "mc_grid", "label": "M", "reqd": 0, "options": ["A", "B"], "grid_rows": ["R1", "R2"]}
		self.assertEqual(api._coerce_and_validate(mc, {"R1": "A", "R2": "B"}), {"R1": "A", "R2": "B"})
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(mc, {"R1": "Z"})  # Z is not a column
		cb = {"field_type": "checkbox_grid", "label": "M", "reqd": 0, "options": ["A", "B"], "grid_rows": ["R1"]}
		self.assertEqual(api._coerce_and_validate(cb, {"R1": ["A", "B"]}), {"R1": ["A", "B"]})
		req = {"field_type": "mc_grid", "label": "M", "reqd": 1, "options": ["A"], "grid_rows": ["R1"]}
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(req, {})  # required grid with no answers

	def test_edit_after_submit(self):
		if frappe.db.exists("FF Form", {"slug": "api-edit"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "api-edit"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Api Edit"; doc.slug = "api-edit"; doc.storage_mode = "Collection"
		doc.doctype_name = "Api Edit Rec"; doc.allow_edit = 1
		doc.append("fields", {"label": "Comment", "field_type": "short_answer"})
		doc.insert(ignore_permissions=True)
		publish(doc.name)
		# submit() commits, so prior runs leave rows behind - start from a clean table.
		frappe.db.delete("Api Edit Rec")
		frappe.db.commit()

		res = api.submit("api-edit", json.dumps({"comment": "First"}))
		self.assertIn("token", res)
		token = res["token"]
		# Editing with the token updates in place - no second record.
		api.submit("api-edit", json.dumps({"comment": "Second"}), token=token)
		self.assertEqual(frappe.db.count("Api Edit Rec"), 1)
		loaded = api.get_submission("api-edit", token)
		self.assertEqual(loaded["answers"]["comment"], "Second")

	def test_collect_email_required_and_stored(self):
		if frappe.db.exists("FF Form", {"slug": "api-email"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "api-email"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Api Email"; doc.slug = "api-email"; doc.storage_mode = "Collection"
		doc.doctype_name = "Api Email Rec"; doc.collect_email = 1
		doc.append("fields", {"label": "Comment", "field_type": "short_answer"})
		doc.insert(ignore_permissions=True)
		publish(doc.name)

		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				api.submit("api-email", json.dumps({"comment": "hi"}))  # no email
			res = api.submit("api-email", json.dumps({"comment": "hi"}), email="a@b.com")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.get_doc("Api Email Rec", res["name"]).respondent_email, "a@b.com")

	def test_apply_doc_perms_linked(self):
		if frappe.db.exists("FF Form", {"slug": "api-perm"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "api-perm"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Api Perm"; doc.slug = "api-perm"; doc.storage_mode = "Linked"
		doc.target_doctype = "ToDo"; doc.apply_doc_perms = 1; doc.collect_email = 0
		doc.append("fields", {"label": "Task", "field_type": "short_answer", "mapped_field": "description"})
		doc.insert(ignore_permissions=True)
		publish(doc.name)

		# A guest cannot submit a permission-enforcing form.
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.submit("api-perm", json.dumps({"task": "from guest"}))
		finally:
			frappe.set_user("Administrator")

		# An authorised user can, and becomes the record owner.
		res = api.submit("api-perm", json.dumps({"task": "from admin"}))
		todo = frappe.get_doc("ToDo", res["name"])
		self.assertEqual(todo.description, "from admin")
		self.assertEqual(todo.owner, "Administrator")

	def test_linked_edit_existing(self):
		if frappe.db.exists("FF Form", {"slug": "api-linkedit"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "api-linkedit"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Api Linkedit"; doc.slug = "api-linkedit"; doc.storage_mode = "Linked"
		doc.target_doctype = "ToDo"; doc.allow_edit = 1; doc.collect_email = 0
		doc.append("fields", {"label": "Task", "field_type": "short_answer", "mapped_field": "description"})
		doc.insert(ignore_permissions=True)
		publish(doc.name)

		res = api.submit("api-linkedit", json.dumps({"task": "v1"}))
		name = res["name"]
		# Prefill loads the mapped value back.
		self.assertEqual(api.get_linked_record("api-linkedit", name)["answers"]["task"], "v1")
		# Submitting with the record name updates in place.
		api.submit("api-linkedit", json.dumps({"task": "v2"}), record=name)
		self.assertEqual(frappe.get_doc("ToDo", name).description, "v2")
		# A guest cannot load a record for editing.
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.get_linked_record("api-linkedit", name)
		finally:
			frappe.set_user("Administrator")

	def test_my_submissions_list_and_delete(self):
		if frappe.db.exists("FF Form", {"slug": "api-mysubs"}):
			frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": "api-mysubs"}, "name"),
				force=True, ignore_permissions=True)
		doc = frappe.new_doc("FF Form")
		doc.title = "Api Mysubs"; doc.slug = "api-mysubs"; doc.storage_mode = "Collection"
		doc.doctype_name = "Api Mysubs Rec"; doc.collect_email = 0
		doc.show_my_submissions = 1; doc.allow_delete = 1; doc.allow_edit = 1
		doc.append("fields", {"label": "Comment", "field_type": "short_answer"})
		doc.insert(ignore_permissions=True)
		publish(doc.name)
		frappe.db.delete("Api Mysubs Rec")
		frappe.db.commit()

		res = api.submit("api-mysubs", json.dumps({"comment": "mine"}))  # owner = Administrator
		lst = api.list_my_submissions("api-mysubs")
		self.assertEqual(len(lst["rows"]), 1)
		self.assertEqual(lst["rows"][0]["label"], "mine")
		self.assertTrue(lst["rows"][0]["edit_param"].startswith("edit="))

		api.delete_my_submission("api-mysubs", res["name"])
		self.assertFalse(frappe.db.exists("Api Mysubs Rec", res["name"]))

		# A guest cannot list submissions.
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.list_my_submissions("api-mysubs")
		finally:
			frappe.set_user("Administrator")

	def test_section_header_not_stored(self):
		form = published_form("api-sec-test", [
			{"label": "Intro", "field_type": "section_header"},
			{"label": "Comment", "field_type": "paragraph"},
		], "Api Sec Rec")
		res = api.submit("api-sec-test", json.dumps({}))
		self.assertTrue(frappe.db.exists(form.doctype_name, res["name"]))

	def test_honeypot_rejects_and_writes_nothing(self):
		# A tripped honeypot is rejected before any record is written.
		before = frappe.db.count("Api Test Collection")
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				api.submit("api-test", json.dumps({
					"full_name": "Bot", "email": "bot@example.com",
				}), hp="i am a bot")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Api Test Collection"), before)

	def test_email_receipt_sent(self):
		form = published_form("api-receipt", [
			{"label": "Comment", "field_type": "short_answer"},
		], "Api Receipt Rec")
		# publish() re-saves the doc server-side, so set flags via the DB rather than the stale ref.
		frappe.db.set_value("FF Form", form.name, {"collect_email": 1, "email_receipt": 1})
		frappe.db.commit()
		with patch("frappe.sendmail") as sendmail:
			api.submit("api-receipt", json.dumps({"comment": "hi"}), email="r@example.com")
		self.assertTrue(sendmail.called)
		self.assertEqual(sendmail.call_args.kwargs.get("recipients"), ["r@example.com"])

	def test_no_receipt_when_flag_off(self):
		# Default form (email_receipt = 0) must not send anything.
		with patch("frappe.sendmail") as sendmail:
			api.submit("api-test", json.dumps({"full_name": "X", "email": "x@example.com"}))
		self.assertFalse(sendmail.called)

	def test_file_upload_attached_to_record(self):
		published_form("api-file", [
			{"label": "Resume", "field_type": "file_upload"},
		], "Api File Rec")
		uploaded = frappe.get_doc({
			"doctype": "File", "file_name": "r.txt", "content": b"resume", "is_private": 1,
		}).insert(ignore_permissions=True)
		res = api.submit("api-file", json.dumps({"resume": uploaded.file_url}))
		attached = frappe.db.get_value("File", uploaded.name,
			["attached_to_doctype", "attached_to_name"], as_dict=True)
		self.assertEqual(attached.attached_to_doctype, "Api File Rec")
		self.assertEqual(attached.attached_to_name, res["name"])

	def test_spec_exposes_shuffle_and_progress_flags(self):
		# Shuffle/progress are presentation flags the respondent SPA reads from the spec.
		form = published_form("api-flags", [
			{"label": "Pick", "field_type": "single_choice", "options": "A\nB", "shuffle_options": 1},
		], "Api Flags Rec")
		frappe.db.set_value("FF Form", form.name, {"shuffle_questions": 1, "show_progress": 0})
		frappe.db.commit()
		spec = api.get_public_form("api-flags")
		self.assertEqual(spec["shuffle_questions"], 1)
		self.assertEqual(spec["show_progress"], 0)
		self.assertEqual(spec["fields"][0]["shuffle_options"], 1)

	def test_date_validation(self):
		spec = {"field_type": "date", "label": "DOB", "reqd": 0, "options": []}
		self.assertEqual(api._coerce_and_validate(spec, "2026-01-15"), "2026-01-15")
		with self.assertRaises(frappe.ValidationError):
			api._coerce_and_validate(spec, "not-a-date")

	def test_conditional_logic_hides_and_shows(self):
		published_form("api-cond", [
			{"label": "Has pet", "field_type": "single_choice", "options": "Yes\nNo", "field_key": "haspet"},
			{"label": "Pet name", "field_type": "short_answer", "reqd": 1, "field_key": "petname",
				"condition_field": "haspet", "condition_operator": "equals", "condition_value": "Yes"},
		], "Api Cond Rec")
		frappe.db.delete("Api Cond Rec")
		frappe.db.commit()
		# Condition not met -> the required "Pet name" is hidden, so its absence can't block the submit.
		res = api.submit("api-cond", json.dumps({"has_pet": "No"}))
		self.assertFalse(frappe.get_doc("Api Cond Rec", res["name"]).pet_name)
		# Condition met -> the field is now required.
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-cond", json.dumps({"has_pet": "Yes"}))
		# Condition met with a value -> stored.
		res2 = api.submit("api-cond", json.dumps({"has_pet": "Yes", "pet_name": "Rex"}))
		self.assertEqual(frappe.get_doc("Api Cond Rec", res2["name"]).pet_name, "Rex")

	def test_quiz_grading_and_storage(self):
		form = published_form("api-quiz", [
			{"label": "2+2", "field_type": "single_choice", "options": "3\n4\n5", "points": 2, "correct_answer": "4"},
			{"label": "Sky color", "field_type": "short_answer", "points": 1, "correct_answer": "blue"},
		], "Api Quiz Rec")
		frappe.db.set_value("FF Form", form.name, "is_quiz", 1)
		frappe.db.commit()
		frappe.db.delete("Api Quiz Rec")
		frappe.db.commit()
		res = api.submit("api-quiz", json.dumps({"2_2": "4", "sky_color": "blue"}))
		self.assertEqual(res["score"], 3)
		self.assertEqual(res["max_score"], 3)
		self.assertEqual(frappe.get_doc("Api Quiz Rec", res["name"]).score, 3)
		partial = api.submit("api-quiz", json.dumps({"2_2": "3", "sky_color": "blue"}))
		self.assertEqual(partial["score"], 1)

	def test_correct_answer_not_in_public_spec(self):
		published_form("api-secret", [
			{"label": "Q", "field_type": "single_choice", "options": "A\nB", "points": 1, "correct_answer": "A"},
		], "Api Secret Rec")
		spec = api.get_public_form("api-secret")
		self.assertNotIn("correct_answer", spec["fields"][0])  # answer key must never reach respondents
		self.assertIn("points", spec["fields"][0])

	def test_response_limit_blocks(self):
		form = published_form("api-limit", [{"label": "X", "field_type": "short_answer"}], "Api Limit Rec")
		frappe.db.set_value("FF Form", form.name, "response_limit", 1)
		frappe.db.commit()
		frappe.db.delete("Api Limit Rec")
		frappe.db.commit()
		api.submit("api-limit", json.dumps({"x": "one"}))
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-limit", json.dumps({"x": "two"}))

	def test_closed_window_blocks(self):
		form = published_form("api-closed", [{"label": "X", "field_type": "short_answer"}], "Api Closed Rec")
		frappe.db.set_value("FF Form", form.name, "closes_on", frappe.utils.add_to_date(None, days=-1))
		frappe.db.commit()
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-closed", json.dumps({"x": "late"}))

	def test_one_response_per_user(self):
		form = published_form("api-once", [{"label": "X", "field_type": "short_answer"}], "Api Once Rec")
		frappe.db.set_value("FF Form", form.name, "allow_multiple", 0)
		frappe.db.commit()
		frappe.db.delete("Api Once Rec")
		frappe.db.commit()
		api.submit("api-once", json.dumps({"x": "first"}))  # owner = Administrator
		with self.assertRaises(frappe.ValidationError):
			api.submit("api-once", json.dumps({"x": "second"}))

	def test_admin_notification_sent(self):
		form = published_form("api-notify", [{"label": "X", "field_type": "short_answer"}], "Api Notify Rec")
		frappe.db.set_value("FF Form", form.name,
			{"notify_on_response": 1, "notify_email": "owner@example.com"})
		frappe.db.commit()
		with patch("frappe.sendmail") as sendmail:
			api.submit("api-notify", json.dumps({"x": "hi"}))
		self.assertTrue(sendmail.called)
		self.assertEqual(sendmail.call_args.kwargs.get("recipients"), ["owner@example.com"])
