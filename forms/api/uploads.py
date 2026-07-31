# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Guest-safe file uploads for file_upload fields: a validated PRIVATE File that submit()
# later re-points to the actual record, plus the scheduled reaper for orphaned uploads.

import frappe
from frappe.rate_limiter import rate_limit

from forms.api.render import _published_form
from forms.compile import resolve_fieldname
from forms.config import (
	ALLOWED_UPLOAD_EXT,
	MAX_UPLOAD_BYTES,
	ORPHAN_UPLOAD_GRACE_HOURS,
	RATE_WINDOW_HOUR,
	UPLOAD_RATE_LIMIT,
)


@frappe.whitelist(allow_guest=True)
@rate_limit(key="slug", limit=UPLOAD_RATE_LIMIT, seconds=RATE_WINDOW_HOUR)
def upload_submission_file(slug: str, fieldname: str):
	"""Guest-safe upload for a published form's file_upload field. Saves a PRIVATE File (validated
	for size + extension) and returns its url; the file is linked to the record on submit. We never
	use Frappe's broad upload_file for guests - this endpoint only accepts files for a real field."""
	form = _published_form(slug)
	field = next((f for f in form.fields if (f.fieldname or resolve_fieldname(f)) == fieldname), None)
	if not field or field.field_type != "file_upload":
		frappe.throw("Unknown upload field.")

	files = getattr(frappe.request, "files", None)
	uploaded = files.get("file") if files else None
	if not uploaded:
		frappe.throw("No file provided.")

	content = uploaded.stream.read()
	if not content:
		frappe.throw("Empty file.")
	if len(content) > MAX_UPLOAD_BYTES:
		frappe.throw("File is too large (max 10 MB).")

	filename = uploaded.filename or "upload"
	ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
	if ext not in ALLOWED_UPLOAD_EXT:
		frappe.throw(f"'{ext or filename}' files are not allowed.")

	# Tie the upload to its form so an unsubmitted file is identifiable (and reapable). On submit,
	# _attach_file re-points it to the actual submission record; anything still attached to "FF Form"
	# after a grace period was never submitted and gets cleaned up (see cleanup_orphan_uploads).
	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": filename,
		"content": content,
		"is_private": 1,
		"attached_to_doctype": "FF Form",
		"attached_to_name": form.name,
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"file_url": file_doc.file_url, "file_name": file_doc.file_name}


def cleanup_orphan_uploads():
	"""Scheduled: delete private guest uploads that were never tied to a submission.

	upload_submission_file parks files on their FF Form; a real submission re-points them to the
	response record. Files still parked on "FF Form" after 2h are abandoned uploads — reap them so
	guest uploads can't accumulate unbounded private-file storage."""
	stale = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "FF Form",
			"is_private": 1,
			"creation": ("<", frappe.utils.add_to_date(None, hours=-ORPHAN_UPLOAD_GRACE_HOURS)),
		},
		pluck="name",
		limit=500,
	)
	for name in stale:
		try:
			frappe.delete_doc("File", name, ignore_permissions=True, delete_permanently=True)
		except Exception:
			frappe.log_error(title="Forms orphan-upload cleanup failed")
	if stale:
		frappe.db.commit()


def _attach_file(file_url: str, dt: str, dn: str, neutralise_owner: bool = False):
	"""Link an already-uploaded File to the submission record it belongs to.

	On an encrypted form (neutralise_owner), also strip the uploader's identity from the File row: a
	signed-in respondent's upload is created with File.owner = their user, which — joined to
	attached_to_name — would deanonymise them despite the sealed identity blob. Guest uploads are
	already owned by Guest, so this only matters for signed-in respondents."""
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return
	values = {"attached_to_doctype": dt, "attached_to_name": dn}
	if neutralise_owner:
		values["owner"] = "Guest"
		values["modified_by"] = "Guest"
	frappe.db.set_value("File", name, values)
