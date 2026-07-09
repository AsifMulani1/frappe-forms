<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dropdown, Tooltip, confirmDialog, toast } from 'frappe-ui'
import { call } from '../data/call'
import Icon from '../components/Icon.vue'
import ShareDialog from '../components/ShareDialog.vue'
import Canvas from '../components/builder/Canvas.vue'
import Inspector from '../components/builder/Inspector.vue'
import FormSettingsDialog from '../components/builder/FormSettingsDialog.vue'
import DevPanel from '../components/builder/DevPanel.vue'
import { FT, hasOptions, isGrid } from '../fieldTypes'
import { prefs, toggleDevMode } from '../data/prefs'
import { useAutosave } from '../data/useAutosave'

const props = defineProps({ slug: String })
const router = useRouter()

const form = reactive({ fields: [] })
const selectedId = ref(null)
const devOpen = ref(false)
const settingsOpen = ref(false)
const loaded = ref(false)
const notFound = ref(false)
let tmpSeq = 0

async function load() {
  try {
    Object.assign(form, await call('forms.admin.get_form', { slug: props.slug }))
    loaded.value = true
  } catch (e) {
    // Missing/renamed slug (stale link, deleted form): show a not-found state instead of
    // hanging on "Loading builder…" with an unhandled rejection.
    notFound.value = true
  }
}
load()

const { saveState, schedule: scheduleSave, flush: flushSave } = useAutosave({
  save: persist,
  isReady: () => loaded.value,
  beacon: saveBeacon,
})

const selectedField = computed(() => form.fields.find((f) => f.name === selectedId.value) || null)

// The full-document payload. Shared by the debounced save and the unload beacon.
function savePayload() {
  return {
    title: form.title, description: form.description, accent: form.accent,
    storage_mode: form.storage_mode, target_doctype: form.target_doctype,
    login_required: form.login_required, allow_multiple: form.allow_multiple,
    collect_email: form.collect_email, thank_you_message: form.thank_you_message,
    redirect_url: form.redirect_url, cover_image: form.cover_image, category: form.category,
    is_template: form.is_template, shuffle_questions: form.shuffle_questions,
    show_progress: form.show_progress, email_receipt: form.email_receipt, allow_edit: form.allow_edit,
    apply_doc_perms: form.apply_doc_perms, show_my_submissions: form.show_my_submissions,
    allow_delete: form.allow_delete,
    notify_on_response: form.notify_on_response, notify_email: form.notify_email,
    opens_on: form.opens_on, closes_on: form.closes_on, response_limit: form.response_limit,
    is_quiz: form.is_quiz, show_score: form.show_score,
    fields: form.fields,
  }
}

// Persist the whole document, then reconcile server-owned identity in place. We never reassign
// form.fields or the meta text fields, so the inputs the user is typing in aren't torn down.
async function persist() {
  // Snapshot the rows we're persisting (by reference, in send order) so we can map the
  // server-assigned names back onto them without clobbering edits made during the round-trip.
  const sent = form.fields.slice()
  const data = await call('forms.admin.save_form', {
    name: form.name,
    data: JSON.stringify(savePayload()),
  })
  form.name = data.name
  // A Draft's slug tracks its title, so renaming changes it. Keep the /:slug/edit URL in sync
  // (replace, not push) so the address bar stays correct and a reload still resolves the form.
  if (data.slug !== form.slug && router.currentRoute.value.name === 'Builder') {
    router.replace({ name: 'Builder', params: { slug: data.slug } })
  }
  form.slug = data.slug
  form.status = data.status
  form.doctype_name = data.doctype_name
  data.fields.forEach((row, i) => {
    const local = sent[i]
    if (!local) return
    if (local.name !== row.name) {
      if (selectedId.value === local.name) selectedId.value = row.name
      local.name = row.name // tmp-N → persisted row name
    }
    local.fieldname = row.fieldname // frozen on publish; echoed back otherwise
  })
}

// Last-ditch save when the tab is hidden/closed before the debounce fires. sendBeacon survives
// unload (a normal fetch would be cancelled); Frappe accepts the CSRF token as a form field.
function saveBeacon() {
  if (!loaded.value || !form.name) return
  const fd = new FormData()
  fd.append('name', form.name)
  fd.append('data', JSON.stringify(savePayload()))
  if (window.csrf_token && window.csrf_token !== '{{ csrf_token }}') fd.append('csrf_token', window.csrf_token)
  navigator.sendBeacon('/api/method/forms.admin.save_form', fd)
}

