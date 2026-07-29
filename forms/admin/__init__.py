# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Authenticated endpoints backing the builder SPA (dashboard, builder, responses).
# All data is read LIVE from the database - no hardcoded values anywhere.
#
# Split by responsibility across this package; re-exported here so every whitelisted
# path stays `forms.admin.<name>` and `from forms import admin` keeps resolving.

from forms.admin.access import has_app_permission
from forms.admin.crud import (
	create_form,
	delete_form,
	delete_forms,
	disable_encryption,
	duplicate_form,
	get_encryption_key,
	get_form,
	list_forms,
	nav_counts,
	preview,
	preview_form,
	publish_form,
	save_form,
	set_archived,
	set_archived_bulk,
	setup_encryption,
	target_doctype_fields,
)
from forms.admin.export import export_csv, open_in_sheet
from forms.admin.responses import (
	get_submission,
	list_submissions,
	responses_summary,
	set_workflow_state,
)
from forms.admin.sharing import list_shares, list_users, share_form, unshare_form

__all__ = [
	"create_form",
	"delete_form",
	"delete_forms",
	"disable_encryption",
	"duplicate_form",
	"export_csv",
	"get_encryption_key",
	"get_form",
	"get_submission",
	"has_app_permission",
	"list_forms",
	"list_shares",
	"list_submissions",
	"list_users",
	"nav_counts",
	"open_in_sheet",
	"preview",
	"preview_form",
	"publish_form",
	"responses_summary",
	"save_form",
	"set_archived",
	"set_archived_bulk",
	"set_workflow_state",
	"setup_encryption",
	"share_form",
	"target_doctype_fields",
	"unshare_form",
]
