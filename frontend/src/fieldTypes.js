// Mirrors design-reference/src/fieldmodel.jsx - the field-type catalog and the
// Frappe fieldtype each compiles to. Display only; the backend compile.py is authoritative.

export const FIELD_TYPES = [
  { id: 'short_answer', label: 'Short answer', icon: 'minus', doctype: 'Data', note: 'Single-line text' },
  { id: 'paragraph', label: 'Paragraph', icon: 'type', doctype: 'Small Text', note: 'Multi-line text' },
  { id: 'single_choice', label: 'Single choice', icon: 'circle-dot', doctype: 'Select', note: 'One option' },
  { id: 'checkboxes', label: 'Checkboxes', icon: 'list-checks', doctype: 'Table MultiSelect', note: 'Many options' },
  { id: 'dropdown', label: 'Dropdown', icon: 'chevron-down', doctype: 'Select', note: 'One from a menu' },
  { id: 'date', label: 'Date', icon: 'calendar', doctype: 'Date', note: 'Calendar date' },
  { id: 'rating', label: 'Rating', icon: 'star', doctype: 'Rating', note: '1-5 stars' },
  { id: 'linear_scale', label: 'Linear scale', icon: 'sliders-horizontal', doctype: 'Int', note: 'Numbered scale with end labels' },
  { id: 'mc_grid', label: 'Multiple choice grid', icon: 'grid-3x3', doctype: 'Table', note: 'One choice per row' },
  { id: 'checkbox_grid', label: 'Checkbox grid', icon: 'layout-grid', doctype: 'Table', note: 'Many choices per row' },
  { id: 'number', label: 'Number', icon: 'hash', doctype: 'Int', note: 'Whole number' },
  { id: 'email', label: 'Email', icon: 'at-sign', doctype: 'Data', note: 'Validated email' },
  { id: 'phone', label: 'Phone', icon: 'phone', doctype: 'Data', note: 'Phone number' },
  { id: 'time', label: 'Time', icon: 'clock', doctype: 'Time', note: 'Time of day' },
  { id: 'address', label: 'Address', icon: 'map-pin', doctype: 'Small Text', note: 'Postal address' },
  { id: 'yes_no', label: 'Yes / No', icon: 'toggle-left', doctype: 'Check', note: 'Boolean checkbox' },
  { id: 'file_upload', label: 'File upload', icon: 'paperclip', doctype: 'Attach', note: 'Attach a file' },
  { id: 'signature', label: 'Signature', icon: 'pen-line', doctype: 'Signature', note: 'Draw to sign' },
  { id: 'section_header', label: 'Section', icon: 'heading', doctype: '-', note: 'Page break + heading' },
]

export const FT = Object.fromEntries(FIELD_TYPES.map((t) => [t.id, t]))

export const CHOICE_TYPES = ['single_choice', 'checkboxes', 'dropdown']
export const hasOptions = (t) => CHOICE_TYPES.includes(t)
// Choice types that can carry a free-text "Other" write-in (compiles to Data, API-validated).
export const OTHER_TYPES = ['single_choice', 'dropdown']
export const canHaveOther = (t) => OTHER_TYPES.includes(t)
// Types whose option order can be shuffled per respondent.
export const canShuffleOptions = (t) => CHOICE_TYPES.includes(t)
// Text types that support max-length / pattern validation.
export const TEXT_TYPES = ['short_answer', 'paragraph', 'address']
export const isText = (t) => TEXT_TYPES.includes(t)
// Grid types: rows (grid_rows) x columns (options).
export const GRID_TYPES = ['mc_grid', 'checkbox_grid']
export const isGrid = (t) => GRID_TYPES.includes(t)
// Display-only blocks (no answer, no required toggle).
export const LAYOUT_TYPES = ['section_header']
export const isLayout = (t) => LAYOUT_TYPES.includes(t)

export function toFieldname(label, fallback = 'field') {
  const base = (label || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return base || fallback
}