function updateMeta(patch) { Object.assign(form, patch); scheduleSave() }
function updateField(name, patch) {
  const f = form.fields.find((x) => x.name === name)
  if (f) Object.assign(f, patch)
  scheduleSave()
}
function addField(typeId, index) {
  const t = FT[typeId]
  const f = {
    name: `tmp-${++tmpSeq}`, label: `Untitled ${t.label.toLowerCase()}`, field_type: typeId,
    reqd: 0, help_text: '',
    options: isGrid(typeId) ? 'Column 1\nColumn 2\nColumn 3' : hasOptions(typeId) ? 'Option 1\nOption 2\nOption 3' : '',
    grid_rows: isGrid(typeId) ? 'Row 1\nRow 2' : '',
    mapped_field: '', fieldname: '', field_key: '',
    has_other: 0, shuffle_options: 0, min_value: '', max_value: '', max_length: 0,
    validation_pattern: '', error_message: '', scale_min: 1, scale_max: 5, min_label: '', max_label: '',
    condition_field: '', condition_operator: 'equals', condition_value: '', points: 0, correct_answer: '',
  }
  // index given (insert-between) → place there; otherwise append.
  if (index == null || index >= form.fields.length) form.fields.push(f)
  else form.fields.splice(Math.max(0, index), 0, f)
  selectedId.value = f.name
  scheduleSave()
}
function removeField(name) {
  const i = form.fields.findIndex((f) => f.name === name)
  if (i >= 0) form.fields.splice(i, 1)
  if (selectedId.value === name) selectedId.value = null
  scheduleSave()
}
function deleteField(name) {
  const f = form.fields.find((x) => x.name === name)
  if (f && f.fieldname) {
    confirmDialog({
      title: 'Delete this field?',
      message: `“${f.label}” is published. Its column is kept (hidden), but it’s removed from the form.`,
      onConfirm: ({ hideDialog }) => { removeField(name); hideDialog?.() },
    })
  } else {
    removeField(name)
  }
}
function duplicateField(name) {
  const i = form.fields.findIndex((f) => f.name === name)
  if (i < 0) return
  form.fields.splice(i + 1, 0, { ...form.fields[i], name: `tmp-${++tmpSeq}`, fieldname: '', field_key: '' })
  scheduleSave()
}
function moveField(name, dir) {
  const i = form.fields.findIndex((f) => f.name === name)
  const j = i + dir
  if (j < 0 || j >= form.fields.length) return
  ;[form.fields[i], form.fields[j]] = [form.fields[j], form.fields[i]]
  scheduleSave()
}
function reorder(from, to) {
  if (from === to || to < 0 || to >= form.fields.length) return
  const [moved] = form.fields.splice(from, 1)
  form.fields.splice(to, 0, moved)
  scheduleSave()
}

function publish() {
  // Name-check up front so an unnamed form prompts immediately, rather than confirm-then-error.
  // (The server enforces this too — this is just the friendlier path.)
  const title = (form.title || '').trim()
  if (!title || title.toLowerCase() === 'untitled form') {
    toast.error('Give your form a name before publishing — it becomes its link and DocType name.')
    return
  }
  confirmDialog({
    title: 'Publish this form?',
    message: form.storage_mode === 'Linked'
      ? `Submissions will be saved as ${form.target_doctype} records. Field names freeze now.`
      : 'Your form goes live and anyone with the link can respond. Question types lock once it’s published, so add the fields you need first.',
    onConfirm: async ({ hideDialog }) => {
      await flushSave()
      try {
        const res = await call('forms.admin.publish_form', { name: form.name })
        Object.assign(form, { status: 'Published', doctype_name: res.doctype_name })
        await load()
        toast.success('Published')
      } catch (e) {
        toast.error(e.messages?.[0] || 'Could not publish')
      }
      hideDialog?.()
    },
  })
}

function preview() {
  // Flush the latest edits, then open the respondent view in read-only preview mode (works on Drafts).
  flushSave()
  window.open(`/forms/f/${form.slug}?preview=1`, '_blank')
}
function copyLink() {
  navigator.clipboard?.writeText(`${location.origin}/forms/f/${form.slug}`)
  toast.success('Link copied')
}

// topbar actions
async function duplicate() {
  const doc = await call('forms.admin.duplicate_form', { name: form.name })
  toast.success('Form duplicated')
  router.push(`/${doc.slug}/edit`)
}
function archive() {
  confirmDialog({
    title: 'Archive this form?',
    message: 'It moves to Archived. Responses are kept and nothing is deleted.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.set_archived', { name: form.name, archived: 1 })
      toast.success('Form archived')
      hideDialog?.()
      router.push({ path: '/', query: { view: 'archived' } })
    },
  })
}
function deleteForm() {
  confirmDialog({
    title: 'Delete this form?',
    message: form.status === 'Published'
      ? 'This permanently deletes the form and every response collected. This cannot be undone.'
      : 'This permanently deletes the form. This cannot be undone.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.delete_form', { name: form.name })
      toast.success('Form deleted')
      hideDialog?.()
      router.push('/')
    },
  })
}
const menu = computed(() => [
  // Form settings has its own standing gear in the header (left of preview); not duplicated here.
  { label: 'Duplicate', icon: 'copy', onClick: duplicate },
  { label: 'Share', icon: 'user-plus', onClick: () => openShare() },
  // quick copy stays available for published forms (Share dialog has it too)
  ...(form.status === 'Published' ? [{ label: 'Copy link', icon: 'link', onClick: copyLink }] : []),
  { label: form.is_template ? 'Unmark template' : 'Mark as template', icon: 'lucide-layout-template',
    onClick: () => updateMeta({ is_template: form.is_template ? 0 : 1 }) },
  { label: 'Archive', icon: 'archive', onClick: archive },
  { label: 'Developer mode', icon: prefs.devMode ? 'lucide-check' : 'lucide-code', onClick: toggleDevMode },
  { label: 'Delete', icon: 'trash-2', theme: 'red', onClick: deleteForm },
])

