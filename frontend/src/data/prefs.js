import { reactive, watch } from 'vue'

// Client-side UI preferences. Developer mode is OFF by default: normal users (HR, ops) get a
// simple Google-Forms-style experience; power users flip it on to reveal Frappe internals
// (storage mode, generated DocType, column names, schema, the Developer panel).
// This is purely a UI preference - independent of the Frappe site's developer_mode.
const KEY = 'forms:devMode'
const NAV_KEY = 'forms:navCollapsed'
const THEME_KEY = 'forms:theme'

// Theme: stored choice wins; otherwise follow the OS preference (Apple-style).
const storedTheme = localStorage.getItem(THEME_KEY)
const prefersDark = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches

export const prefs = reactive({
  devMode: localStorage.getItem(KEY) === '1',
  navCollapsed: localStorage.getItem(NAV_KEY) === '1',
  dark: storedTheme ? storedTheme === 'dark' : !!prefersDark,
})

function applyTheme(dark) {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}
applyTheme(prefs.dark) // run on import so the theme is set before first paint

watch(
  () => prefs.devMode,
  (on) => localStorage.setItem(KEY, on ? '1' : '0'),
)
watch(
  () => prefs.navCollapsed,
  (on) => localStorage.setItem(NAV_KEY, on ? '1' : '0'),
)
watch(
  () => prefs.dark,
  (on) => {
    localStorage.setItem(THEME_KEY, on ? 'dark' : 'light')
    applyTheme(on)
  },
)

export function toggleDevMode() {
  prefs.devMode = !prefs.devMode
}
export function toggleNav() {
  prefs.navCollapsed = !prefs.navCollapsed
}
export function toggleTheme() {
  prefs.dark = !prefs.dark
}
