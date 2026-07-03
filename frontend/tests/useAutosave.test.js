import assert from 'node:assert/strict'
import { test } from 'node:test'
import { useAutosave } from '../src/data/useAutosave.js'

const delay = (ms) => new Promise((r) => setTimeout(r, ms))
const noop = () => {}

test('debounces multiple schedules into a single save', async () => {
  let saves = 0
  const { schedule } = useAutosave({ save: async () => { saves++ }, isReady: () => true, beacon: noop, debounceMs: 20, savedMs: 20 })
  schedule(); schedule(); schedule()
  await delay(60)
  assert.equal(saves, 1)
})

test('saveState transitions saving -> saved -> idle', async () => {
  const { saveState, schedule } = useAutosave({ save: async () => delay(5), isReady: () => true, beacon: noop, debounceMs: 10, savedMs: 20 })
  schedule()
  await delay(25) // debounce fired + save resolved
  assert.equal(saveState.value, 'saved')
  await delay(30)
  assert.equal(saveState.value, 'idle')
})

test('flush commits immediately when there are pending edits', async () => {
  let saves = 0
  const { schedule, flush } = useAutosave({ save: async () => { saves++ }, isReady: () => true, beacon: noop, debounceMs: 1000 })
  schedule()
  await flush()
  assert.equal(saves, 1)
})

test('flush is a no-op when nothing is pending', async () => {
  let saves = 0
  const { flush } = useAutosave({ save: async () => { saves++ }, isReady: () => true, beacon: noop })
  await flush()
  assert.equal(saves, 0)
})

test('does not save until isReady() is true', async () => {
  let saves = 0
  const { schedule } = useAutosave({ save: async () => { saves++ }, isReady: () => false, beacon: noop, debounceMs: 10 })
  schedule()
  await delay(30)
  assert.equal(saves, 0)
})
