<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, DatePicker, FormControl, TimePicker, confirmDialog, toast } from 'frappe-ui'
import { call } from '../data/call'
import Icon from '../components/Icon.vue'
import SignaturePad from '../components/SignaturePad.vue'

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

const page = computed(() => pages.value[currentPage.value] || { header: null, fields: [] })
const multiPage = computed(() => pages.value.length > 1)
const isLastPage = computed(() => currentPage.value >= pages.value.length - 1)

function validatePage(idx) {
  let ok = true
  for (const f of pages.value[idx]?.fields || []) {
    const res = validateField(f)
    if (res) { errors[f.fieldname] = res; ok = false }
  }
  return ok
}
function nextPage() {
  if (currentPage.value === 0 && !emailOk()) return
  if (!validatePage(currentPage.value)) return
  if (currentPage.value < pages.value.length - 1) {
    currentPage.value++
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}
function prevPage() {
  if (currentPage.value > 0) {
    currentPage.value--
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function scaleRange(f) {
  let lo = Number.isFinite(+f.scale_min) ? +f.scale_min : 1
  let hi = Number.isFinite(+f.scale_max) ? +f.scale_max : 5
  if (hi <= lo || hi - lo > 14) { lo = 1; hi = 5 }
  return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
}

async function load() {
  try {
    const endpoint = isPreview.value ? 'forms.admin.preview_form' : 'forms.api.get_public_form'
    form.value = await call(endpoint, { slug: props.slug })
    buildPresentation()
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
function fmtDate(dt) {
  if (!dt) return ''
  try { return new Date(dt.replace(' ', 'T')).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) } catch { return dt }
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

// Section headers carry no answer - exclude them from the progress count.
const questions = computed(() => (form.value?.fields || []).filter((f) => f.field_type !== 'section_header'))
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
function gridMcChecked(f, row, col) { return (answers[f.fieldname] || {})[row] === col }
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
function gridCbChecked(f, row, col) {
  const v = (answers[f.fieldname] || {})[row]
  return Array.isArray(v) && v.includes(col)
}

// Mirror the server's validation client-side: false = ok, true = required, string = specific message.
function validateField(f) {
  const v = answers[f.fieldname]
  const empty = Array.isArray(v) ? !v.length
    : v && typeof v === 'object' ? !Object.keys(v).length
    : v === undefined || v === '' || v === null
  if (empty) return !!f.reqd
  if (f.field_type === 'number') {
    const n = Number(v)
    const lo = f.min_value !== '' && f.min_value != null ? Number(f.min_value) : null
    const hi = f.max_value !== '' && f.max_value != null ? Number(f.max_value) : null
    if (lo != null && n < lo) return f.error_message || `Must be at least ${lo}.`
    if (hi != null && n > hi) return f.error_message || `Must be at most ${hi}.`
  }
  if (['short_answer', 'paragraph', 'address'].includes(f.field_type)) {
    if (f.max_length && String(v).length > f.max_length) return f.error_message || `Must be at most ${f.max_length} characters.`
    if (f.validation_pattern) {
      let ok = true
      try { ok = new RegExp(`^(?:${f.validation_pattern})$`).test(String(v)) } catch { ok = true }
      if (!ok) return f.error_message || 'Not in the expected format.'
    }
  }
  return false
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
    const res = await call('forms.api.submit', {
      slug: props.slug,
      data: JSON.stringify(answers),
      hp: hp.value,
      token: editToken.value || undefined,
      record: recordName.value || undefined,
      email: form.value.collect_email ? (respondentEmail.value || '').trim() : undefined,
    })
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
         class="fixed bottom-5 right-5 z-30 flex items-center justify-center h-8 w-8 rounded-full bg-surface-white text-ink-gray-5 border border-outline-gray-2 shadow-sm">
      <Icon name="eye" :size="14" />
    </div>

    <div v-if="notFound" class="flex flex-col items-center justify-center h-screen text-center px-6">
      <Icon name="file-question" :size="34" class="text-ink-gray-4" />
      <h1 class="text-xl text-ink-gray-9 mt-3">Form not available</h1>
      <p class="text-sm text-ink-gray-5 mt-1">This form doesn’t exist or isn’t published yet.</p>
    </div>

    <template v-else-if="form">
      <!-- progress -->
      <div v-if="form.show_progress !== 0" class="h-[3px] bg-surface-gray-2 sticky top-0 z-10">
        <div class="h-full transition-all" :style="{ width: `${done ? 100 : pct}%`, background: 'var(--accent)' }" />
      </div>

      <div class="max-w-[600px] mx-auto px-3 pt-8 pb-16 sm:px-5">
        <template v-if="!done">
          <img v-if="form.cover_image" :src="form.cover_image" alt="" class="w-full h-[180px] object-cover rounded-xl mb-6" />
          <div class="mb-7">
            <h1 class="text-2xl font-semibold text-ink-gray-9 tracking-tight">{{ form.title }}</h1>
            <p v-if="form.description" class="text-base text-ink-gray-6 mt-2">{{ form.description }}</p>
            <p class="text-sm text-ink-gray-5 mt-3.5"><span class="text-ink-red-500">*</span> Indicates a required question</p>
          </div>

          <!-- the signed-in respondent's own past submissions -->
          <div v-if="mySubs.length" class="public-card p-4 mb-4 sm:p-5">
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-sm font-medium text-ink-gray-9">Your responses</span>
              <span class="text-xs text-ink-gray-5">{{ mySubs.length }}</span>
            </div>
            <div class="flex flex-col divide-y divide-outline-gray-1">
              <div v-for="s in mySubs" :key="s.name" class="flex items-center gap-3 py-2.5">
                <div class="flex flex-col min-w-0 flex-1">
                  <span class="text-sm text-ink-gray-8 truncate">{{ s.label }}</span>
                  <span class="text-[11px] text-ink-gray-5">{{ fmtDate(s.creation) }}</span>
                </div>
                <a v-if="s.edit_param && mySubsMeta.can_edit" :href="`/forms/f/${slug}?${s.edit_param}`"
                   class="text-sm text-ink-gray-7 hover:text-ink-gray-9">Edit</a>
                <button v-if="mySubsMeta.can_delete" type="button" class="text-sm text-ink-red-500 hover:text-ink-red-600" @click="deleteSub(s.name)">Delete</button>
              </div>
            </div>
          </div>

          <div class="public-card p-5 sm:p-7">
            <!-- honeypot -->
            <input v-model="hp" type="text" tabindex="-1" autocomplete="off"
                   class="absolute opacity-0 pointer-events-none -z-10 h-0 w-0" aria-hidden="true" />

            <!-- email capture (first page only) -->
            <div v-if="form.collect_email && currentPage === 0" class="flex flex-col gap-2 mb-6">
              <div class="flex flex-col gap-0.5">
                <span class="text-[15px] font-medium text-ink-gray-9">Email<span class="text-ink-red-500 ml-0.5">*</span></span>
                <span class="text-sm text-ink-gray-5">Recorded with your response.</span>
              </div>
              <FormControl type="email" size="lg" placeholder="name@example.com"
                     :modelValue="respondentEmail" @update:modelValue="respondentEmail = $event; emailError = false" />
              <span v-if="emailError" class="text-xs text-ink-red-500 flex items-center gap-1">
                <Icon name="circle-alert" :size="12" />Enter a valid email address.
              </span>
            </div>

            <!-- page heading (from the section_header that starts this page) -->
            <div v-if="page.header" class="mb-6">
              <h2 class="text-lg font-semibold text-ink-gray-9">{{ page.header.label }}</h2>
              <p v-if="page.header.help_text" class="text-sm text-ink-gray-5 mt-1">{{ page.header.help_text }}</p>
            </div>

            <template v-for="f in page.fields" :key="f.fieldname">
            <div class="flex flex-col gap-2 mb-6">
              <div class="flex flex-col gap-0.5">
                <span class="text-[15px] font-medium text-ink-gray-9">
                  {{ f.label }}<span v-if="f.reqd" class="text-ink-red-500 ml-0.5">*</span>
                </span>
                <span v-if="f.help_text" class="text-sm text-ink-gray-5">{{ f.help_text }}</span>
              </div>

              <FormControl v-if="f.field_type === 'short_answer'" type="text" size="lg" placeholder="Your answer"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'email'" type="email" size="lg" placeholder="name@example.com"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'number'" type="number" size="lg" placeholder="0"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'phone'" type="tel" size="lg" placeholder="+1 (555) 000-0000"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <div v-else-if="f.field_type === 'time'" class="r-picker">
                <TimePicker placeholder="Select time"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              </div>
              <FormControl v-else-if="f.field_type === 'paragraph'" type="textarea" size="lg" :rows="4" placeholder="Your answer"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'address'" type="textarea" size="lg" :rows="3" placeholder="Street, city, state, ZIP"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <div v-else-if="f.field_type === 'date'" class="r-picker">
                <DatePicker placeholder="Select date"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              </div>
              <template v-else-if="f.field_type === 'dropdown'">
                <FormControl type="select" size="lg"
                     :options="[{ label: 'Choose an option', value: '' }, ...optionMap[f.fieldname].map((o) => ({ label: o, value: o })), ...(f.has_other ? [{ label: 'Other…', value: '__other__' }] : [])]"
                     :modelValue="otherOn[f.fieldname] ? '__other__' : (answers[f.fieldname] || '')" @update:modelValue="onDropdown(f, $event)" />
                <FormControl v-if="f.has_other && otherOn[f.fieldname]" type="text" size="lg" placeholder="Your answer"
                     :modelValue="otherText[f.fieldname] || ''" @update:modelValue="setOther(f, $event)" />
              </template>

              <!-- file upload -->
              <label v-else-if="f.field_type === 'file_upload'"
                     class="flex items-center gap-2.5 h-10 px-3 rounded-md bg-surface-gray-2 hover:bg-surface-gray-3 transition-colors cursor-pointer">
                <input type="file" class="hidden" @change="uploadFile(f, $event)" />
                <Icon :name="answers[f.fieldname] ? 'file-check-2' : 'paperclip'" :size="16" class="text-ink-gray-6 shrink-0" />
                <span class="text-base text-ink-gray-8 truncate flex-1">
                  {{ uploading[f.fieldname] ? 'Uploading…' : (fileNames[f.fieldname] || 'Choose a file') }}
                </span>
                <button v-if="answers[f.fieldname]" type="button" class="text-ink-gray-4 hover:text-ink-gray-7 shrink-0" @click.prevent.stop="clearFile(f)"><Icon name="x" :size="15" /></button>
              </label>

              <!-- signature -->
              <SignaturePad v-else-if="f.field_type === 'signature'"
                     :modelValue="answers[f.fieldname]" @update:modelValue="setVal(f.fieldname, $event)" />

              <div v-else-if="f.field_type === 'rating'" class="flex gap-1">
                <span v-for="s in 5" :key="s" class="star" :class="{ on: s <= (answers[f.fieldname] || 0) }" @click="setVal(f.fieldname, s)">
                  <Icon name="star" :size="28" :style="{ fill: s <= (answers[f.fieldname] || 0) ? 'var(--amber-500)' : 'none' }" />
                </span>
              </div>

              <div v-else-if="f.field_type === 'linear_scale'" class="flex items-center gap-x-4 gap-y-2 flex-wrap pt-1">
                <span v-if="f.min_label" class="text-sm text-ink-gray-6 shrink-0">{{ f.min_label }}</span>
                <div class="flex items-center gap-3">
                  <button v-for="n in scaleRange(f)" :key="n" type="button" class="flex flex-col items-center gap-1.5"
                          @click="setVal(f.fieldname, n)">
                    <span class="text-[13px] text-ink-gray-7">{{ n }}</span>
                    <span class="r-radio" :style="answers[f.fieldname] === n ? 'border-color:var(--accent)' : ''">
                      <span v-if="answers[f.fieldname] === n" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" />
                    </span>
                  </button>
                </div>
                <span v-if="f.max_label" class="text-sm text-ink-gray-6 shrink-0">{{ f.max_label }}</span>
              </div>

              <div v-else-if="f.field_type === 'mc_grid' || f.field_type === 'checkbox_grid'" class="overflow-x-auto -mx-1 px-1">
                <table class="r-grid">
                  <thead>
                    <tr>
                      <th></th>
                      <th v-for="col in f.options" :key="col" class="px-3 pb-2 text-sm font-normal text-ink-gray-6 text-center">{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in f.grid_rows" :key="row" class="border-t border-outline-gray-1">
                      <td class="py-2.5 pr-4 text-base text-ink-gray-8">{{ row }}</td>
                      <td v-for="col in f.options" :key="col" class="px-3 text-center">
                        <button v-if="f.field_type === 'mc_grid'" type="button" class="r-radio mx-auto"
                                :style="gridMcChecked(f, row, col) ? 'border-color:var(--accent)' : ''" @click="setGridMc(f, row, col)">
                          <span v-if="gridMcChecked(f, row, col)" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" />
                        </button>
                        <button v-else type="button" class="r-cb mx-auto" :class="{ 'grid-cb-on': gridCbChecked(f, row, col) }" @click="toggleGridCb(f, row, col)">
                          <Icon v-if="gridCbChecked(f, row, col)" name="check" :size="12" />
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-else-if="f.field_type === 'yes_no'" class="flex gap-2">
                <div v-for="o in ['Yes', 'No']" :key="o" class="r-choice min-w-[92px] flex-none"
                     :class="{ sel: answers[f.fieldname] === o }" @click="setVal(f.fieldname, o)">
                  <span class="r-radio"><span v-if="answers[f.fieldname] === o" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
                  <span class="text-base text-ink-gray-8">{{ o }}</span>
                </div>
              </div>

              <div v-else-if="f.field_type === 'single_choice'" class="flex flex-col gap-2">
                <div v-for="o in optionMap[f.fieldname]" :key="o" class="r-choice"
                     :class="{ sel: !otherOn[f.fieldname] && answers[f.fieldname] === o }" @click="selectChoice(f, o)">
                  <span class="r-radio"><span v-if="!otherOn[f.fieldname] && answers[f.fieldname] === o" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
                  <span class="text-base text-ink-gray-8">{{ o }}</span>
                </div>
                <div v-if="f.has_other" class="r-choice" :class="{ sel: otherOn[f.fieldname] }" @click="selectOther(f)">
                  <span class="r-radio"><span v-if="otherOn[f.fieldname]" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
                  <span class="text-base text-ink-gray-8 shrink-0">Other:</span>
                  <input class="ml-1 flex-1 bg-transparent outline-none border-b border-outline-gray-2 focus:border-outline-gray-4 text-base text-ink-gray-8 py-0.5"
                         :value="otherText[f.fieldname] || ''" placeholder="Your answer"
                         @click.stop @input="setOther(f, $event.target.value)" />
                </div>
              </div>

              <div v-else-if="f.field_type === 'checkboxes'" class="flex flex-col gap-2">
                <div v-for="o in optionMap[f.fieldname]" :key="o" class="r-choice"
                     :class="{ sel: (answers[f.fieldname] || []).includes(o) }" @click="toggleCb(f.fieldname, o)">
                  <span class="r-cb"><Icon v-if="(answers[f.fieldname] || []).includes(o)" name="check" :size="12" /></span>
                  <span class="text-base text-ink-gray-8">{{ o }}</span>
                </div>
              </div>

              <span v-if="errors[f.fieldname]" class="text-xs text-ink-red-500 flex items-center gap-1">
                <Icon name="circle-alert" :size="12" />{{ typeof errors[f.fieldname] === 'string' ? errors[f.fieldname] : 'This field is required.' }}
              </span>
            </div>
            </template>

            <div class="flex items-center justify-between border-t border-outline-gray-1 pt-5 mt-1">
              <div class="flex items-center gap-2">
                <Button v-if="multiPage && currentPage > 0" variant="outline" theme="gray" size="lg" @click="prevPage">Back</Button>
                <Button v-if="!isLastPage" variant="solid" theme="gray" size="lg" @click="nextPage">Next</Button>
                <Button v-else variant="solid" theme="gray" size="lg" :loading="submitting" @click="submit">{{ editing ? 'Update' : 'Submit' }}</Button>
              </div>
              <span v-if="multiPage" class="text-sm text-ink-gray-5">Page {{ currentPage + 1 }} of {{ pages.length }}</span>
              <button v-else class="text-sm text-ink-gray-5" @click="resetForm">Clear form</button>
            </div>
          </div>

          <div class="flex flex-col gap-0.5 mt-4 px-1 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
            <span class="text-xs text-ink-gray-5 font-medium">Frappe Forms</span>
            <span class="text-xs text-ink-gray-4">Never submit passwords through Frappe Forms.</span>
          </div>
        </template>

        <!-- success -->
        <div v-else class="public-card text-center px-5 py-12 sm:px-8">
          <span class="w-[52px] h-[52px] rounded-[14px] bg-surface-green-2 flex items-center justify-center mx-auto text-green-600">
            <Icon name="check" :size="26" />
          </span>
          <h2 class="text-xl font-semibold text-ink-gray-9 mt-4">{{ editing ? 'Response updated' : 'Response received' }}</h2>
          <p v-if="redirecting" class="text-base text-ink-gray-6 mt-2 flex items-center justify-center gap-2">
            <Icon name="loader" :size="16" class="animate-spin" />Redirecting you now…
          </p>
          <p v-else class="text-base text-ink-gray-6 mt-2 max-w-[420px] mx-auto">
            {{ form.thank_you_message || 'Thanks! Your response has been recorded.' }}
          </p>

          <div v-if="form.allow_edit && editUrl && !redirecting" class="mt-5 mx-auto max-w-[440px] text-left bg-surface-gray-1 rounded-lg p-3.5">
            <div class="flex items-center gap-1.5 text-sm text-ink-gray-7 mb-2"><Icon name="pencil" :size="13" />Edit your response later</div>
            <div class="flex items-center gap-2">
              <input readonly class="cfg-input flex-1 text-[12px]" :value="editUrl" @focus="$event.target.select()" />
              <Button variant="subtle" theme="gray" @click="copyEditLink">Copy</Button>
            </div>
          </div>

          <Button v-if="!redirecting && !editing" variant="outline" theme="gray" class="mt-6" @click="done = null; editToken = null; recordName = null; resetForm()">
            Submit another response
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
