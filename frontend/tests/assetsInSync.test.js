import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// Guard against the exact drift that once blanked the live site: the committed forms.html
// referenced hashed asset files (index-<hash>.js/.css) that were never committed, so on Frappe
// Cloud — which serves the committed bundle as-is, no rebuild — those URLs 404'd and the page
// rendered blank. This asserts every asset forms.html points at actually exists on disk. It needs
// no build and is fully deterministic, unlike the CI "rebuild and diff" check (whose content
// hashes can shift across environments). forms.html and forms/public/frontend/ must ship together.

const appRoot = path.resolve(fileURLToPath(import.meta.url), '../../..') // frontend/tests -> app root
const html = readFileSync(path.join(appRoot, 'forms/www/forms.html'), 'utf8')

// The public URL /assets/forms/frontend/<rel> maps to forms/public/frontend/<rel> on disk.
const refs = [...html.matchAll(/\/assets\/forms\/frontend\/([^"'\s>]+)/g)].map((m) => m[1])

test('forms.html references at least one JS and one CSS bundle', () => {
  assert.ok(refs.some((r) => r.endsWith('.js')), 'no JS asset referenced in forms.html')
  assert.ok(refs.some((r) => r.endsWith('.css')), 'no CSS asset referenced in forms.html')
})

test('every asset forms.html references exists in forms/public/frontend', () => {
  const missing = refs.filter((rel) => !existsSync(path.join(appRoot, 'forms/public/frontend', rel)))
  assert.deepEqual(
    missing,
    [],
    `forms.html references asset(s) not committed to forms/public/frontend — the live site will ` +
      `404 on these and render blank. Run 'yarn build' and commit the result:\n  ${missing.join('\n  ')}`,
  )
})
