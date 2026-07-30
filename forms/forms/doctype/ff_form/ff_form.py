# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class FFForm(Document):
	def validate(self):
		self.ensure_slug()
		self.set_doctype_name()
		self.validate_redirect_url()
		self.ensure_field_keys()
		self.validate_field_patterns()
		self.guard_encryption()

	_ENC_FIELDS = ("encrypted", "enc_public_key", "enc_wrapped_key", "enc_kdf_salt",
		"enc_key_iv", "enc_fingerprint")

	def guard_encryption(self):
		"""Enforce the encryption invariants at the schema layer, so they hold even against a generic
		REST write that bypasses the owner-only setup_encryption / disable_encryption endpoints:

		- 'encrypted' requires the FULL key envelope. A partial state (e.g. public key but no wrapped
		  key) would let respondents seal identities the creator can never unlock.
		- Encryption is Collection-only. Linked mode writes the identity into the target record's owner
		  in the clear and has nowhere to store the sealed blob.
		- Once Published, the flag and key material are frozen. Identities are already sealed to the
		  current key; flipping the flag on re-publish would strip or duplicate the identity column and
		  could leave prior plaintext emails readable."""
		if cint(self.encrypted):
			if not all(self.get(f) for f in self._ENC_FIELDS):
				frappe.throw("Encryption can't be enabled without its key material. "
					"Set it up from the form's settings.")
			if self.storage_mode != "Collection":
				frappe.throw("Encryption is only available for Collection forms.")

		before = self.get_doc_before_save()
		if before and before.status == "Published":
			if any(self.get(f) != before.get(f) for f in self._ENC_FIELDS):
				frappe.throw("Encryption settings are frozen once a form is published.")

	def validate_field_patterns(self):
		"""Reject an invalid validation_pattern at save time (a builder typo), so it surfaces in the
		editor instead of silently no-op'ing at submit time. The submit path keeps its own re.error
		fallback so pre-existing bad data can never hard-fail a respondent."""
		import re

		from forms.compile import TEXT_TYPES

		for f in self.fields:
			pattern = (f.validation_pattern or "").strip()
			if f.field_type in TEXT_TYPES and pattern:
				try:
					re.compile(pattern)
				except re.error as e:
					frappe.throw(f"'{f.label or f.fieldname}' has an invalid validation pattern: {e}")

	def ensure_field_keys(self):
		"""Give every field a stable key the moment it's saved, so conditional logic can reference
		it across edits (labels and derived fieldnames change; field_key never does)."""
		for f in self.fields:
			if not f.field_key:
				f.field_key = frappe.generate_hash(length=10)

	def validate_redirect_url(self):
		"""Only allow http(s) or site-relative redirects — never javascript:/data: schemes."""
		url = (self.redirect_url or "").strip()
		if url and not (url.startswith("http://") or url.startswith("https://") or url.startswith("/")):
			frappe.throw("Redirect URL must start with http://, https:// or /")
		self.redirect_url = url

	def ensure_slug(self):
		"""While a form is a Draft its slug tracks the title, so renaming a form gives it a matching
		URL and generated-DocType name (a form created as "Untitled form" and then titled
		"DevCon 2026" becomes devcon-2026, not untitled-form-87). Once Published the slug is frozen —
		public links must never break. The slug is server-derived only; the client can't set it."""
		frozen = self.status == "Published"
		before = self.get_doc_before_save()
		title_changed = before is None or before.title != self.title
		if not frozen and (title_changed or not self.slug):
			base = slugify(self.title)
		else:
			base = slugify(self.slug) or slugify(self.title)
		if not base:
			base = "form"

		slug, n = base, 1
		while frappe.db.exists("FF Form", {"slug": slug, "name": ("!=", self.name or "")}):
			n += 1
			slug = f"{base}-{n}"
		self.slug = slug

	def set_doctype_name(self):
		"""Generated DocType name (Collection mode) tracks the title-derived slug while Draft, then
		freezes on publish so the name keeps pointing at the DocType that was actually created. An
		explicitly-set name is preserved — only an auto-derived one follows the slug."""
		if self.storage_mode != "Collection":
			return
		if self.status == "Published" and self.doctype_name:
			return
		before = self.get_doc_before_save()
		auto = not self.doctype_name or (before is not None and self.doctype_name == title_case(before.slug))
		if auto:
			self.doctype_name = title_case(self.slug)

	@frappe.whitelist()
	def publish(self):
		from forms.compile import publish

		return publish(self.name)


def slugify(text: str) -> str:
	import re

	text = (text or "").strip().lower()
	text = re.sub(r"[^a-z0-9]+", "-", text)
	return re.sub(r"^-+|-+$", "", text)


def title_case(text: str) -> str:
	import re

	cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", text or "").strip()
	return " ".join(w.capitalize() for w in cleaned.split()) or "Form Submission"
