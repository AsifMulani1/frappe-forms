import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ref } from 'vue'
import { useSelection } from '../src/data/useSelection.js'

const rowsOf = (...ids) => ref(ids.map((name) => ({ name })))

test('toggle adds then removes a name', () => {
  const { selected, toggle } = useSelection(rowsOf('a', 'b'))
  toggle('a')
  assert.ok(selected.value.has('a'))
  toggle('a')
  assert.ok(!selected.value.has('a'))
})

test('selectMode reflects whether anything is selected', () => {
  const { selectMode, toggle } = useSelection(rowsOf('a'))
  assert.equal(selectMode.value, false)
  toggle('a')
  assert.equal(selectMode.value, true)
})

test('allSelected is true only when every visible row is selected', () => {
  const rows = rowsOf('a', 'b')
  const { allSelected, toggle } = useSelection(rows)
  toggle('a')
  assert.equal(allSelected.value, false)
  toggle('b')
  assert.equal(allSelected.value, true)
})

test('allSelected is false for an empty list', () => {
  const { allSelected } = useSelection(rowsOf())
  assert.equal(allSelected.value, false)
})

test('toggleAll selects every visible row, then clears', () => {
  const { selected, allSelected, toggleAll } = useSelection(rowsOf('a', 'b', 'c'))
  toggleAll()
  assert.equal(selected.value.size, 3)
  assert.equal(allSelected.value, true)
  toggleAll()
  assert.equal(selected.value.size, 0)
})

test('names exposes the selection as an array', () => {
  const { names, toggle } = useSelection(rowsOf('a', 'b'))
  toggle('b')
  assert.deepEqual(names.value, ['b'])
})

test('clear empties the selection', () => {
  const { selected, toggle, clear } = useSelection(rowsOf('a', 'b'))
  toggle('a'); toggle('b')
  clear()
  assert.equal(selected.value.size, 0)
})
