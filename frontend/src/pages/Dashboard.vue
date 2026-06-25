<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Checkbox, Dropdown, FormControl, TabButtons, createResource, confirmDialog, toast } from 'frappe-ui'
import { call } from '../data/call'
import Icon from '../components/Icon.vue'
import AppShell from '../components/AppShell.vue'
import ShareDialog from '../components/ShareDialog.vue'
import { prefs } from '../data/prefs'

const router = useRouter()
const route = useRoute()
const statusTab = ref('all')
const view = ref('list')
const shell = ref(null)
const search = ref('')

const activeView = computed(() => route.query.view || 'all')

const META = {
  all: { title: 'Forms', sub: 'Create a form, share it, and collect responses — all in one place.' },
  shared: { title: 'Shared with me', sub: 'Forms other people have shared with you.' },
  templates: { title: 'Templates', sub: 'Start a new form from a ready-made blueprint.' },
  archived: { title: 'Archived', sub: 'Forms you’ve archived. Restore any time - nothing is deleted.' },
}
const meta = computed(() => META[activeView.value] || META.all)
const isTemplates = computed(() => activeView.value === 'templates')
const isArchived = computed(() => activeView.value === 'archived')
const showStatusTabs = computed(() => activeView.value === 'all')

// Context-aware list columns (clarity: show only what's meaningful here).
// Hide Status when the list is already filtered to a single status; hide metrics for Drafts.
const onlyOneStatus = computed(() => activeView.value === 'all' && statusTab.value !== 'all')
const showStatusCol = computed(() => !onlyOneStatus.value)
const showMetrics = computed(() => !(activeView.value === 'all' && statusTab.value === 'draft'))

// Choice-style fields render with a select chevron in the preview; paragraphs get a taller box.
const CHOICE_TYPES = ['single_choice', 'dropdown', 'checkboxes']
function isChoice(t) { return CHOICE_TYPES.includes(t) }

const forms = createResource({
  url: 'forms.admin.list_forms',
  makeParams: () => ({ view: activeView.value }),
  auto: true,
})
watch(activeView, () => { statusTab.value = 'all'; forms.reload() })

const statusButtons = computed(() => {
  const list = forms.data || []
  return [
    { label: `All ${list.length}`, value: 'all' },
    { label: `Published ${list.filter((f) => f.status === 'Published').length}`, value: 'published' },
    { label: `Drafts ${list.filter((f) => f.status === 'Draft').length}`, value: 'draft' },
  ]
})

const categoryTab = ref('all')
watch(activeView, () => { categoryTab.value = 'all' })
const categoryButtons = computed(() => {
  const cats = [...new Set((forms.data || []).map((f) => f.category).filter(Boolean))].sort()
  return [{ label: 'All', value: 'all' }, ...cats.map((c) => ({ label: c, value: c }))]
})

const rows = computed(() => {
  const q = search.value.trim().toLowerCase()
  return (forms.data || [])
    .filter((f) => !showStatusTabs.value || statusTab.value === 'all' || f.status.toLowerCase() === statusTab.value)
    .filter((f) => !isTemplates.value || categoryTab.value === 'all' || f.category === categoryTab.value)
    .filter((f) => !q || f.title.toLowerCase().includes(q))
})

function ago(dt) {
  if (!dt) return '-'
  const d = (Date.now() - new Date(dt.replace(' ', 'T')).getTime()) / 1000
  if (d < 3600) return `${Math.max(1, Math.round(d / 60))}m ago`
  if (d < 86400) return `${Math.round(d / 3600)}h ago`
  return `${Math.round(d / 86400)}d ago`
}

// Default-named drafts recede so real, named forms lead the list (never hidden or deleted).
function isUntitled(f) {
  return f.status !== 'Published' && (!f.title || f.title === 'Untitled form')
}

// One quiet line of context per grid card (published -> reach, draft -> size).
function cardSubtitle(f) {
  if (f.status === 'Published')
    return f.responses ? `${f.responses.toLocaleString()} ${f.responses === 1 ? 'response' : 'responses'}` : 'No responses yet'
  return f.field_count ? `${f.field_count} ${f.field_count === 1 ? 'question' : 'questions'}` : 'Empty draft'
}

