// Pure helpers for editing a builder field's newline-joined lists (options, grid rows,
// correct answers) and its linear-scale range. No Vue and no emit — Canvas wraps these and
// emits the returned value, which keeps the fiddly string logic unit-testable in isolation.

const lines = (text) => (text || '').split('\n')
const nonEmpty = (text) => lines(text).filter((x) => x.length)

// Options keep a trailing empty entry so a just-added blank option stays editable.
export function optionsArray(field) {
  return lines(field.options).filter((o) => o.length || o === '')
}

export function rowsArray(field) {
  return nonEmpty(field.grid_rows)
}

export function setLine(text, i, val) {
  const arr = lines(text)
  arr[i] = val
  return arr.join('\n')
}

export function addLine(text, label) {
  const arr = nonEmpty(text)
  arr.push(`${label} ${arr.length + 1}`)
  return arr.join('\n')
}

export function removeLine(text, i) {
  const arr = nonEmpty(text)
  arr.splice(i, 1)
  return arr.join('\n')
}

// Inclusive integer range for a linear-scale field, clamped to a sane span.
export function scaleRange(field) {
  let lo = Number.isFinite(+field.scale_min) ? +field.scale_min : 1
  let hi = Number.isFinite(+field.scale_max) ? +field.scale_max : 5
  if (hi <= lo || hi - lo > 14) { lo = 1; hi = 5 }
  return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
}

// Quiz: correct_answer is stored newline-joined.
export function correctSet(field) {
  return nonEmpty(field.correct_answer)
}

export function isCorrect(field, opt) {
  return correctSet(field).includes(opt)
}

export function toggleLine(text, opt) {
  const set = new Set(nonEmpty(text))
  set.has(opt) ? set.delete(opt) : set.add(opt)
  return [...set].join('\n')
}

export function quizOptions(field) {
  if (field.field_type === 'yes_no') return ['Yes', 'No']
  return nonEmpty(field.options)
}
