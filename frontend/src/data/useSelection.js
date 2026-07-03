import { computed, ref } from 'vue'

// Multi-select over a reactive list of rows (each with a unique `name`). Tracks the set of
// selected names and derives select-mode / select-all from the currently visible rows, so
// "select all" and the all-checkbox always reflect the active view/filter.
//
// `visibleRows` is a ref/computed of the visible rows (or a getter returning them).
export function useSelection(visibleRows) {
  const selected = ref(new Set())
  const selectMode = computed(() => selected.value.size > 0)
  const names = computed(() => [...selected.value])

  const rows = () => (typeof visibleRows === 'function' ? visibleRows() : visibleRows.value) || []

  const allSelected = computed(() => {
    const list = rows()
    return list.length > 0 && list.every((f) => selected.value.has(f.name))
  })

  function toggle(name) {
    const s = new Set(selected.value)
    s.has(name) ? s.delete(name) : s.add(name)
    selected.value = s
  }

  function clear() { selected.value = new Set() }

  function toggleAll() {
    selected.value = allSelected.value ? new Set() : new Set(rows().map((f) => f.name))
  }

  return { selected, selectMode, names, allSelected, toggle, clear, toggleAll }
}