function refresh() {
  forms.reload()
  shell.value?.refreshCounts?.()
}

async function newForm() {
  const doc = await call('forms.admin.create_form')
  router.push(`/${doc.slug}/edit`)
}
async function useTemplate(f) {
  const doc = await call('forms.admin.duplicate_form', { name: f.name })
  toast.success('Created from template')
  router.push(`/${doc.slug}/edit`)
}
async function duplicate(f) {
  const doc = await call('forms.admin.duplicate_form', { name: f.name })
  toast.success('Form duplicated')
  router.push(`/${doc.slug}/edit`)
}
function archive(f, archived) {
  confirmDialog({
    title: archived ? 'Archive this form?' : 'Restore this form?',
    message: archived ? 'It moves to Archived. Responses are kept and nothing is deleted.' : 'It moves back to All forms.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.set_archived', { name: f.name, archived: archived ? 1 : 0 })
      toast.success(archived ? 'Form archived' : 'Form restored')
      refresh()
      hideDialog?.()
    },
  })
}
function deleteForm(f) {
  confirmDialog({
    title: 'Delete this form?',
    message: f.status === 'Published'
      ? 'This permanently deletes the form and every response collected. This cannot be undone.'
      : 'This permanently deletes the form. This cannot be undone.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.delete_form', { name: f.name })
      toast.success('Form deleted')
      refresh()
      hideDialog?.()
    },
  })
}
function rowMenu(f) {
  const items = [{ label: 'Edit', icon: 'edit-2', onClick: () => router.push(`/${f.slug}/edit`) }]
  if (f.status === 'Published') items.push({ label: 'Responses', icon: 'bar-chart-2', onClick: () => router.push(`/${f.slug}/responses`) })
  items.push({ label: 'Duplicate', icon: 'copy', onClick: () => duplicate(f) })
  items.push({ label: 'Share', icon: 'user-plus', onClick: () => openShare(f) })
  if (f.archived) items.push({ label: 'Restore', icon: 'archive-restore', onClick: () => archive(f, false) })
  else items.push({ label: 'Archive', icon: 'archive', onClick: () => archive(f, true) })
  items.push({ label: 'Delete', icon: 'trash-2', theme: 'red', onClick: () => deleteForm(f) })
  return items
}

// --- multi-select: bulk archive / delete across List and Grid ---
const selected = ref(new Set())
const selectMode = computed(() => selected.value.size > 0)
function toggleSelect(name) {
  const s = new Set(selected.value)
  s.has(name) ? s.delete(name) : s.add(name)
  selected.value = s
}
function clearSelection() { selected.value = new Set() }
const allSelected = computed(() => rows.value.length > 0 && rows.value.every((f) => selected.value.has(f.name)))
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(rows.value.map((f) => f.name))
}
// Selection is scoped to the current view/filter — reset it when that changes.
watch([activeView, statusTab, categoryTab], clearSelection)

function bulkArchive() {
  const names = [...selected.value]
  const n = names.length
  confirmDialog({
    title: `Archive ${n} ${n === 1 ? 'form' : 'forms'}?`,
    message: 'They move to Archived. Responses are kept and nothing is deleted.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.set_archived_bulk', { names: JSON.stringify(names), archived: 1 })
      toast.success(`Archived ${n} ${n === 1 ? 'form' : 'forms'}`)
      clearSelection(); refresh(); hideDialog?.()
    },
  })
}
function bulkRestore() {
  const names = [...selected.value]
  const n = names.length
  confirmDialog({
    title: `Restore ${n} ${n === 1 ? 'form' : 'forms'}?`,
    message: 'They move back to All forms.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.set_archived_bulk', { names: JSON.stringify(names), archived: 0 })
      toast.success(`Restored ${n} ${n === 1 ? 'form' : 'forms'}`)
      clearSelection(); refresh(); hideDialog?.()
    },
  })
}
function bulkDelete() {
  const names = [...selected.value]
  const n = names.length
  confirmDialog({
    title: `Delete ${n} ${n === 1 ? 'form' : 'forms'}?`,
    message: 'This permanently deletes the selected forms and every response collected. This cannot be undone.',
    onConfirm: async ({ hideDialog }) => {
      await call('forms.admin.delete_forms', { names: JSON.stringify(names) })
      toast.success(`Deleted ${n} ${n === 1 ? 'form' : 'forms'}`)
      clearSelection(); refresh(); hideDialog?.()
    },
  })
}

