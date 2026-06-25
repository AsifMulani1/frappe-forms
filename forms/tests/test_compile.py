# Copyright (c) 2026, Acme and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from forms import compile as cc


def make_form(slug, fields, storage_mode="Collection", target_doctype=None, doctype_name=None):
	if frappe.db.exists("FF Form", {"slug": slug}):
		frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": slug}, "name"),
			force=True, ignore_permissions=True)
	doc = frappe.new_doc("FF Form")
	doc.title = slug.replace("-", " ").title()
	doc.slug = slug
	doc.storage_mode = storage_mode
	doc.target_doctype = target_doctype
	if doctype_name:
		doc.doctype_name = doctype_name
	for f in fields:
		doc.append("fields", f)
	doc.insert(ignore_permissions=True)
	return doc


class TestCompile(IntegrationTestCase):
	def test_field_type_mapping(self):
		fields = [
			{"label": "Short", "field_type": "short_answer"},
			{"label": "Para", "field_type": "paragraph"},
			{"label": "Mail", "field_type": "email"},
			{"label": "Num", "field_type": "number"},
			{"label": "Single", "field_type": "single_choice", "options": "A\nB\nC"},
			{"label": "Drop", "field_type": "dropdown", "options": "X\nY"},
			{"label": "Date", "field_type": "date"},
			{"label": "Rate", "field_type": "rating"},
			{"label": "Yn", "field_type": "yes_no"},
		]
		form = make_form("map-test", fields)
		dfs = {df["label"]: df for df in cc.build_docfields(form)}
		self.assertEqual(dfs["Short"]["fieldtype"], "Data")
		self.assertEqual(dfs["Para"]["fieldtype"], "Small Text")
		self.assertEqual(dfs["Mail"]["fieldtype"], "Data")
		self.assertEqual(dfs["Num"]["fieldtype"], "Int")
		self.assertEqual(dfs["Single"]["fieldtype"], "Select")
		self.assertEqual(dfs["Single"]["options"], "A\nB\nC")
		self.assertEqual(dfs["Drop"]["fieldtype"], "Select")
		self.assertEqual(dfs["Date"]["fieldtype"], "Date")
		self.assertEqual(dfs["Rate"]["fieldtype"], "Rating")
		self.assertEqual(dfs["Yn"]["fieldtype"], "Check")

	def test_new_field_type_mapping(self):
		fields = [
			{"label": "Phone", "field_type": "phone"},
			{"label": "Time", "field_type": "time"},
			{"label": "Address", "field_type": "address"},
			{"label": "File", "field_type": "file_upload"},
			{"label": "Sign", "field_type": "signature"},
		]
		form = make_form("new-map-test", fields)
		dfs = {df["label"]: df for df in cc.build_docfields(form)}
		self.assertEqual(dfs["Phone"]["fieldtype"], "Data")
		self.assertEqual(dfs["Time"]["fieldtype"], "Time")
		self.assertEqual(dfs["Address"]["fieldtype"], "Small Text")
		self.assertEqual(dfs["File"]["fieldtype"], "Attach")
		self.assertEqual(dfs["Sign"]["fieldtype"], "Signature")

	def test_section_header_omitted(self):
		form = make_form("layout-test", [
			{"label": "Your details", "field_type": "section_header"},
			{"label": "Name", "field_type": "short_answer"},
		])
		labels = [df["label"] for df in cc.build_docfields(form)]
		self.assertNotIn("Your details", labels)
		self.assertIn("Name", labels)

	def test_email_gets_options_email(self):
		form = make_form("email-test", [{"label": "Email", "field_type": "email"}])
		df = cc.build_docfields(form)[0]
		self.assertEqual(df["fieldtype"], "Data")
		self.assertEqual(df["options"], "Email")

	def test_required_gets_reqd(self):
		form = make_form("reqd-test", [{"label": "Name", "field_type": "short_answer", "reqd": 1}])
		df = cc.build_docfields(form)[0]
		self.assertEqual(df.get("reqd"), 1)

	def test_help_becomes_description(self):
		form = make_form("help-test", [{"label": "Name", "field_type": "short_answer", "help_text": "Your name"}])
		df = cc.build_docfields(form)[0]
		self.assertEqual(df["description"], "Your name")

	def test_fieldnames_freeze(self):
		form = make_form("freeze-test", [{"label": "Full Name", "field_type": "short_answer"}])
		cc.freeze_fieldnames(form)
		form.reload()
		self.assertEqual(form.fields[0].fieldname, "full_name")
		# Relabel; the frozen fieldname must not change.
		form.fields[0].label = "Renamed"
		cc.freeze_fieldnames(form)
		form.reload()
		self.assertEqual(form.fields[0].fieldname, "full_name")

	def test_checkboxes_generate_child_doctype(self):
		form = make_form("cb-test", [
			{"label": "Diet", "field_type": "checkboxes", "options": "Veg\nVegan"},
		], doctype_name="CB Test Collection")
		cc.publish(form.name)
		form.reload()
		self.assertTrue(frappe.db.exists("DocType", form.doctype_name))
		meta = frappe.get_meta(form.doctype_name)
		diet = meta.get_field("diet")
		self.assertEqual(diet.fieldtype, "Table MultiSelect")
		self.assertTrue(frappe.db.exists("DocType", diet.options))
		child = frappe.get_meta(diet.options)
		self.assertTrue(child.istable)
		self.assertTrue(child.get_field("value"))

	def test_publish_is_additive(self):
		form = make_form("additive-test", [
			{"label": "Keep", "field_type": "short_answer"},
			{"label": "Remove Me", "field_type": "short_answer"},
		], doctype_name="Additive Test Collection")
		cc.publish(form.name)
		form.reload()
		dt_name = form.doctype_name
		self.assertTrue(frappe.get_meta(dt_name).get_field("remove_me"))

		# Drop the second field and re-publish.
		form.fields = [form.fields[0]]
		form.save(ignore_permissions=True)
		cc.publish(form.name)

		frappe.clear_cache(doctype=dt_name)
		meta = frappe.get_meta(dt_name)
		removed = meta.get_field("remove_me")
		# Never dropped - hidden + read_only instead.
		self.assertIsNotNone(removed, "removed field must NOT be dropped")
		self.assertTrue(removed.hidden)
		self.assertTrue(removed.read_only)
