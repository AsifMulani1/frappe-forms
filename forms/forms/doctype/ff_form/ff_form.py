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

	def guard_encryption(self):
		"""Encryption can only be armed while keys are present, and only the creator can hold them.

		The keys themselves are written by the owner-only setup_encryption endpoint, never through the
		generic builder save — so here we just refuse an inconsistent state: 'encrypted' on with no
		public key would silently store plaintext identities."""
		if cint(self.encrypted) and not self.enc_public_key:
			frappe.throw("Encryption can't be enabled without a key. Set it up from the form's settings.")

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
