# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Guest-facing endpoints. Submissions are governed records: the public form posts through a
# single whitelisted, rate-limited, honeypot-checked endpoint that validates every field
# server-side and inserts with ignore_permissions=True (we never grant Guest broad perms).
#
# Split by responsibility across this package; re-exported here so every whitelisted path
# stays `forms.api.<name>` and the hooks / admin / tests keep resolving against `forms.api`.

from forms.api.render import (
	WORKFLOW_STATES,
	get_public_form,
	inject_csrf_token,
	public_render_spec,
	session_info,
	track_view,
)
from forms.api.submissions import (
	delete_my_submission,
	get_linked_record,
	get_submission,
	list_my_submissions,
)
from forms.api.submit import submit
from forms.api.uploads import cleanup_orphan_uploads, upload_submission_file
from forms.api.validation import _coerce_and_validate  # used directly by the test-suite

__all__ = [
	"WORKFLOW_STATES",
	"cleanup_orphan_uploads",
	"delete_my_submission",
	"get_linked_record",
	"get_public_form",
	"get_submission",
	"inject_csrf_token",
	"list_my_submissions",
	"public_render_spec",
	"session_info",
	"submit",
	"track_view",
	"upload_submission_file",
]