// share dialog (shared ShareDialog component)
const shareOpen = ref(false)
function openShare() { shareOpen.value = true }
</script>

<template>
  <div v-if="loaded" class="flex flex-col h-full w-full" :data-accent="form.accent" @focusout="flushSave">
    <div class="h-[48px] border-b border-outline-gray-1 bg-surface-base flex items-center px-3.5 shrink-0 relative">
      <!-- left: back + title + a quiet status dot -->
      <div class="flex items-center gap-2.5 min-w-0">
        <button class="flex items-center gap-1.5 px-2 h-8 rounded-md hover:bg-surface-gray-2 text-ink-gray-7 shrink-0 transition-colors" title="Back to all forms" @click="router.push('/')">
          <Icon name="clipboard-list" :size="15" />
          <span class="text-sm font-medium">Forms</span>
        </button>
        <Icon name="chevron-right" :size="15" class="text-ink-gray-4 shrink-0" />
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-sm font-medium text-ink-gray-9 truncate max-w-[260px]">{{ form.title }}</span>
          <Badge :theme="form.status === 'Published' ? 'green' : 'gray'" :label="form.status" />
        </div>
      </div>

      <!-- center: the page switch, anchored to the true center of the bar -->
      <div class="segmented absolute left-1/2 -translate-x-1/2">
        <span class="seg-btn active">Edit</span>
        <span class="seg-btn" @click="router.push(`/${form.slug}/responses`)">Responses</span>
      </div>

      <!-- right: autosave state, settings, preview, overflow, single primary action -->
      <div class="flex items-center gap-1.5 ml-auto">
        <span class="text-[11px] text-ink-gray-4 flex items-center gap-1 mr-1 w-[52px] justify-end">
          <template v-if="saveState === 'saving'"><Icon name="loader" :size="12" class="animate-spin" />Saving</template>
          <template v-else-if="saveState === 'saved'"><Icon name="check" :size="12" class="text-ink-green-600" />Saved</template>
        </span>
        <!-- Form settings: one home in every mode. Dev mode gets an extra Developer tab inside. -->
        <Tooltip text="Form settings">
          <Button variant="ghost" theme="gray" @click="settingsOpen = true"><Icon name="settings" :size="16" /></Button>
        </Tooltip>
        <Tooltip text="Preview">
          <Button variant="ghost" theme="gray" @click="preview"><Icon name="eye" :size="16" /></Button>
        </Tooltip>
        <Dropdown :options="menu">
          <Button variant="ghost" theme="gray"><Icon name="ellipsis" :size="16" /></Button>
        </Dropdown>
        <div class="w-px h-[18px] bg-outline-gray-2 mx-1" />
        <Button v-if="form.status === 'Published'" variant="solid" theme="gray" @click="openShare">
          <template #prefix><Icon name="user-plus" :size="15" /></template>Share
        </Button>
        <Button v-else variant="solid" theme="gray" @click="publish">
          <template #prefix><Icon name="rocket" :size="15" /></template>Publish
        </Button>
      </div>
    </div>

    <div class="flex flex-1 relative min-h-0">
      <Canvas :form="form" :selectedId="selectedId"
        @select="selectedId = $event" @update-meta="updateMeta" @update-field="updateField"
        @delete="deleteField" @duplicate="duplicateField" @move="moveField" @reorder="reorder" @add="addField" />
      <Inspector v-if="prefs.devMode && selectedField" :form="form" :field="selectedField" @update-field="updateField" @open-dev="devOpen = true" />
      <DevPanel v-if="devOpen" :form="form" :slug="form.slug" @close="devOpen = false" />
    </div>

    <FormSettingsDialog v-model="settingsOpen" :form="form" @update-meta="updateMeta" @open-dev="devOpen = true" />
    <ShareDialog v-model="shareOpen" :form="form" />
  </div>
  <div v-else-if="notFound" class="flex flex-col items-center justify-center h-full gap-3 text-center">
    <Icon name="file-question" :size="28" class="text-ink-gray-4" />
    <p class="text-ink-gray-7">This form doesn't exist. It may have been deleted or renamed.</p>
    <Button variant="solid" theme="gray" @click="router.push('/')">Back to all forms</Button>
  </div>
  <div v-else class="flex items-center justify-center h-full text-ink-gray-5">Loading builder…</div>
</template>
