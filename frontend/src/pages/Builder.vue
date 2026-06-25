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
import { FT, hasOptions } from '../fieldTypes'
import { prefs, toggleDevMode } from '../data/prefs'

const props = defineProps({ slug: String })
const router = useRouter()

const form = reactive({ fields: [] })
const selectedId = ref(null)
const devOpen = ref(false)
const settingsOpen = ref(false)
const loaded = ref(false)
const saveState = ref('idle') // idle | saving | saved
let saveTimer = null
let savedTimer = null
let tmpSeq = 0

async function load() {
  Object.assign(form, await call('forms.admin.get_form', { slug: props.slug }))
  loaded.value = true
}
load()

const selectedField = computed(() => form.fields.find((f) => f.name === selectedId.value) || null)

function scheduleSave() {
  clearTimeout(saveTimer)
  saveState.value = 'saving'
  saveTimer = setTimeout(doSave, 600)
}

async function doSave() {
  if (!loaded.value) return
  saveState.value = 'saving'
  const data = await call('forms.admin.save_form', {
    name: form.name,
    data: JSON.stringify({
      title: form.title, description: form.description, accent: form.accent,
      storage_mode: form.storage_mode, target_doctype: form.target_doctype,
      login_required: form.login_required, allow_multiple: form.allow_multiple,
      collect_email: form.collect_email, thank_you_message: form.thank_you_message,
      redirect_url: form.redirect_url, cover_image: form.cover_image, category: form.category,
      is_template: form.is_template, fields: form.fields,
    }),
  })
  const keep = selectedField.value?.name
  Object.assign(form, data)
  if (keep && !form.fields.find((f) => f.name === keep)) selectedId.value = null
  saveState.value = 'saved'
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => { if (saveState.value === 'saved') saveState.value = 'idle' }, 2000)
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
    reqd: 0, help_text: '', options: hasOptions(typeId) ? 'Option 1\nOption 2\nOption 3' : '',
    mapped_field: '', fieldname: '',
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
  form.fields.splice(i + 1, 0, { ...form.fields[i], name: `tmp-${++tmpSeq}`, fieldname: '' })
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
  confirmDialog({
    title: 'Publish this form?',
    message: form.storage_mode === 'Linked'
      ? `Submissions will be saved as ${form.target_doctype} records. Field names freeze now.`
      : 'Your form goes live and anyone with the link can respond. Question types lock once it’s published, so add the fields you need first.',
    onConfirm: async ({ hideDialog }) => {
      await doSave()
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

function preview() { window.open(`/forms/f/${form.slug}`, '_blank') }
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
  // Form settings folds in here (no standing gear icon); hidden in dev mode where the inspector covers it.
  ...(!prefs.devMode ? [{ label: 'Form settings', icon: 'settings', onClick: () => { settingsOpen.value = true } }] : []),
  { label: 'Duplicate', icon: 'copy', onClick: duplicate },
  { label: 'Share', icon: 'user-plus', onClick: () => openShare() },
  // quick copy stays available for published forms (Share dialog has it too)
  ...(form.status === 'Published' ? [{ label: 'Copy link', icon: 'link', onClick: copyLink }] : []),
  { label: form.is_template ? 'Unmark template' : 'Mark as template', icon: 'layout-template',
    onClick: () => updateMeta({ is_template: form.is_template ? 0 : 1 }) },
  { label: 'Archive', icon: 'archive', onClick: archive },
  { label: 'Developer mode', icon: prefs.devMode ? 'check' : 'code-2', onClick: toggleDevMode },
  { label: 'Delete', icon: 'trash-2', theme: 'red', onClick: deleteForm },
])

// share dialog (shared ShareDialog component)
const shareOpen = ref(false)
function openShare() { shareOpen.value = true }
</script>

<template>
  <div v-if="loaded" class="flex flex-col h-full w-full" :data-accent="form.accent">
    <div class="h-[48px] border-b border-outline-gray-1 bg-surface-white flex items-center px-3.5 shrink-0 relative">
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

      <!-- right: autosave state, preview, overflow, single primary action -->
      <div class="flex items-center gap-1.5 ml-auto">
        <span class="text-[11px] text-ink-gray-4 flex items-center gap-1 mr-1 w-[52px] justify-end">
          <template v-if="saveState === 'saving'"><Icon name="loader" :size="12" class="animate-spin" />Saving</template>
          <template v-else-if="saveState === 'saved'"><Icon name="check" :size="12" class="text-ink-green-600" />Saved</template>
        </span>
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
      <Inspector v-if="prefs.devMode" :form="form" :field="selectedField" @update-meta="updateMeta" @update-field="updateField" @open-dev="devOpen = true" />
      <DevPanel v-if="devOpen" :form="form" :slug="form.slug" @close="devOpen = false" />
    </div>

    <FormSettingsDialog v-model="settingsOpen" :form="form" @update-meta="updateMeta" />
    <ShareDialog v-model="shareOpen" :form="form" />
  </div>
  <div v-else class="flex items-center justify-center h-full text-ink-gray-5">Loading builder…</div>
</template>
