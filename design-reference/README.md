# UI reference - Frappe Forms prototype

Visual + interaction reference for the build (a React/Babel prototype - NOT the app). Recreate
the UI in Vue 3 + frappe-ui; do not copy the JSX. The authoritative field map and compile logic
live in `src/fieldmodel.jsx`; app-specific styling in `src/forms.css`.

## Five screens to match
| File | Screen |
|---|---|
| `app.jsx`        | top-level state machine, storage-mode + publish-freeze logic, tweaks |
| `shell.jsx`      | app-launcher grid (suite), sidebar, 48px page header |
| `dashboard.jsx`  | forms list (list + grid), status badges, response counts |
| `builder.jsx`    | field palette · editable canvas · question cards · inline option editing |
| `inspector.jsx`  | right panel: field settings + form settings, storage toggle, frozen lock, mapping |
| `bridge.jsx`     | "Developer view" slide-over: DocType/Web Form JSON, mapping table, Guardrails |
| `respondent.jsx` | public fillable form + success state |
| `responses.jsx`  | stat cards, bar charts, submissions as DocType records + record drawer |
| `fieldmodel.jsx` | **authoritative** field-type→fieldtype map, compileDocType/compileWebForm, freezing |

## Design system
Real Frappe UI (Espresso) tokens/components - in the app via the `frappe-ui` npm package +
its Tailwind preset. Inter font, near-black primary buttons, blue only for active/selection.
