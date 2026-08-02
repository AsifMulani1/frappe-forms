<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, FormControl, confirmDialog, toast } from 'frappe-ui'
import { call } from '../data/call'
import { conditionMet } from '../fieldTypes'
import { validateField } from '../data/validate'
import { sealIdentity } from '../data/crypto'
import Icon from '../components/Icon.vue'
import RespondentField from '../components/RespondentField.vue'
import ProgressBar from '../components/public/ProgressBar.vue'
import SubmissionsList from '../components/public/SubmissionsList.vue'
import PageNav from '../components/public/PageNav.vue'
import SuccessScreen from '../components/public/SuccessScreen.vue'

const props = defineProps({ slug: String })
const route = useRoute()
// Builder preview: render the respondent view for a (possibly Draft) form via an auth-only
// endpoint. Submitting is disabled — nothing is written.
const isPreview = ref(!!route.query.preview)
const editToken = ref(route.query.edit || null) // Collection: editing via private token link
const recordName = ref(route.query.name || null) // Linked: editing an existing target record
const editing = ref(false)

const form = ref(null)
const notFound = ref(false)
const answers = reactive({})
const errors = reactive({})
const submitting = ref(false)
const done = ref(null)
const submitResult = ref(null) // { score, max_score, show_score } after a quiz submission
const redirecting = ref(false)
const hp = ref('') // honeypot
const uploading = reactive({})
const fileNames = reactive({})
const respondentEmail = ref('') // captured when the form collects email
const emailError = ref(false)
const mySubs = ref([]) // signed-in respondent's own past submissions
const mySubsMeta = ref({})
// "Other" write-in state, keyed by fieldname (single choice / dropdown).
const otherOn = reactive({})
const otherText = reactive({})
// Per-respondent presentation: questions paginated by section_header, optionally shuffled.
const pages = ref([]) // [{ header: field|null, fields: [...] }]
const currentPage = ref(0)
const optionMap = reactive({})
// Which question card is "active" — the last one focused or tapped. Drives the accent edge
// so the respondent always sees where they are, one card at a time.
const activeField = ref(null)

function shuffle(arr) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function buildPresentation() {
  const f = form.value
  for (const fld of f.fields || []) {
    optionMap[fld.fieldname] = fld.shuffle_options ? shuffle(fld.options || []) : fld.options || []
  }
  // A section_header starts a new page; its label/help become that page's heading. Fields before
  // the first header form page 0. This keeps section_header as the sole page-break marker.
  const result = []
  let cur = { header: null, fields: [] }
  for (const fld of f.fields || []) {
    if (fld.field_type === 'section_header') {
      if (cur.fields.length || cur.header) result.push(cur)
      cur = { header: fld, fields: [] }
    } else {
      cur.fields.push(fld)
    }
  }
  if (cur.fields.length || cur.header) result.push(cur)
  // Shuffle questions WITHIN each page so page boundaries stay intact.
  if (f.shuffle_questions) result.forEach((p) => { p.fields = shuffle(p.fields) })
  pages.value = result.length ? result : [{ header: null, fields: [] }]
  currentPage.value = 0
}

// Conditional logic: a field referencing another (by field_key) shows only when the rule holds.
const keyToFieldname = computed(() => {
  const m = {}
  for (const f of form.value?.fields || []) {
    if (f.field_type !== 'section_header' && f.field_key) m[f.field_key] = f.fieldname
  }
  return m
})
function isVisible(f) {
  if (!f.condition_field) return true
  const ctrlFn = keyToFieldname.value[f.condition_field]
  return conditionMet(f.condition_operator, f.condition_value, ctrlFn ? answers[ctrlFn] : undefined)
}
function visibleFields(fields) {
  return (fields || []).filter(isVisible)
}

// Read query params as answer prefills (?fieldname=value, checkboxes comma-separated; ?email=…).
function applyPrefill() {
  const reserved = new Set(['preview', 'edit', 'name'])
  const byFieldname = {}
  for (const f of form.value.fields || []) if (f.fieldname) byFieldname[f.fieldname] = f
  for (const [k, v] of Object.entries(route.query)) {
    if (reserved.has(k)) continue
    const f = byFieldname[k]
    if (f) {
      if (f.field_type === 'checkboxes') answers[f.fieldname] = String(v).split(',').map((s) => s.trim()).filter(Boolean)
      else answers[f.fieldname] = String(v)
    } else if (k === 'email' && form.value.collect_email) {
      respondentEmail.value = String(v)
    }
  }
}

