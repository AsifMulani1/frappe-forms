# Frappe Forms - app guide (authoritative)

"Frappe Forms" is a Frappe app: a Google-Forms-style form builder whose forms compile to
real Frappe DocTypes. It ships as a HEADLESS frappe-ui SPA - users never touch Frappe Desk.

## Environment (this machine)
- Bench: `~/frappe-bench` (Frappe v17 develop, Python 3.14 venv at `env/`).
- Site: `forms.localhost` (admin password `admin`).
- The real Frappe bench CLI is `/Users/asif/Library/Python/3.9/bin/bench` (bare `bench`
  resolves to an unrelated custom `bench-cli` wizard - do NOT use that).
- DB: local MariaDB 12, root password `1234`, socket auth (users created at host `localhost`).
- Run commands as e.g.
  `/Users/asif/Library/Python/3.9/bin/bench --site forms.localhost migrate`.

## Architecture
- App: `forms` (module "Forms", folder `apps/forms/forms/forms`).
- Frontend: Vue 3 + Vite + frappe-ui in `apps/forms/frontend`.
  - Builder SPA (login required, role "Forms Manager") at `/forms`: dashboard, builder, responses.
  - Respondent SPA (guest allowed) at `/forms/f/<slug>`: the public fillable form.
  - Redirect `/app` -> `/forms` for users without System Manager.
- Backend: Python controllers + a DocType-compilation engine.

## Design system = frappe-ui (Espresso). Hard rules
- frappe-ui components only (Button, Dialog, FormControl, ListView, Badge, Avatar, Switch,
  Tabs, Tooltip, Dropdown). Never hand-roll/restyle raw HTML to imitate them.
- frappe-ui Tailwind preset for all tokens. Inter font. Lucide icons only (no emoji/SVG icons).
- Sentence case. Terse labels. Confirmations are questions ("Delete this form?" /
  "This cannot be undone.").
- Primary action = Button variant="solid" theme="gray" (near-black). Blue is ONLY for
  selection, focus rings, links, active states. Hairline borders, subtle shadows, radii
  8px controls / 10px cards / 12px dialogs. 48px sticky page header, one primary action.
- Visual reference prototype in `design-reference/` (Frappe Forms.html + src/*.jsx, React -
  reference only, do NOT copy). Match its layout, copy, spacing, and five screen flows.

## Data model (builder metadata - normal app DocTypes, defined in code)
- "FF Form": title (Data, reqd), slug (Data, unique - auto-slugify from title if empty),
  description (Small Text), status (Select: Draft\nPublished, default Draft),
  storage_mode (Select: Collection\nLinked, default Collection),
  target_doctype (Link: DocType), doctype_name (Data, the generated DocType),
  accent (Select: blue\ngreen\nviolet\nrose\namber\nteal, default blue),
  login_required (Check), allow_multiple (Check, default 1), collect_email (Check, default 1),
  fields (Table: FF Form Field).
  Plus: cover_image, category, thank_you_message, redirect_url, shuffle_questions, show_progress,
  email_receipt, allow_edit, show_my_submissions, allow_delete, apply_doc_perms, is_template,
  notify_on_response + notify_email (admin notification), opens_on / closes_on / response_limit
  (scheduling + cap), is_quiz + show_score (quiz mode).
- "FF Form Field" (istable:1): label (Data), fieldname (Data, frozen at publish),
  field_key (Data, read-only stable id used by conditional logic - never changes),
  field_type (Select, the types above), reqd (Check), help_text (Small Text),
  options (Small Text, newline-joined for choice types / grid columns), grid_rows, mapped_field
  (Linked mode), has_other, shuffle_options, min_value/max_value/max_length/validation_pattern/
  error_message, scale_min/scale_max/min_label/max_label (linear scale),
  condition_field/condition_operator/condition_value (conditional logic, references a field_key),
  points + correct_answer (quiz grading; correct_answer is server-only, never sent to respondents).

## Field-type -> Frappe fieldtype map (authoritative)
  short_answer  -> Data
  paragraph     -> Small Text
  email         -> Data            (options: "Email")
  number        -> Int
  single_choice -> Select          (options = newline-joined choices)
  dropdown      -> Select          (options = newline-joined choices)
  checkboxes    -> Table MultiSelect  (generate child DocType "<Parent> <Label> Item",
                                       istable:1, one Data field "value"; parent options =
                                       that child DocType name)
  date          -> Date
  rating        -> Rating
  linear_scale  -> Int             (scale_min..scale_max, optional min_label/max_label)
  mc_grid       -> Table           (rows x columns -> child {row, value}, one value per row)
  checkbox_grid -> Table           (rows x columns -> child {row, value}, many values per row)
  yes_no        -> Check
  phone         -> Data            (regex-validated)
  time          -> Time
  address       -> Small Text
  file_upload   -> Attach          (guest upload via upload_submission_file; private File)
  signature     -> Signature       (base64 PNG data URL, size-capped)
  section_header-> (display only, no column; doubles as page break in the respondent view)
  reqd -> reqd:1 ; help_text -> description ; frozen fieldname is authoritative.

## Publish rules
- Freeze every field's fieldname on publish (scrub from label if empty; keep if set).
- Collection mode: create custom DocType (custom:1, module "Forms",
  autoname "format:{SLUG}-{YYYY}-{#####}", track_changes:1, permissions: System Manager rwcd,
  Forms Manager rwc-). Re-publish = additive-only (append new, set hidden:1 + read_only:1 on
  removed, NEVER drop).
- Linked mode: validate each mapped_field exists on target_doctype; no schema change.
- Submissions arrive via a guest endpoint (we do NOT grant Guest broad create perms).

## Submission
One `@frappe.whitelist(allow_guest=True)` endpoint, rate-limited (20/hr per slug),
honeypot-checked, validates required + email/int/select/date formats server-side, inserts with
`ignore_permissions=True`, returns the new record name.
- Gating (new responses only, not token/record edits): `_accepting_status` enforces the
  opens_on/closes_on window + response_limit; `_block_if_duplicate` enforces one-response-per-user
  when allow_multiple is off (by record owner if signed in, else by collected email).
- Conditional logic: `_visible_specs` drops fields whose condition_field rule isn't met by the
  submitted answers - hidden fields are neither validated (a hidden required field can't block a
  submit) nor stored. Conditional fields are compiled reqd:0 (their requiredness is API-enforced
  when visible). The SPA mirrors the same evaluator (`conditionMet` in fieldTypes.js).
- Quiz: when is_quiz, `_grade` scores visible graded fields into the score/max_score system
  columns and returns the score (shown to the respondent when show_score).
- Pre-filled links: the respondent SPA reads `?<fieldname>=value` query params (checkboxes
  comma-separated, `?email=` for the collected email) - client-side only.
- Generated Collection DocTypes carry system columns: workflow_state, edit_token,
  respondent_email, score, max_score (all backfilled additively on re-publish).

## Conventions
snake_case fieldnames, server-side validation always, never trust client data. Write a
controller test for the compile engine and the submission endpoint. Run migrate after
DocType changes and `bench build --app forms` for assets.

## NO HARDCODED DATA (hard rule)
Zero mock/placeholder/hardcoded data in the frontend OR backend. Every list, card, stat,
chart, table, and record reads LIVE from the DB via frappe-ui resources
(createResource / createListResource) or whitelisted API calls. Empty states are real.
The ONLY place data is created is `seed.py` (dev-only), which writes REAL records through the
app's own code paths; the UI reads them live, never imports them.
