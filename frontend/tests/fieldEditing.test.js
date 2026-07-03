import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  addLine, correctSet, isCorrect, optionsArray, removeLine, rowsArray,
  scaleRange, setLine, toggleLine, quizOptions,
} from '../src/components/builder/fieldEditing.js'

test('optionsArray keeps a trailing empty option editable', () => {
  assert.deepEqual(optionsArray({ options: 'A\nB\n' }), ['A', 'B', ''])
  assert.deepEqual(optionsArray({ options: '' }), [''])
})

test('rowsArray drops empty lines', () => {
  assert.deepEqual(rowsArray({ grid_rows: 'R1\nR2\n' }), ['R1', 'R2'])
})

test('setLine replaces one line, preserving the rest', () => {
  assert.equal(setLine('A\nB\nC', 1, 'X'), 'A\nX\nC')
})

test('addLine appends a numbered entry after non-empty lines', () => {
  assert.equal(addLine('A\nB', 'Option'), 'A\nB\nOption 3')
  assert.equal(addLine('', 'Row'), 'Row 1')
})

test('removeLine drops the entry at index (after compacting empties)', () => {
  assert.equal(removeLine('A\nB\nC', 0), 'B\nC')
  assert.equal(removeLine('A\nB\nC', 2), 'A\nB')
})

test('scaleRange returns an inclusive range and falls back on a bad span', () => {
  assert.deepEqual(scaleRange({ scale_min: 1, scale_max: 5 }), [1, 2, 3, 4, 5])
  assert.deepEqual(scaleRange({ scale_min: 0, scale_max: 2 }), [0, 1, 2])
  assert.deepEqual(scaleRange({ scale_min: 5, scale_max: 1 }), [1, 2, 3, 4, 5]) // hi <= lo → fallback
  assert.equal(scaleRange({ scale_min: 1, scale_max: 100 }).length, 5) // span too wide → fallback
})

test('toggleLine adds then removes membership', () => {
  assert.equal(toggleLine('A', 'B'), 'A\nB')
  assert.equal(toggleLine('A\nB', 'A'), 'B')
})

test('correctSet / isCorrect read the newline-joined answer key', () => {
  assert.deepEqual(correctSet({ correct_answer: 'A\nC' }), ['A', 'C'])
  assert.ok(isCorrect({ correct_answer: 'A\nC' }, 'C'))
  assert.ok(!isCorrect({ correct_answer: 'A\nC' }, 'B'))
})

test('quizOptions yields Yes/No for yes_no, else the field options', () => {
  assert.deepEqual(quizOptions({ field_type: 'yes_no' }), ['Yes', 'No'])
  assert.deepEqual(quizOptions({ field_type: 'single_choice', options: 'A\nB' }), ['A', 'B'])
})