// Form closed (outside its open/close window, or at its response limit) — render a notice, not the form.
const closed = computed(() => !isPreview.value && form.value && form.value.accepting === false)

const page = computed(() => pages.value[currentPage.value] || { header: null, fields: [] })
const multiPage = computed(() => pages.value.length > 1)
const isLastPage = computed(() => currentPage.value >= pages.value.length - 1)

function validatePage(idx) {
  let ok = true
  for (const f of visibleFields(pages.value[idx]?.fields)) {
    const res = validateField(f, answers[f.fieldname])
    if (res) { errors[f.fieldname] = res; ok = false }
  }
  return ok
}
function nextPage() {
  if (currentPage.value === 0 && !emailOk()) return
  if (!validatePage(currentPage.value)) return
  if (currentPage.value < pages.value.length - 1) {
    currentPage.value++
    activeField.value = null // new page: drop the previous page's active card
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}
function prevPage() {
  if (currentPage.value > 0) {
    currentPage.value--
    activeField.value = null
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

async function load() {
  try {
    const endpoint = isPreview.value ? 'forms.admin.preview_form' : 'forms.api.get_public_form'
    form.value = await call(endpoint, { slug: props.slug })
    buildPresentation()
    applyPrefill()
    if (form.value.collect_email && form.value.user_email) respondentEmail.value = form.value.user_email
    // Preview is read-only: no edit-link loading, no view tracking, no submissions list.
    if (!isPreview.value) {
      if (editToken.value && form.value.allow_edit) await loadSubmission()
      if (form.value.storage_mode === 'Linked' && recordName.value && form.value.allow_edit) await loadLinkedRecord()
      loadMySubmissions()
      // Count this open for the completion funnel (fire-and-forget).
      call('forms.api.track_view', { slug: props.slug }).catch(() => {})
    }
  } catch (e) {
    notFound.value = true
  }
}
load()

async function loadSubmission() {
  try {
    const res = await call('forms.api.get_submission', { slug: props.slug, token: editToken.value })
    for (const [fn, v] of Object.entries(res.answers || {})) {
      if (v !== null && v !== undefined) answers[fn] = v
    }
    if (res.respondent_email) respondentEmail.value = res.respondent_email
    // Rebuild "Other" state for any single-choice/dropdown answer outside the option list.
    for (const f of form.value.fields) {
      if ((f.field_type === 'single_choice' || f.field_type === 'dropdown') && f.has_other) {
        const v = answers[f.fieldname]
        if (v != null && v !== '' && !(f.options || []).includes(v)) {
          otherOn[f.fieldname] = true
          otherText[f.fieldname] = v
        }
      }
    }
    editing.value = true
  } catch (e) {
    toast.error('This edit link is no longer valid.')
    editToken.value = null
  }
}

async function loadLinkedRecord() {
  try {
    const res = await call('forms.api.get_linked_record', { slug: props.slug, name: recordName.value })
    for (const [fn, v] of Object.entries(res.answers || {})) {
      if (v !== null && v !== undefined) answers[fn] = v
    }
    for (const f of form.value.fields) {
      if ((f.field_type === 'single_choice' || f.field_type === 'dropdown') && f.has_other) {
        const v = answers[f.fieldname]
        if (v != null && v !== '' && !(f.options || []).includes(v)) {
          otherOn[f.fieldname] = true
          otherText[f.fieldname] = v
        }
      }
    }
    editing.value = true
  } catch (e) {
    toast.error(e.messages?.[0] || 'You cannot edit this record.')
    recordName.value = null
  }
}

async function loadMySubmissions() {
  if (!form.value?.show_my_submissions || !form.value?.user_email) return
  try {
    const res = await call('forms.api.list_my_submissions', { slug: props.slug })
    mySubs.value = res.rows || []
    mySubsMeta.value = { can_edit: res.can_edit, can_delete: res.can_delete }
  } catch (e) { /* not signed in / not permitted — just don't show the list */ }
}
function deleteSub(name) {
  confirmDialog({
    title: 'Delete this response?',
    message: 'This cannot be undone.',
    onConfirm: async ({ hideDialog }) => {
      try {
        await call('forms.api.delete_my_submission', { slug: props.slug, name })
        mySubs.value = mySubs.value.filter((s) => s.name !== name)
        toast.success('Response deleted')
      } catch (e) {
        toast.error(e.messages?.[0] || 'Could not delete this response.')
      }
      hideDialog?.()
    },
  })
}
const editUrl = computed(() => {
  const base = `${window.location.origin}/forms/f/${props.slug}`
  if (editToken.value) return `${base}?edit=${editToken.value}`
  if (recordName.value && form.value?.storage_mode === 'Linked') return `${base}?name=${encodeURIComponent(recordName.value)}`
  return ''
})
function copyEditLink() {
  navigator.clipboard?.writeText(editUrl.value)
  toast.success('Edit link copied')
}

// Section headers carry no answer, and fields hidden by conditional logic don't count.
const questions = computed(() => (form.value?.fields || []).filter((f) => f.field_type !== 'section_header' && isVisible(f)))
const total = computed(() => questions.value.length)
const answered = computed(() =>
  questions.value.filter((f) => {
    const v = answers[f.fieldname]
    return Array.isArray(v) ? v.length : v !== undefined && v !== '' && v !== null
  }).length,
)
// Multi-page forms track progress by page; single-page forms by fields answered.
const pct = computed(() => {
  if (multiPage.value) return Math.round(((currentPage.value + 1) / pages.value.length) * 100)
  return total.value ? Math.round((answered.value / total.value) * 100) : 0
})

function setVal(fn, v) {
  answers[fn] = v
  errors[fn] = false
}
function resetForm() {
  for (const o of [answers, errors, otherOn, otherText, fileNames]) {
    Object.keys(o).forEach((k) => delete o[k])
  }
  respondentEmail.value = form.value?.user_email || ''
  emailError.value = false
  submitResult.value = null
  activeField.value = null
}
// "Submit another response": clear the done/edit state and start a fresh blank form.
function submitAnother() {
  done.value = null
  editToken.value = null
  recordName.value = null
  resetForm()
}
// Email is collected on the first page; validate it there.
function emailOk() {
  if (!form.value.collect_email) return true
  const v = (respondentEmail.value || '').trim()
  if (!v || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) {
    emailError.value = true
    return false
  }
  emailError.value = false
  return true
}

async function uploadFile(f, e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading[f.fieldname] = true
  errors[f.fieldname] = false
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('slug', props.slug)
    fd.append('fieldname', f.fieldname)
    const headers = {}
    if (window.csrf_token && window.csrf_token !== '{{ csrf_token }}') headers['X-Frappe-CSRF-Token'] = window.csrf_token
    const res = await fetch('/api/method/forms.api.upload_submission_file', { method: 'POST', headers, body: fd })
    const json = await res.json()
    if (!res.ok) throw new Error(json?.message || 'Upload failed')
    answers[f.fieldname] = json.message.file_url
    fileNames[f.fieldname] = json.message.file_name
  } catch (err) {
    toast.error('Upload failed — check the file size (max 10 MB) and type.')
  } finally {
    uploading[f.fieldname] = false
    e.target.value = ''
  }
}
function clearFile(f) {
  delete answers[f.fieldname]
  delete fileNames[f.fieldname]
}
function toggleCb(fn, opt) {
  const arr = Array.isArray(answers[fn]) ? [...answers[fn]] : []
  const i = arr.indexOf(opt)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(opt)
  setVal(fn, arr)
}
// Single choice with an "Other" write-in: a normal pick clears Other; Other holds the typed text.
function selectChoice(f, o) { otherOn[f.fieldname] = false; setVal(f.fieldname, o) }
function selectOther(f) { otherOn[f.fieldname] = true; setVal(f.fieldname, otherText[f.fieldname] || '') }
function setOther(f, v) { otherText[f.fieldname] = v; otherOn[f.fieldname] = true; setVal(f.fieldname, v) }
function onDropdown(f, v) {
  if (v === '__other__') { otherOn[f.fieldname] = true; setVal(f.fieldname, otherText[f.fieldname] || '') }
  else { otherOn[f.fieldname] = false; setVal(f.fieldname, v) }
}
// Grids: answers[fieldname] is { row: col } (mc) or { row: [cols] } (checkbox).
function setGridMc(f, row, col) { setVal(f.fieldname, { ...(answers[f.fieldname] || {}), [row]: col }) }
function toggleGridCb(f, row, col) {
  const cur = { ...(answers[f.fieldname] || {}) }
  const arr = Array.isArray(cur[row]) ? [...cur[row]] : []
  const i = arr.indexOf(col)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(col)
  if (arr.length) cur[row] = arr
  else delete cur[row]
  setVal(f.fieldname, cur)
}

async function submit() {
  if (isPreview.value) { toast.info("This is a preview — responses aren’t saved."); return }
  if (!emailOk()) { currentPage.value = 0; window.scrollTo({ top: 0, behavior: 'smooth' }); return }
  // Validate every page; on failure jump to the first page that has an error.
  for (let i = 0; i < pages.value.length; i++) {
    if (!validatePage(i)) {
      currentPage.value = i
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
  }
  submitting.value = true
  try {
    // Encrypted form: seal the collected email in-browser to the creator's public key and send only
    // the ciphertext — the plaintext email never touches the network or the server.
    let encIdentity
    let plainEmail = form.value.collect_email ? (respondentEmail.value || '').trim() : undefined
    if (form.value.encrypted) {
      // Fail closed: an encrypted form with no public key must not fall through and leak the
      // plaintext email — abort the submit instead.
      if (!form.value.enc_public_key) throw new Error('This form is misconfigured for encryption. Please contact the form owner.')
      encIdentity = await sealIdentity(form.value.enc_public_key, {
        email: plainEmail || null,
        user: form.value.user_email || null,
      })
      plainEmail = undefined // never send the plaintext address for an encrypted form
    }
    const res = await call('forms.api.submit', {
      slug: props.slug,
      data: JSON.stringify(answers),
      hp: hp.value,
      token: editToken.value || undefined,
      record: recordName.value || undefined,
      email: plainEmail,
      enc_identity: encIdentity,
    })
    submitResult.value = res
    if (res.token) editToken.value = res.token
    // Linked + editable + signed in: expose a return-to-edit link for the new record.
    if (form.value.storage_mode === 'Linked' && form.value.allow_edit && form.value.user_email) {
      recordName.value = res.name
    }
    // Redirect to the configured URL if set (overrides the thank-you screen).
    const url = (form.value.redirect_url || '').trim()
    if (url && /^(https?:\/\/|\/)/.test(url)) {
      done.value = res.name
      redirecting.value = true
      setTimeout(() => { window.location.href = url }, 900)
      return
    }
    done.value = res.name
    loadMySubmissions() // keep the respondent's list fresh for when they return
  } catch (e) {
    toast.error(e.messages?.[0] || 'Submission failed. Please check your answers.')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="min-h-full overflow-auto bg-surface-gray-1" :data-accent="form?.accent || 'blue'">
    <!-- builder preview: minimal floating indicator, read-only, no submission -->
    <div v-if="isPreview" title="Preview — responses aren’t saved"
         class="fixed bottom-5 right-5 z-30 flex items-center justify-center h-8 w-8 rounded-full bg-surface-base text-ink-gray-5 border border-outline-gray-2 shadow-sm">
      <Icon name="eye" :size="14" />
    </div>

    <div v-if="notFound" class="flex flex-col items-center justify-center h-screen text-center px-6">
      <Icon name="file-question" :size="34" class="text-ink-gray-4" />
      <h1 class="text-xl font-semibold text-ink-gray-9 mt-3">Form not available</h1>
      <p class="text-sm text-ink-gray-5 mt-1">This form doesn’t exist or isn’t published yet.</p>
    </div>

    <!-- form closed: outside its open/close window, or at its response limit -->
    <div v-else-if="closed" class="flex flex-col items-center justify-center h-screen text-center px-6">
      <Icon name="lock" :size="34" class="text-ink-gray-4" />
      <h1 class="text-xl font-semibold text-ink-gray-9 mt-3">{{ form.title }}</h1>
      <p class="text-sm text-ink-gray-5 mt-1 max-w-[420px]">{{ form.closed_reason || 'This form is not accepting responses.' }}</p>
    </div>

    <template v-else-if="form">
      <!-- progress -->
      <ProgressBar :show="form.show_progress !== 0" :pct="pct" :done="!!done" />

      <div class="max-w-[672px] mx-auto px-3 pt-8 pb-16 sm:px-5">
        <template v-if="!done">
          <img v-if="form.cover_image" :src="form.cover_image" alt="" class="w-full h-[180px] object-cover rounded-xl mb-6" />
          <div class="mb-7">
            <h1 class="text-2xl font-semibold text-ink-gray-9 tracking-tight">{{ form.title }}</h1>
            <p v-if="form.description" class="text-base text-ink-gray-6 mt-2">{{ form.description }}</p>
            <p class="text-sm text-ink-gray-5 mt-3.5"><span class="text-ink-red-400">*</span> Indicates a required question</p>
          </div>

          <!-- the signed-in respondent's own past submissions -->
          <SubmissionsList :subs="mySubs" :meta="mySubsMeta" :slug="slug" @delete="deleteSub" />

          <div class="public-card flex flex-col gap-4">
            <!-- honeypot -->
            <input v-model="hp" type="text" tabindex="-1" autocomplete="off"
                   class="absolute opacity-0 pointer-events-none -z-10 h-0 w-0" aria-hidden="true" />

            <!-- page heading (from the section_header that starts this page): a bare label above the cards -->
            <div v-if="page.header" class="px-1 pt-1">
              <h2 class="text-lg font-semibold text-ink-gray-9">{{ page.header.label }}</h2>
              <p v-if="page.header.help_text" class="text-sm text-ink-gray-5 mt-1">{{ page.header.help_text }}</p>
            </div>

            <!-- email capture (first page only) -->
            <div v-if="form.collect_email && currentPage === 0" class="r-card"
                 :class="{ active: activeField === '__email__', invalid: emailError }"
                 @focusin="activeField = '__email__'" @pointerdown="activeField = '__email__'">
              <div class="flex flex-col gap-2.5">
                <div class="flex flex-col gap-1">
                  <span class="text-md font-medium text-ink-gray-9 leading-snug">Email<span class="text-ink-red-400 ml-0.5">*</span></span>
                  <span class="text-sm text-ink-gray-5 leading-snug">Recorded with your response.</span>
                </div>
                <FormControl type="email" size="lg" placeholder="name@example.com"
                       :modelValue="respondentEmail" @update:modelValue="respondentEmail = $event; emailError = false" />
                <span v-if="emailError" class="text-xs text-ink-red-500 flex items-center gap-1">
                  <Icon name="circle-alert" :size="12" />Enter a valid email address.
                </span>
              </div>
            </div>

            <!-- one card per question -->
            <div v-for="f in visibleFields(page.fields)" :key="f.fieldname" class="r-card"
                 :class="{ active: activeField === f.fieldname, invalid: !!errors[f.fieldname] }"
                 @focusin="activeField = f.fieldname" @pointerdown="activeField = f.fieldname">
              <RespondentField
                :field="f" :value="answers[f.fieldname]" :options="optionMap[f.fieldname]"
                :error="errors[f.fieldname]" :otherOn="!!otherOn[f.fieldname]" :otherText="otherText[f.fieldname]"
                :uploading="!!uploading[f.fieldname]" :fileName="fileNames[f.fieldname]"
                @set="setVal(f.fieldname, $event)"
                @toggleCb="toggleCb(f.fieldname, $event)"
                @selectChoice="selectChoice(f, $event)"
                @selectOther="selectOther(f)"
                @setOther="setOther(f, $event)"
                @onDropdown="onDropdown(f, $event)"
                @setGridMc="setGridMc(f, $event.row, $event.col)"
                @toggleGridCb="toggleGridCb(f, $event.row, $event.col)"
                @upload="uploadFile(f, $event)"
                @clearFile="clearFile(f)" />
            </div>

            <!-- footer: submit / navigation in its own quiet card -->
            <div class="r-card">
              <PageNav :multiPage="multiPage" :currentPage="currentPage" :isLastPage="isLastPage"
                       :submitting="submitting" :editing="editing" :pageCount="pages.length"
                       @prev="prevPage" @next="nextPage" @submit="submit" @reset="resetForm" />
            </div>
          </div>

          <div class="flex flex-col gap-0.5 mt-4 px-1 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
            <span class="text-xs text-ink-gray-5 font-medium">Frappe Forms</span>
            <span class="text-xs text-ink-gray-4">Never submit passwords through Frappe Forms.</span>
          </div>
        </template>

        <!-- success -->
        <SuccessScreen v-else :form="form" :editing="editing" :submitResult="submitResult"
                       :redirecting="redirecting" :editUrl="editUrl"
                       @copy="copyEditLink" @another="submitAnother" />
      </div>
    </template>
  </div>
</template>
