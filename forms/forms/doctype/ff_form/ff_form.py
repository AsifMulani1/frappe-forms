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

	def validate_redirect_url(self):
		"""Only allow http(s) or site-relative redirects — never javascript:/data: schemes."""
		url = (self.redirect_url or "").strip()
		if url and not (url.startswith("http://") or url.startswith("https://") or url.startswith("/")):
			frappe.throw("Redirect URL must start with http://, https:// or /")
		self.redirect_url = url

	def ensure_slug(self):
		"""Auto-slugify from title (or the given slug), de-duping with a numeric suffix."""
		base = slugify(self.slug) if self.slug else slugify(self.title)
		if not base:
			base = "form"

		slug, n = base, 1
		while frappe.db.exists("FF Form", {"slug": slug, "name": ("!=", self.name or "")}):
			n += 1
			slug = f"{base}-{n}"
		self.slug = slug

	def set_doctype_name(self):
		"""Default the generated DocType name from the (unique) slug - Collection mode."""
		if self.storage_mode == "Collection" and not self.doctype_name:
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