// --- share dialog (shared ShareDialog component) ---
const shareOpen = ref(false)
const shareForm = ref(null)
function openShare(f) {
  shareForm.value = f
  shareOpen.value = true
}
</script>

<template>
  <AppShell ref="shell">
    <div class="flex-1 overflow-auto bg-surface-white">
      <div class="px-5 pt-10 pb-12 max-w-[960px] mx-auto">
        <div class="flex items-start justify-between gap-4 mb-7">
          <div class="flex flex-col gap-1.5 min-w-0">
            <h1 class="text-3xl text-ink-gray-9">{{ meta.title }}</h1>
            <p class="text-sm text-ink-gray-5">{{ meta.sub }}</p>
          </div>
          <Button variant="solid" theme="gray" class="shrink-0 mt-1" @click="newForm">
            <template #prefix><Icon name="plus" :size="15" /></template>
            New form
          </Button>
        </div>

        <div class="flex items-center justify-between gap-3 mb-5">
          <!-- selection toolbar replaces the filters while items are selected -->
          <template v-if="selectMode && !isTemplates">
            <div class="flex items-center gap-2.5">
              <Button variant="ghost" theme="gray" @click="clearSelection"><Icon name="x" :size="16" /></Button>
              <span class="text-sm text-ink-gray-7">{{ selected.size }} selected</span>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <Button v-if="isArchived" variant="ghost" theme="gray" @click="bulkRestore">
                <template #prefix><Icon name="archive-restore" :size="15" /></template>Restore
              </Button>
              <Button v-else variant="ghost" theme="gray" @click="bulkArchive">
                <template #prefix><Icon name="archive" :size="15" /></template>Archive
              </Button>
              <Button variant="ghost" theme="red" @click="bulkDelete">
                <template #prefix><Icon name="trash-2" :size="15" /></template>Delete
              </Button>
            </div>
          </template>
          <template v-else>
            <TabButtons v-if="showStatusTabs" :buttons="statusButtons" v-model="statusTab" />
            <TabButtons v-else-if="isTemplates && categoryButtons.length > 1" :buttons="categoryButtons" v-model="categoryTab" />
            <div v-else />
            <div class="flex items-center gap-2 shrink-0">
              <FormControl type="text" size="sm" placeholder="Search" v-model="search" class="w-[180px]">
                <template #prefix><Icon name="search" :size="14" class="text-ink-gray-4" /></template>
              </FormControl>
              <TabButtons v-if="!isTemplates" :buttons="[
                { label: 'List', value: 'list', icon: 'list', hideLabel: true },
                { label: 'Grid', value: 'grid', icon: 'grid', hideLabel: true },
              ]" v-model="view" />
            </div>
          </template>
        </div>

        <!-- loading skeleton -->
        <div v-if="forms.loading && !forms.data" class="flex flex-col gap-2">
          <div v-for="i in 5" :key="i" class="h-[52px] rounded-[10px] bg-surface-gray-2 animate-pulse" />
        </div>

        <!-- empty state -->
        <div v-else-if="!rows.length" class="flex flex-col items-center justify-center text-center border border-outline-gray-2 rounded-[10px] bg-surface-white py-16">
          <Icon :name="search ? 'search' : isArchived ? 'archive' : isTemplates ? 'layout-template' : 'clipboard-list'" :size="26" class="text-ink-gray-4" />
          <template v-if="search">
            <p class="text-base text-ink-gray-7 mt-3">No forms match “{{ search }}”</p>
            <p class="text-sm text-ink-gray-5 mt-1">Try a different search.</p>
          </template>
          <template v-else>
            <p class="text-base text-ink-gray-7 mt-3">
              {{ isArchived ? 'Nothing archived' : isTemplates ? 'No templates yet' : activeView === 'shared' ? 'Nothing shared with you' : 'No forms yet' }}
            </p>
            <p class="text-sm text-ink-gray-5 mt-1">{{ isTemplates ? 'Mark any form as a template to reuse it.' : 'Create one to get started.' }}</p>
            <Button v-if="activeView === 'all'" variant="solid" theme="gray" class="mt-4" @click="newForm">New form</Button>
          </template>
        </div>

        <!-- template gallery: start blank or pick a ready-made blueprint (Builder-style picker) -->
        <div v-else-if="isTemplates" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-8">
          <!-- blank form: leads the grid, caption-less so it aligns with the thumbnails -->
          <button type="button" @click="newForm"
                  class="self-start h-[256px] rounded-[10px] border border-dashed border-outline-gray-3 bg-surface-white flex flex-col items-center justify-center gap-3 text-ink-gray-5 transition-colors hover:border-ink-gray-4 hover:text-ink-gray-7 hover:bg-surface-gray-1">
            <Icon name="plus" :size="26" />
            <span class="text-base">Blank form</span>
          </button>

          <div v-for="f in rows" :key="f.name"
               class="group flex flex-col gap-3 cursor-pointer"
               @click="useTemplate(f)">
            <!-- thumbnail: neutral document preview (Espresso, no accent bands) -->
            <div class="relative h-[256px] rounded-[10px] overflow-hidden border border-outline-gray-1 bg-surface-gray-2 shadow-sm transition-shadow group-hover:shadow-md">
              <div class="absolute inset-x-3.5 top-7 bottom-0 bg-surface-white rounded-t-[8px] shadow-[0_-1px_8px_rgba(0,0,0,0.06)] px-4 pt-3.5 flex flex-col gap-2.5 overflow-hidden">
                <div class="text-sm font-semibold text-ink-gray-9 pb-2.5 border-b border-outline-gray-1 truncate">{{ f.title }}</div>
                <div v-for="(fld, i) in (f.preview || []).slice(0, 3)" :key="i" class="flex flex-col gap-1">
                  <span class="text-[11px] font-medium text-ink-gray-7 truncate">
                    {{ fld.label }}<span v-if="fld.reqd" class="text-ink-red-500">&nbsp;*</span>
                  </span>
                  <div v-if="fld.field_type === 'paragraph'" class="h-9 rounded-md border border-outline-gray-2 bg-surface-gray-1" />
                  <div v-else class="relative h-6 rounded-md border border-outline-gray-2 bg-surface-gray-1">
                    <Icon v-if="isChoice(fld.field_type)" name="chevron-down" :size="13" class="absolute right-1.5 top-1/2 -translate-y-1/2 text-ink-gray-4" />
                  </div>
                </div>
              </div>
            </div>
            <!-- title (left) + field count (right) -->
            <div class="flex items-baseline justify-between gap-3">
              <span class="text-base text-ink-gray-9 group-hover:underline truncate">{{ f.title }}</span>
              <span class="text-sm text-ink-gray-5 shrink-0 tabular-nums">{{ f.field_count }} fields</span>
            </div>
          </div>
        </div>

        <!-- list view (columns adapt to the active filter) -->
        <div v-else-if="view === 'list'" class="border border-outline-gray-1 rounded-[10px] overflow-hidden bg-surface-white">
          <div class="flex items-center gap-3 px-4 py-2.5 border-b border-outline-gray-1 bg-surface-gray-1 text-xs text-ink-gray-5">
            <span class="w-4 flex items-center justify-center" @click.stop>
              <Checkbox :modelValue="allSelected" @update:modelValue="toggleAll" />
            </span>
            <span class="flex-1">Form</span>
            <span v-if="showMetrics" class="w-24 text-right">Responses</span>
            <span v-if="showStatusCol" class="w-[104px] pl-4">Status</span>
            <span class="w-20 text-right">Updated</span>
            <span class="w-8" />
          </div>
          <div v-for="f in rows" :key="f.name"
               class="group flex items-center gap-3 px-4 py-3.5 cursor-pointer border-t border-outline-gray-1 first:border-t-0 hover:bg-surface-gray-1 transition-colors"
               :class="{ 'bg-surface-gray-1': selected.has(f.name) }"
               @click="router.push(`/${f.slug}/edit`)">
            <!-- leading cell: status dot by default, checkbox on hover or when selected -->
            <span class="relative w-4 h-4 shrink-0" @click.stop>
              <span class="absolute inset-0 flex items-center justify-center transition-opacity"
                    :class="selected.has(f.name) ? 'opacity-0' : 'group-hover:opacity-0'">
                <span class="w-2 h-2 rounded-full" :title="f.status"
                      :style="{ background: f.status === 'Published' ? 'var(--green-500)' : 'var(--gray-400)' }" />
              </span>
              <span class="absolute inset-0 flex items-center justify-center transition-opacity"
                    :class="selected.has(f.name) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'">
                <Checkbox :modelValue="selected.has(f.name)" @update:modelValue="toggleSelect(f.name)" />
              </span>
            </span>
            <div class="flex flex-col flex-1 min-w-0 gap-0.5">
              <span class="text-base truncate leading-tight" :class="isUntitled(f) ? 'text-ink-gray-5' : 'text-ink-gray-9'">{{ f.title }}</span>
              <span class="text-xs text-ink-gray-5 truncate">
                {{ prefs.devMode ? (f.storage_mode === 'Linked' ? `Linked · ${f.target_doctype}` : 'DocType compiled')
                  : f.field_count === 0 ? 'Empty draft — add questions to publish'
                  : `${f.field_count} ${f.field_count === 1 ? 'question' : 'questions'}` }}
              </span>
            </div>
            <span v-if="showMetrics" class="w-24 text-right text-base tabular-nums"
                  :title="f.status === 'Published' ? `${f.responses} responses · ${f.completion}% completion rate` : ''">
              <span v-if="f.status === 'Published'" :class="f.responses ? 'text-ink-gray-8' : 'text-ink-gray-3'">{{ f.responses ? f.responses.toLocaleString() : '0' }}</span>
              <span v-else class="text-ink-gray-3">–</span>
            </span>
            <span v-if="showStatusCol" class="w-[104px] pl-4"><Badge :theme="f.status === 'Published' ? 'green' : 'gray'" :label="f.status" /></span>
            <span class="w-20 text-right text-sm text-ink-gray-5">{{ ago(f.modified) }}</span>
            <span class="w-8 flex justify-end" @click.stop>
              <Dropdown :options="rowMenu(f)">
                <Button variant="ghost" theme="gray" class="opacity-0 group-hover:opacity-100"><Icon name="ellipsis" :size="16" /></Button>
              </Dropdown>
            </span>
          </div>
        </div>

        <!-- grid view: minimal cards — status as a dot, one quiet subtitle, actions on hover -->
        <div v-else class="grid grid-cols-2 gap-4">
          <div v-for="f in rows" :key="f.name"
               class="group relative border rounded-[12px] px-5 py-[18px] bg-surface-white cursor-pointer transition-colors"
               :class="selected.has(f.name) ? 'border-outline-gray-4' : 'border-outline-gray-1 hover:border-outline-gray-2'"
               @click="router.push(`/${f.slug}/edit`)">
            <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity" @click.stop>
              <Dropdown :options="rowMenu(f)">
                <Button variant="ghost" theme="gray"><Icon name="ellipsis" :size="16" /></Button>
              </Dropdown>
            </div>
            <div class="flex items-center gap-2 pr-7">
              <!-- status dot by default, checkbox on hover or when selected -->
              <span class="relative w-4 h-4 shrink-0" @click.stop>
                <span class="absolute inset-0 flex items-center justify-center transition-opacity"
                      :class="selected.has(f.name) ? 'opacity-0' : 'group-hover:opacity-0'">
                  <span class="w-2 h-2 rounded-full" :title="f.status"
                        :style="{ background: f.status === 'Published' ? 'var(--green-500)' : 'var(--gray-400)' }" />
                </span>
                <span class="absolute inset-0 flex items-center justify-center transition-opacity"
                      :class="selected.has(f.name) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'">
                  <Checkbox :modelValue="selected.has(f.name)" @update:modelValue="toggleSelect(f.name)" />
                </span>
              </span>
              <span class="text-base truncate" :class="isUntitled(f) ? 'text-ink-gray-5' : 'text-ink-gray-9'">{{ f.title }}</span>
            </div>
            <span class="block text-sm text-ink-gray-5 mt-1.5">{{ cardSubtitle(f) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- share dialog (shared component) -->
    <ShareDialog v-model="shareOpen" :form="shareForm" @changed="shell?.refreshCounts?.()" />
  </AppShell>
</template>
