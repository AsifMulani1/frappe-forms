import { onBeforeUnmount, ref } from 'vue'

// Debounced full-document autosave. Edits are coalesced into one save once typing pauses;
// `save` does the actual persist (+ any reconciliation), `isReady` gates it until loaded, and
// `beacon` is the last-ditch sync save fired when the tab is hidden/closed before the debounce.
//
// The debounce/save-state machine is DOM-free and unit-tested; only the pagehide/visibility
// wiring touches window/document, and it's skipped outside the browser (node tests, SSR).
export function useAutosave({ save, isReady, beacon, debounceMs = 1000, savedMs = 2000 }) {
  const saveState = ref('idle') // idle | saving | saved
  let saveTimer = null
  let savedTimer = null
  let pending = false // unsaved edits are queued behind the debounce

  function schedule() {
    clearTimeout(saveTimer)
    pending = true
    saveTimer = setTimeout(commit, debounceMs)
  }

  // Commit queued edits now — used on blur/navigation so a field commits as you leave it.
  function flush() {
    if (pending) return commit()
  }

  async function commit() {
    clearTimeout(saveTimer)
    if (!isReady() || !pending) return
    pending = false
    saveState.value = 'saving'
    await save()
    // A fresh edit during the round-trip re-armed the timer; don't stomp its "Saving…" state.
    if (pending) return
    saveState.value = 'saved'
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => { if (saveState.value === 'saved') saveState.value = 'idle' }, savedMs)
  }

  function fireBeacon() {
    if (!pending) return
    beacon()
    pending = false
  }

  function onVisibility() { if (document.visibilityState === 'hidden') fireBeacon() }

  if (typeof window !== 'undefined') {
    window.addEventListener('pagehide', fireBeacon)
    document.addEventListener('visibilitychange', onVisibility)
    onBeforeUnmount(() => {
      flush() // leaving the builder within the SPA: commit before teardown
      clearTimeout(saveTimer)
      clearTimeout(savedTimer)
      window.removeEventListener('pagehide', fireBeacon)
      document.removeEventListener('visibilitychange', onVisibility)
    })
  }

  return { saveState, schedule, flush }
}
