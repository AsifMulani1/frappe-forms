import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateField } from '../src/data/validate.js'

// These cases pin the client mirror of forms/api/validation.py::_coerce_and_validate. If the server
// rules change, these should change in lockstep — that's the point of the file.

test('required empty is flagged, optional empty is ok', () => {
  assert.equal(validateField({ field_type: 'short_answer', reqd: 1 }, ''), true)
  assert.equal(validateField({ field_type: 'short_answer', reqd: 1 }, undefined), true)
  assert.equal(validateField({ field_type: 'short_answer', reqd: 0 }, ''), false)
  assert.equal(validateField({ field_type: 'checkboxes', reqd: 1 }, []), true)
  assert.equal(validateField({ field_type: 'mc_grid', reqd: 1 }, {}), true)
})

test('number bounds mirror the server', () => {
  const f = { field_type: 'number', reqd: 0, min_value: '18', max_value: '60' }
  assert.equal(validateField(f, '30'), false)
  assert.equal(validateField(f, '17'), 'Must be at least 18.')
  assert.equal(validateField(f, '61'), 'Must be at most 60.')
})

test('text max length and pattern mirror the server', () => {
  assert.equal(validateField({ field_type: 'short_answer', reqd: 0, max_length: 4 }, 'abcd'), false)
  assert.equal(
    validateField({ field_type: 'short_answer', reqd: 0, max_length: 4 }, 'abcde'),
    'Must be at most 4 characters.',
  )
  const pat = { field_type: 'short_answer', reqd: 0, validation_pattern: '\\d{5}' }
  assert.equal(validateField(pat, '12345'), false)
  assert.equal(validateField(pat, 'abc'), 'Not in the expected format.')
})

test('a malformed pattern never blocks a real answer (matches the server fallback)', () => {
  const bad = { field_type: 'short_answer', reqd: 0, validation_pattern: '([unclosed' }
  assert.equal(validateField(bad, 'anything'), false)
})

test('error_message overrides the default text', () => {
  const f = { field_type: 'number', reqd: 0, min_value: '1', error_message: 'Pick a bigger number.' }
  assert.equal(validateField(f, '0'), 'Pick a bigger number.')
})
