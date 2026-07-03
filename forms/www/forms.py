import re
from urllib.parse import unquote

import frappe

# Context module for the SPA page (forms/www/forms.html). Frappe calls get_context on every
# full-page load of any /forms/... route. We use it for one thing: relax frame-busting on the
# public respondent form so it can be embedded on the sites its owner allow-lists.


def get_context(context):
	"""Emit a `frame-ancestors` CSP for a published public form whose owner has allow-listed
	embedding domains, so it may be iframed on exactly those sites. Every other /forms route
	(builder, dashboard) is left untouched and keeps the platform's default same-origin framing.
	"""
	slug = _public_form_slug()
	if not slug:
		return

	row = frappe.db.get_value(
		"FF Form", {"slug": slug}, ["status", "embed_allowed_domains"], as_dict=True
	)
	if not row or row.status != "Published":
		return

	ancestors = _frame_ancestors(row.embed_allowed_domains)
	if not ancestors:
		return

	# The page is otherwise cacheable for guests; a cached render would skip this hook and drop
	# the header, so opt this form's page out of the website cache.
	context.no_cache = 1
	frappe.local.response_headers["Content-Security-Policy"] = (
		f"frame-ancestors 'self' {' '.join(ancestors)}"
	)


def _public_form_slug() -> str | None:
	"""The slug of the public form being loaded, or None if this isn't a /forms/f/<slug> load."""
	request = getattr(frappe.local, "request", None)
	path = request.path if request else ""
	match = re.match(r"^/forms/f/([^/?#]+)", path or "")
	return unquote(match.group(1)) if match else None


def _frame_ancestors(raw: str | None) -> list[str]:
	"""Parse the allow-list into CSP host-sources. Accepts one origin per line (commas too),
	tolerates a pasted scheme/path, and reduces each to `scheme://host[:port]` or a bare host.
	"""
	sources = []
	for line in (raw or "").replace(",", "\n").splitlines():
		token = line.strip()
		if not token:
			continue
		if "://" in token:
			scheme, rest = token.split("://", 1)
			token = f"{scheme}://{rest.split('/', 1)[0]}"
		else:
			token = token.split("/", 1)[0]
		if token:
			sources.append(token)
	return sources
