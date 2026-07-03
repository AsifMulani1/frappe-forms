# Copyright (c) 2026, Acme and contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from forms.tests.test_api import published_form
from forms.www import forms as spa


class TestEmbedFrameAncestors(IntegrationTestCase):
	def test_empty_is_no_ancestors(self):
		self.assertEqual(spa._frame_ancestors(None), [])
		self.assertEqual(spa._frame_ancestors(""), [])
		self.assertEqual(spa._frame_ancestors("  \n \n"), [])

	def test_one_origin_per_line(self):
		self.assertEqual(
			spa._frame_ancestors("https://a.com\nhttps://b.com"),
			["https://a.com", "https://b.com"],
		)

	def test_commas_also_split(self):
		self.assertEqual(
			spa._frame_ancestors("https://a.com, https://b.com"),
			["https://a.com", "https://b.com"],
		)

	def test_pasted_path_is_reduced_to_origin(self):
		self.assertEqual(
			spa._frame_ancestors("https://a.com/path/to/page?x=1"),
			["https://a.com"],
		)

	def test_bare_host_is_kept(self):
		self.assertEqual(spa._frame_ancestors("example.com/foo"), ["example.com"])

	def test_wildcard_subdomain_and_port_kept(self):
		self.assertEqual(
			spa._frame_ancestors("*.example.com\nhttps://app.test:8443"),
			["*.example.com", "https://app.test:8443"],
		)

	def test_directive_injection_token_is_dropped(self):
		# A token that tries to open a second CSP directive (';', spaces, keywords) is not a
		# valid host-source and must be discarded rather than emitted into the header.
		self.assertEqual(spa._frame_ancestors("evil.com; script-src 'unsafe-inline'"), [])
		self.assertEqual(
			spa._frame_ancestors("good.com\nevil.com; default-src *"),
			["good.com"],
		)


class TestEmbedGetContext(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.form = published_form(
			"embed-test",
			[{"label": "Full name", "field_type": "short_answer"}],
			"Embed Test Collection",
		)

	def setUp(self):
		frappe.local.response_headers = frappe.local.response_headers.__class__()

	def _csp(self):
		return frappe.local.response_headers.get("Content-Security-Policy")

	def test_header_set_when_domains_allow_listed(self):
		frappe.db.set_value("FF Form", self.form.name, "embed_allowed_domains", "https://partner.test")
		with patch.object(spa, "_public_form_slug", return_value="embed-test"):
			spa.get_context(frappe._dict())
		self.assertEqual(self._csp(), "frame-ancestors 'self' https://partner.test")

	def test_no_header_without_domains(self):
		frappe.db.set_value("FF Form", self.form.name, "embed_allowed_domains", "")
		with patch.object(spa, "_public_form_slug", return_value="embed-test"):
			spa.get_context(frappe._dict())
		self.assertIsNone(self._csp())

	def test_no_header_off_the_public_form_route(self):
		with patch.object(spa, "_public_form_slug", return_value=None):
			spa.get_context(frappe._dict())
		self.assertIsNone(self._csp())

	def test_no_header_for_draft_form(self):
		frappe.db.set_value("FF Form", self.form.name, "embed_allowed_domains", "https://partner.test")
		frappe.db.set_value("FF Form", self.form.name, "status", "Draft")
		try:
			with patch.object(spa, "_public_form_slug", return_value="embed-test"):
				spa.get_context(frappe._dict())
			self.assertIsNone(self._csp())
		finally:
			frappe.db.set_value("FF Form", self.form.name, "status", "Published")
