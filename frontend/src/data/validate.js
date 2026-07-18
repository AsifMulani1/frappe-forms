// Client mirror of the server's per-field validation (forms/api/validation.py::_coerce_and_validate).
// Kept as a pure function — value in, verdict out — so it's unit-testable and the client/server
// contract can be pinned in tests. Returns: false = ok, true = required-but-empty, string = a
// specific error message. The server remains authoritative; this only spares a round-trip.
export function validateField(f, value) {
  const v = value
  const empty = Array.isArray(v) ? !v.length
    : v && typeof v === 'object' ? !Object.keys(v).length
    : v === undefined || v === '' || v === null
  if (empty) return !!f.reqd
  if (f.field_type === 'number') {
    const n = Number(v)
    const lo = f.min_value !== '' && f.min_value != null ? Number(f.min_value) : null
    const hi = f.max_value !== '' && f.max_value != null ? Number(f.max_value) : null
    if (lo != null && n < lo) return f.error_message || `Must be at least ${lo}.`
    if (hi != null && n > hi) return f.error_message || `Must be at most ${hi}.`
  }
  if (['short_answer', 'paragraph', 'address'].includes(f.field_type)) {
    if (f.max_length && String(v).length > f.max_length) return f.error_message || `Must be at most ${f.max_length} characters.`
    if (f.validation_pattern) {
      let ok = true
      try { ok = new RegExp(`^(?:${f.validation_pattern})$`).test(String(v)) } catch { ok = true }
      if (!ok) return f.error_message || 'Not in the expected format.'
    }
  }
  return false
}
