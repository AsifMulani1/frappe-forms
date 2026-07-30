# Copyright (c) 2026, Acme and contributors
# See license.txt
#
# Identity encryption: the generated DocType must store a ciphertext blob instead of the plaintext
# email, the guest submit path must accept + store the sealed blob and anonymise the row's owner
# (parent AND child rows), receipts must not leak the address, and the encrypted flag is frozen at
# publish and confined to Collection forms. The seal/open crypto itself is WebCrypto (browser-only);
# here the blob is opaque to the server, so a length-shaped sentinel string stands in.

import base64
import hashlib
import json
from unittest.mock import patch

import frappe
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from frappe.tests import IntegrationTestCase

from forms import api
from forms.admin import crud
from forms.compile import publish

NON_OWNER = "enc-nonowner@example.com"  # a System Manager who is NOT the form's creator


def _real_epk() -> bytes:
	"""A genuine 65-byte uncompressed P-256 public point — what a real browser ephemeral key yields
	and what _validate_enc_identity's on-curve check requires."""
	priv = ec.generate_private_key(ec.SECP256R1())
	return priv.public_key().public_bytes(
		serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _sealed(ct_len: int = 32) -> str:
	"""A length-shaped sentinel envelope: real on-curve epk, 12-byte iv, ct >= 16 bytes. Opaque to the
	server (unopenable without the private key) but passes _validate_enc_identity."""
	return json.dumps({
		"v": 1,
		"epk": base64.b64encode(_real_epk()).decode(),
		"iv": base64.b64encode(bytes(12)).decode(),
		"ct": base64.b64encode(bytes(ct_len)).decode(),
	})


def _keypair_material():
	"""A real P-256 public key (base64) and its crypto.js-style fingerprint, for setup_encryption."""
	priv = ec.generate_private_key(ec.SECP256R1())
	raw = priv.public_key().public_bytes(
		serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
	fp = ":".join(f"{b:02x}" for b in hashlib.sha256(raw).digest()[:8])
	return base64.b64encode(raw).decode(), fp


SEALED = _sealed()
SEALED2 = _sealed(ct_len=48)  # a distinct, also-valid blob (for edit-persists-new-blob)


def encrypted_form(slug, doctype_name, fields=None):
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
	for f in (fields or [{"label": "Full name", "field_type": "short_answer", "reqd": 1}]):
		doc.append("fields", f)
	doc.insert(ignore_permissions=True)
	publish(doc.name)
	return doc


def draft_collection_form(slug):
	"""A minimal unpublished Collection form owned by the current user (for endpoint tests)."""
	if frappe.db.exists("FF Form", {"slug": slug}):
		frappe.delete_doc("FF Form", frappe.db.get_value("FF Form", {"slug": slug}, "name"),
			force=True, ignore_permissions=True)
	doc = frappe.new_doc("FF Form")
	doc.title = slug.replace("-", " ").title()
	doc.slug = slug
	doc.storage_mode = "Collection"
	doc.append("fields", {"label": "Full name", "field_type": "short_answer", "reqd": 1})
	doc.insert(ignore_permissions=True)
	return doc


class TestEncryption(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.form = encrypted_form("enc-test", "Enc Test Collection")
		# A second user who is a System Manager but NOT the form's creator — used to prove that even
		# the highest-privilege role can't arm/disable encryption or fetch the wrapped key.
		if not frappe.db.exists("User", NON_OWNER):
			u = frappe.new_doc("User")
			u.email = NON_OWNER
			u.first_name = "Non Owner"
			u.append("roles", {"role": "System Manager"})
			u.append("roles", {"role": "Forms Manager"})
			u.insert(ignore_permissions=True)

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

	def test_arming_encryption_on_published_form_refused(self):
		# Arming after publish can't add the enc_identity column, so sealed identities would be
		# dropped on submit. Encryption must be set up before publishing. (This also subsumes the old
		# "re-key with responses" case: responses only exist for published forms, and arming is now
		# blocked outright once published.)
		with self.assertRaisesRegex(frappe.ValidationError, "before the form is published"):
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

	def test_off_curve_epk_refused(self):
		# 65 bytes with the 0x04 prefix but NOT a real P-256 point (the (0,0) "point"): the browser's
		# importKey() rejects it, so the sealed identity could never be opened. Must be refused here.
		off_curve = base64.b64encode(bytes([4]) + bytes(64)).decode()
		bad = json.dumps({"v": 1, "epk": off_curve,
			"iv": base64.b64encode(bytes(12)).decode(),
			"ct": base64.b64encode(bytes(32)).decode()})
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				api.submit("enc-test", json.dumps({"full_name": "Off Curve"}), enc_identity=bad)
		finally:
			frappe.set_user("Administrator")

	def test_encrypted_edit_writes_no_version_record(self):
		# The leak only manifests in production: frappe.in_test is True during tests, so save()'s
		# default already suppresses versions and masks the bug. Force the production path
		# (in_test=False) and assert an encrypted edit leaves NO Version row — one would capture the
		# signed-in respondent's modified_by. Uses a dedicated form so the shared fixture is untouched.
		encrypted_form("enc-ver", "Enc Ver Collection")
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

	def test_child_table_rows_are_neutralised(self):
		# A signed-in respondent's identity is stamped onto child-table rows (checkbox answers) too,
		# not just the parent — those must be scrubbed to Guest, or a child→parent join deanonymises
		# them despite the sealed blob.
		encrypted_form("enc-child", "Enc Child Collection", fields=[
			{"label": "Full name", "field_type": "short_answer", "reqd": 1},
			{"label": "Toppings", "field_type": "checkboxes", "options": "Cheese\nOlives"},
		])
		res = api.submit("enc-child",
			json.dumps({"full_name": "Alice", "toppings": ["Cheese", "Olives"]}), enc_identity=SEALED)
		doc = frappe.get_doc("Enc Child Collection", res["name"])
		self.assertEqual(frappe.db.get_value("Enc Child Collection", doc.name, "owner"), "Guest")
		children = doc.get_all_children()
		self.assertTrue(children, "expected checkbox child rows to exist")
		for c in children:
			row = frappe.db.get_value(c.doctype, c.name, ["owner", "modified_by"], as_dict=True)
			self.assertEqual(row.owner, "Guest")
			self.assertEqual(row.modified_by, "Guest")

	def test_attach_file_neutralises_owner_when_encrypted(self):
		# A signed-in respondent's upload keeps File.owner = their user; on encrypted forms that must
		# be scrubbed so the File row (joined via attached_to_name) doesn't unmask them.
		from forms.api.uploads import _attach_file
		f = frappe.get_doc({"doctype": "File", "file_name": "enc-test.txt",
			"content": "hi", "is_private": 1}).insert(ignore_permissions=True)
		self.assertNotEqual(f.owner, "Guest")  # created as the signed-in test user
		_attach_file(f.file_url, "Enc Test Collection", "dummy", neutralise_owner=True)
		self.assertEqual(frappe.db.get_value("File", f.name, "owner"), "Guest")

	def test_receipt_skipped_for_encrypted_form(self):
		# The receipt recipient falls back to the signed-in user's real email; sending it would persist
		# the plaintext address in the Email Queue. It must be skipped on encrypted forms.
		with patch("forms.api.submit._maybe_send_receipt") as receipt:
			api.submit("enc-test", json.dumps({"full_name": "No Receipt"}), enc_identity=SEALED)
		receipt.assert_not_called()

	def test_metadata_only_edit_preserves_stored_identity(self):
		# Editing without re-sending a blob must not wipe the identity already on the row.
		res = api.submit("enc-test", json.dumps({"full_name": "Keep"}), enc_identity=SEALED)
		api.submit("enc-test", json.dumps({"full_name": "Keep edited"}), token=res["token"])
		self.assertEqual(frappe.db.get_value("Enc Test Collection", res["name"], "enc_identity"), SEALED)

	def test_edit_with_new_blob_persists_it(self):
		res = api.submit("enc-test", json.dumps({"full_name": "Reseal"}), enc_identity=SEALED)
		api.submit("enc-test", json.dumps({"full_name": "Reseal"}), token=res["token"], enc_identity=SEALED2)
		self.assertEqual(frappe.db.get_value("Enc Test Collection", res["name"], "enc_identity"), SEALED2)

	def test_oversized_blob_refused(self):
		big = json.dumps({"v": 1, "epk": base64.b64encode(_real_epk()).decode(),
			"iv": base64.b64encode(bytes(12)).decode(),
			"ct": base64.b64encode(b"x" * 9000).decode()})  # > ENC_IDENTITY_MAX_BYTES (8 KiB)
		frappe.set_user("Guest")
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "too large"):
				api.submit("enc-test", json.dumps({"full_name": "Big"}), enc_identity=big)
		finally:
			frappe.set_user("Administrator")

	def test_encryption_frozen_after_publish(self):
		# The freeze lives in validate(), not just the endpoints — a direct save flipping the flag on a
		# published form must be refused (else a re-publish could strip/duplicate the identity column).
		form = frappe.get_doc("FF Form", self.form.name)
		form.encrypted = 0
		with self.assertRaisesRegex(frappe.ValidationError, "frozen once a form is published"):
			form.save(ignore_permissions=True)

	def test_guard_requires_full_key_envelope(self):
		# encrypted=1 with only a public key (no wrapped key) would let respondents seal identities the
		# creator can never unlock — the schema guard must reject the partial state.
		doc = draft_collection_form("enc-partial")
		doc.encrypted = 1
		doc.enc_public_key = "pub-only"
		with self.assertRaisesRegex(frappe.ValidationError, "key material"):
			doc.save(ignore_permissions=True)

	def test_setup_encryption_rejects_linked_form(self):
		doc = frappe.new_doc("FF Form")
		doc.title = "Enc Linked"
		doc.slug = "enc-linked"
		doc.storage_mode = "Linked"
		doc.insert(ignore_permissions=True)
		pub, fp = _keypair_material()
		with self.assertRaisesRegex(frappe.ValidationError, "Collection"):
			crud.setup_encryption(doc.name, public_key=pub, wrapped_key="w",
				kdf_salt="s", key_iv="i", fingerprint=fp)

	def test_setup_encryption_verifies_fingerprint(self):
		doc = draft_collection_form("enc-fp")
		pub, fp = _keypair_material()
		# Wrong fingerprint (doesn't derive from pub) is refused...
		with self.assertRaisesRegex(frappe.ValidationError, "fingerprint"):
			crud.setup_encryption(doc.name, public_key=pub, wrapped_key="w",
				kdf_salt="s", key_iv="i", fingerprint="00:00:00:00:00:00:00:00")
		# ...the correct one arms the form.
		out = crud.setup_encryption(doc.name, public_key=pub, wrapped_key="w",
			kdf_salt="s", key_iv="i", fingerprint=fp)
		self.assertEqual(out["encrypted"], 1)
		self.assertEqual(frappe.db.get_value("FF Form", doc.name, "encrypted"), 1)

	def test_encryption_endpoints_refuse_non_owner_system_manager(self):
		# The whole promise: even a System Manager who isn't the creator can't arm encryption or pull
		# the wrapped key. Owner check must fire regardless of role.
		draft = draft_collection_form("enc-nonowner-form")  # owned by Administrator
		pub, fp = _keypair_material()
		frappe.set_user(NON_OWNER)
		try:
			with self.assertRaises(frappe.PermissionError):
				crud.setup_encryption(draft.name, public_key=pub, wrapped_key="w",
					kdf_salt="s", key_iv="i", fingerprint=fp)
			with self.assertRaises(frappe.PermissionError):
				crud.get_encryption_key("enc-test")
		finally:
			frappe.set_user("Administrator")

	def test_get_encryption_key_returns_material_to_owner(self):
		out = crud.get_encryption_key("enc-test")
		self.assertEqual(set(out), {"public_key", "wrapped_key", "kdf_salt", "key_iv", "fingerprint"})
		self.assertEqual(out["wrapped_key"], "wrapped-key-b64")

	def test_disable_encryption_clears_material_on_draft(self):
		doc = draft_collection_form("enc-disable")
		pub, fp = _keypair_material()
		crud.setup_encryption(doc.name, public_key=pub, wrapped_key="w",
			kdf_salt="s", key_iv="i", fingerprint=fp)
		crud.disable_encryption(doc.name)
		row = frappe.db.get_value("FF Form", doc.name,
			["encrypted", "enc_public_key", "enc_wrapped_key"], as_dict=True)
		self.assertEqual(row.encrypted, 0)
		self.assertFalse(row.enc_public_key)
		self.assertFalse(row.enc_wrapped_key)
