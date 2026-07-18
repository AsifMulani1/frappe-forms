import assert from 'node:assert/strict'
import { test } from 'node:test'
import { answerValues, conditionMet, toFieldname } from '../src/fieldTypes.js'

// conditionMet / answerValues must mirror forms/api/validation.py::_condition_met so a field's
// visibility is identical on the client and on submit.

test('answerValues flattens scalars, lists and grid dicts', () => {
  assert.deepEqual(answerValues(''), [])
  assert.deepEqual(answerValues(null), [])
  assert.deepEqual(answerValues('Yes'), ['Yes'])
  assert.deepEqual(answerValues(['A', 'B']), ['A', 'B'])
  assert.deepEqual(answerValues({ R1: 'A', R2: ['B', 'C'] }), ['A', 'B', 'C'])
})

test('conditionMet: equals / not_equals / contains', () => {
  assert.equal(conditionMet('equals', 'Yes', 'Yes'), true)
  assert.equal(conditionMet('equals', 'Yes', 'No'), false)
  assert.equal(conditionMet('not_equals', 'Yes', 'No'), true)
  assert.equal(conditionMet('not_equals', 'Yes', 'Yes'), false)
  assert.equal(conditionMet('contains', 'Veg', ['Vegan', 'Meat']), true)
  assert.equal(conditionMet('contains', 'Fish', ['Vegan', 'Meat']), false)
})

test('conditionMet matches a value inside a checkbox list (equals)', () => {
  assert.equal(conditionMet('equals', 'B', ['A', 'B']), true)
})

test('toFieldname scrubs a label to a safe snake_case identifier', () => {
  assert.equal(toFieldname('Full Name'), 'full_name')
  assert.equal(toFieldname('  Weird!! chars @# '), 'weird_chars')
  assert.equal(toFieldname(''), 'field')
})
