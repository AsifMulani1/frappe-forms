# Copyright (c) 2026, Acme and contributors
# See license.txt
#
# Identity encryption: the generated DocType must store a ciphertext blob instead of the plaintext
# email, the guest submit path must accept + store the sealed blob and anonymise the row's owner,
# and re-keying a form that already has responses must be refused. The seal/open crypto itself is
# WebCrypto (browser-only); here the blob is opaque to the server, so a sentinel string stands in.

import base64
import json

import frappe
from frappe.tests import IntegrationTestCase

from forms import api
from forms.admin import crud
from forms.compile import publish

# Opaque to the server (all-zero payload — only the creator's browser could decrypt a real one), but
# the component *lengths* mirror a genuine sealed envelope so it passes _validate_enc_identity:
# epk = 65-byte uncompressed P-256 point (0x04 prefix), iv = 12-byte GCM nonce, ct >= 16-byte tag.
SEALED = json.dumps({
	"v": 1,
	"epk": base64.b64encode(bytes([4]) + bytes(64)).decode(),
	"iv": base64.b64encode(bytes(12)).decode(),
	"ct": base64.b64encode(bytes(32)).decode(),
})


def encrypted_form(slug, doctype_name):
	if frappe.db.exists("FF Form", {"slug": slug}):
		frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": slug}, "name"),
			force=True, ignore_permissions=True)
	doc = frappe.new_doc("FF Form")
	doc.title = slug.replace("-", " ").title()
	doc.slug = slug
	doc.storage_mode = "Collection"
	doc.doctype_name = doctype_name
	doc.collect_email = 1
	doc.allow_edit = 1
	# Key material is generated in the creator's browser; sentinels stand in for the test.
	doc.encrypted = 1
	doc.enc_public_key = "pub-key-b64"
	doc.enc_wrapped_key = "wrapped-key-b64"
	doc.enc_kdf_salt = "salt-b64"
	doc.enc_key_iv = "iv-b64"
	doc.enc_fingerprint = "de:ad:be:ef"
	doc.append("fields", {"label": "Full name", "field_type": "short_answer", "reqd": 1})
	doc.insert(ignore_permissions=True)
	publish(doc.name)
	return doc


