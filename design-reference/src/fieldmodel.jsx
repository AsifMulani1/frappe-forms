// fieldmodel.jsx — field-type catalog, DocType compilation, and sample form data.
// AUTHORITATIVE reference for compile.py. Port this logic to Python faithfully.

const FIELD_TYPES = [
  { id: 'short_answer',  label: 'Short answer',  icon: 'minus',          doctype: 'Data',              note: 'Single-line text' },
  { id: 'paragraph',     label: 'Paragraph',     icon: 'text',           doctype: 'Small Text',        note: 'Multi-line text' },
  { id: 'single_choice', label: 'Single choice', icon: 'circle-dot',     doctype: 'Select',            note: 'One option' },
  { id: 'checkboxes',    label: 'Checkboxes',    icon: 'list-checks',    doctype: 'Table MultiSelect', note: 'Many options' },
  { id: 'dropdown',      label: 'Dropdown',      icon: 'chevron-down',   doctype: 'Select',            note: 'One from a menu' },
  { id: 'date',          label: 'Date',          icon: 'calendar',       doctype: 'Date',              note: 'Calendar date' },
  { id: 'rating',        label: 'Rating',        icon: 'star',           doctype: 'Rating',            note: '1–5 stars' },
  { id: 'number',        label: 'Number',        icon: 'hash',           doctype: 'Int',               note: 'Whole number' },
  { id: 'email',         label: 'Email',         icon: 'at-sign',        doctype: 'Data',              note: 'Validated email' },
  { id: 'yes_no',        label: 'Yes / No',      icon: 'toggle-left',    doctype: 'Check',             note: 'Boolean checkbox' },
];

const CHOICE_TYPES = ['single_choice', 'checkboxes', 'dropdown'];

// derive a Frappe fieldname (snake_case, ascii) from a label
function toFieldname(label, fallback) {
  const base = (label || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return base || fallback || 'field';
}

// A field's column name is FROZEN at publish: once f.fieldname is set it is authoritative.
function resolveFieldname(f) { return f.fieldname || toFieldname(f.label, f.id); }

// Translate the friendly form into a Frappe DocField object.
function compileField(f, allNames) {
  let fieldname = resolveFieldname(f);
  let candidate = fieldname, n = 1;
  while (allNames.has(candidate)) { candidate = `${fieldname}_${++n}`; }
  allNames.add(candidate);
  const df = { fieldname: candidate, label: f.label, fieldtype: FT[f.type].doctype };
  switch (f.type) {
    case 'email': df.options = 'Email'; break;
    case 'single_choice':
    case 'dropdown': df.options = (f.options || []).join('\n'); break;
    case 'checkboxes': df.options = `${toTitle(candidate)} Item`; break; // child table doctype
    default: break;
  }
  if (f.required) df.reqd = 1;
  if (f.help) df.description = f.help;
  return df;
}

// Model A — a dedicated DocType is created for this form's submissions.
function compileDocType(form) {
  const names = new Set();
  const fields = form.fields.map((f) => compileField(f, names));
  return {
    doctype: 'DocType', name: form.doctypeName, module: 'Forms', custom: 1,
    naming_rule: 'Expression', autoname: 'format:REG-{YYYY}-{#####}', track_changes: 1, fields,
    permissions: [
      { role: 'System Manager', read: 1, write: 1, create: 1, delete: 1 },
      { role: 'Forms Manager', read: 1, write: 1, create: 1, delete: 0 },
      { role: 'Guest', read: 0, write: 0, create: 1, delete: 0 },
    ],
  };
}

// Linked mode (Model B) — Web Form bound to an existing DocType. autoMap guesses field mapping.
// See original prototype for TARGET_DOCTYPES, autoMap, compileWebForm.
