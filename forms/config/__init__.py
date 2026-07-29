# Copyright (c) 2026, Acme and contributors
# For license information, please see license.txt
#
# Central tunables for the guest-facing endpoints. Kept in one stdlib-only module (no imports
# from forms.api / forms.compile) so it can be imported at decorator-evaluation time without any
# risk of a circular import.

# --- Submission ---------------------------------------------------------------------------------
RATE_WINDOW_HOUR = 60 * 60

# Per-slug guest submission cap. Google-Forms-style abuse control leans on this + the honeypot +
# login/one-response gating rather than a CAPTCHA.
SUBMIT_RATE_LIMIT = 20
SUBMIT_RATE_WINDOW = RATE_WINDOW_HOUR

# --- Public render ------------------------------------------------------------------------------
PUBLIC_RENDER_RATE_LIMIT = 600
TRACK_VIEW_RATE_LIMIT = 120

# --- Uploads ------------------------------------------------------------------------------------
UPLOAD_RATE_LIMIT = 30
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXT = {"png", "jpg", "jpeg", "gif", "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt"}
# Files still parked on their FF Form after this window were never submitted — reap them.
ORPHAN_UPLOAD_GRACE_HOURS = 2

# --- Signatures ---------------------------------------------------------------------------------
# Base64 PNG data URL cap, to keep records sane.
SIGNATURE_MAX_BYTES = 500_000

# --- Identity encryption ------------------------------------------------------------------------
# A sealed identity envelope is tiny (an ephemeral P-256 key + IV + a short ciphertext). Cap it so a
# malformed/oversized blob can't bloat the row or be used to abuse the Long Text column.
ENC_IDENTITY_MAX_BYTES = 8 * 1024