class TestEncryption(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.form = encrypted_form("enc-test", "Enc Test Collection")

	def test_publish_swaps_plaintext_email_for_ciphertext_column(self):
		meta = frappe.get_meta("Enc Test Collection")
		self.assertIsNotNone(meta.get_field("enc_identity"))
		self.assertIsNone(meta.get_field("respondent_email"))

	def test_guest_submit_stores_sealed_blob(self):
		frappe.set_user("Guest")
		try:
			res = api.submit("enc-test", json.dumps({"full_name": "Neha Verma"}), enc_identity=SEALED)
		finally:
			frappe.set_user("Administrator")
		doc = frappe.get_doc("Enc Test Collection", res["name"])
		self.assertEqual(doc.full_name, "Neha Verma")
		self.assertEqual(doc.enc_identity, SEALED)

	def test_signed_in_submitter_is_anonymised(self):
		# Even a logged-in respondent must not be unmasked via the row's owner/modified_by metadata.
		res = api.submit("enc-test", json.dumps({"full_name": "Ravi"}), enc_identity=SEALED)
		owner = frappe.db.get_value("Enc Test Collection", res["name"], "owner")
		self.assertEqual(owner, "Guest")

	def test_encrypted_submit_needs_no_plaintext_email(self):
		# collect_email is on, but an encrypted form never validates a plaintext address server-side.
		frappe.set_user("Guest")
		try:
			res = api.submit("enc-test", json.dumps({"full_name": "No Email"}), enc_identity=SEALED)
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(res["name"])

	def test_get_submission_returns_blob_not_plaintext(self):
		res = api.submit("enc-test", json.dumps({"full_name": "Drawer"}), enc_identity=SEALED)
		from forms.admin.responses import get_submission
		out = get_submission("enc-test", res["name"])
		self.assertEqual(out["encrypted"], 1)
		self.assertEqual(out["enc_identity"], SEALED)
		self.assertFalse(any(f["fieldname"] == "respondent_email" for f in out["fields"]))

	def test_rekey_with_responses_refused(self):
		api.submit("enc-test", json.dumps({"full_name": "Locked In"}), enc_identity=SEALED)
		with self.assertRaises(frappe.ValidationError):
			crud.setup_encryption(self.form.name, public_key="NEW-pub", wrapped_key="w",
				kdf_salt="s", key_iv="i", fingerprint="ff")

	def test_arming_encryption_on_published_form_refused(self):
		# Arming after publish can't add the enc_identity column, so sealed identities would be
		# dropped on submit. Encryption must be set up before publishing.
		with self.assertRaises(frappe.ValidationError):
			crud.setup_encryption(self.form.name, public_key="pub", wrapped_key="w",
				kdf_salt="s", key_iv="i", fingerprint="ff")

	def test_edit_reneutralises_modified_by(self):
		# A signed-in respondent edits their response; owner AND modified_by must stay Guest so the
		# save() doesn't re-stamp them onto the row.
		res = api.submit("enc-test", json.dumps({"full_name": "Before"}), enc_identity=SEALED)
		token = res["token"]
		api.submit("enc-test", json.dumps({"full_name": "After"}), token=token, enc_identity=SEALED)
		row = frappe.db.get_value("Enc Test Collection", res["name"],
			["owner", "modified_by", "full_name"], as_dict=True)
		self.assertEqual(row.owner, "Guest")
		self.assertEqual(row.modified_by, "Guest")
		self.assertEqual(row.full_name, "After")

	def test_missing_sealed_identity_refused(self):
		# An encrypted submission with no blob would persist an undecryptable identity — reject it.
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				api.submit("enc-test", json.dumps({"full_name": "No Blob"}))
		finally:
			frappe.set_user("Administrator")

	def test_malformed_sealed_identity_refused(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				api.submit("enc-test", json.dumps({"full_name": "Bad"}),
					enc_identity=json.dumps({"v": 1, "epk": "not base64!!", "iv": "BB", "ct": "CC"}))
		finally:
			frappe.set_user("Administrator")

	def test_wrong_length_envelope_component_refused(self):
		# Valid base64 but wrong decoded length: the browser could never importKey/decrypt this, so a
		# stored response would be permanently unreadable. epk here is 3 bytes, not the required 65.
		bad = json.dumps({"v": 1, "epk": "AAAA",
			"iv": base64.b64encode(bytes(12)).decode(),
			"ct": base64.b64encode(bytes(32)).decode()})
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				api.submit("enc-test", json.dumps({"full_name": "Short EPK"}), enc_identity=bad)
		finally:
			frappe.set_user("Administrator")

	def test_encrypted_edit_writes_no_version_record(self):
		# The leak only manifests in production: frappe.in_test is True during tests, so save()'s
		# default already suppresses versions and masks the bug. Force the production path
		# (in_test=False) and assert an encrypted edit leaves NO Version row — one would capture the
		# signed-in respondent's modified_by. Uses a dedicated form so the shared fixture is untouched.
		form = encrypted_form("enc-ver", "Enc Ver Collection")
		res = api.submit("enc-ver", json.dumps({"full_name": "V1"}), enc_identity=SEALED)
		name, token = res["name"], res["token"]
		saved = frappe.in_test
		frappe.in_test = False
		try:
			api.submit("enc-ver", json.dumps({"full_name": "V2"}), token=token, enc_identity=SEALED)
		finally:
			frappe.in_test = saved
		self.assertEqual(frappe.db.get_value("Enc Ver Collection", name, "full_name"), "V2")
		versions = frappe.get_all("Version",
			filters={"ref_doctype": "Enc Ver Collection", "docname": name})
		self.assertEqual(versions, [], "encrypted edit must not create a Version record")
