<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Avatar, Badge, Button, createResource, toast } from 'frappe-ui'
import { call } from '../data/call'
import Icon from '../components/Icon.vue'
import { prefs } from '../data/prefs'

const props = defineProps({ slug: String })
const router = useRouter()
const sub = ref('summary')
const openRec = ref(null)
const drawer = ref(null)

const meta = createResource({ url: 'forms.admin.get_form', params: { slug: props.slug }, auto: true })
const sheetLoading = ref(false)

async function openSheet() {
  // Export responses into Frappe Sheets (one persistent sheet per form) and open it.
  sheetLoading.value = true
  try {
    const res = await call('forms.admin.open_in_sheet', { slug: props.slug })
    window.open(res.url, '_blank')
  } catch (e) {
    toast.error(e.messages?.[0] || 'Could not open in Frappe Sheets')
  } finally {
    sheetLoading.value = false
  }
}
const summary = createResource({ url: 'forms.admin.responses_summary', params: { slug: props.slug }, auto: true })
const subs = createResource({ url: 'forms.admin.list_submissions', params: { slug: props.slug, limit: 100 }, auto: true })

const stateTheme = { Confirmed: 'green', Pending: 'orange', Waitlist: 'blue' }

function fmtDate(dt) {
  if (!dt) return '-'
  return new Date(dt.replace(' ', 'T')).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
function maxN(data) {
  return Math.max(1, ...data.map((d) => d.n))
}

async function openRecord(name) {
  openRec.value = name
  drawer.value = await call('forms.admin.get_submission', { slug: props.slug, name })
}
async function setState(state) {
  await call('forms.admin.set_workflow_state', { slug: props.slug, name: openRec.value, state })
  drawer.value.workflow_state = state
  subs.fetch()
}
async function exportCsv() {
  const csv = await call('forms.admin.export_csv', { slug: props.slug })
  const blob = new Blob([csv], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.slug}-responses.csv`
  a.click()
  toast.success('CSV exported')
}
</script>

<template>
  <div class="flex flex-col h-full w-full" :data-accent="meta.data?.accent || 'blue'">
    <!-- topbar -->
    <div class="h-[48px] border-b border-outline-gray-1 bg-surface-white flex items-center px-3.5 shrink-0 relative">
      <!-- left: back + title + status dot (matches the builder bar) -->
      <div class="flex items-center gap-2.5 min-w-0">
        <button class="flex items-center gap-1.5 px-2 h-8 rounded-md hover:bg-surface-gray-2 text-ink-gray-7 shrink-0 transition-colors" title="Back to all forms" @click="router.push('/')">
          <Icon name="clipboard-list" :size="15" />
          <span class="text-sm font-medium">Forms</span>
        </button>
        <Icon name="chevron-right" :size="15" class="text-ink-gray-4 shrink-0" />
        <div class="flex flex-col leading-tight min-w-0">
          <div class="flex items-center gap-2 min-w-0">
            <span class="text-sm font-medium text-ink-gray-9 truncate max-w-[260px]">{{ meta.data?.title }}</span>
            <Badge v-if="meta.data" :theme="meta.data.status === 'Published' ? 'green' : 'gray'" :label="meta.data.status" />
          </div>
          <span v-if="prefs.devMode" class="text-[11px] text-ink-gray-5 font-mono">{{ meta.data?.doctype_name }}</span>
        </div>
      </div>

      <!-- center: page switch, anchored to the true center of the bar -->
      <div class="segmented absolute left-1/2 -translate-x-1/2">
        <span class="seg-btn" @click="router.push(`/${slug}/edit`)">Edit</span>
        <span class="seg-btn active">Responses</span>
      </div>
    </div>

    <div class="flex-1 overflow-auto relative bg-surface-gray-1">
      <div class="px-5 pt-6 pb-14 max-w-[940px] mx-auto">
        <div class="flex items-center justify-between mb-4">
          <div class="flex gap-4">
            <span class="text-sm cursor-pointer pb-1 border-b-2" :class="sub === 'summary' ? 'text-ink-gray-9 border-ink-gray-9 font-medium' : 'text-ink-gray-6 border-transparent'" @click="sub = 'summary'">Summary</span>
            <span class="text-sm cursor-pointer pb-1 border-b-2" :class="sub === 'individual' ? 'text-ink-gray-9 border-ink-gray-9 font-medium' : 'text-ink-gray-6 border-transparent'" @click="sub = 'individual'">
              Individual <span class="text-ink-gray-4">{{ subs.data?.total || 0 }}</span>
            </span>
          </div>
          <div class="flex items-center gap-2">
            <Button variant="outline" theme="gray" :loading="sheetLoading" @click="openSheet">
              <template #prefix><Icon name="table-2" :size="15" /></template>Open in Frappe Sheets
            </Button>
            <Button variant="outline" theme="gray" @click="exportCsv">
              <template #prefix><Icon name="download" :size="15" /></template>Export CSV
            </Button>
          </div>
        </div>

        <!-- SUMMARY -->
        <div v-if="sub === 'summary'" class="flex flex-col gap-4">
          <div v-if="summary.loading && !summary.data" class="flex flex-col gap-3">
            <div class="grid grid-cols-4 gap-3"><div v-for="i in 4" :key="i" class="h-[88px] rounded-[10px] bg-surface-gray-2 animate-pulse" /></div>
            <div class="h-[180px] rounded-md bg-surface-gray-2 animate-pulse" />
          </div>
          <div v-else-if="summary.data" class="grid grid-cols-4 gap-3">
            <div class="stat-card">
              <div class="flex items-center justify-between"><span class="text-xs text-ink-gray-5">Total responses</span><Icon name="inbox" :size="15" class="text-ink-gray-4" /></div>
              <span class="text-[26px] font-medium text-ink-gray-9">{{ summary.data.total.toLocaleString() }}</span>
            </div>
            <div class="stat-card">
              <div class="flex items-center justify-between"><span class="text-xs text-ink-gray-5">Completion rate</span><Icon name="check-check" :size="15" class="text-ink-gray-4" /></div>
              <span class="text-[26px] font-medium text-ink-gray-9">{{ summary.data.completion }}%</span>
              <span class="text-xs text-ink-gray-5">{{ summary.data.total.toLocaleString() }} of {{ (summary.data.views || 0).toLocaleString() }} opens</span>
            </div>
            <div class="stat-card">
              <div class="flex items-center justify-between"><span class="text-xs text-ink-gray-5">Confirmed</span><Icon name="user-check" :size="15" class="text-ink-gray-4" /></div>
              <span class="text-[26px] font-medium text-ink-gray-9">{{ summary.data.confirmed }}</span>
            </div>
            <div class="stat-card">
              <div class="flex items-center justify-between"><span class="text-xs text-ink-gray-5">Avg. rating</span><Icon name="star" :size="15" class="text-ink-gray-4" /></div>
              <span class="text-[26px] font-medium text-ink-gray-9">{{ summary.data.rating ? summary.data.rating.average : '-' }}</span>
            </div>
          </div>
          <div v-else class="border border-outline-gray-1 rounded-md bg-surface-white text-center py-12 px-4">
            <Icon name="chart-no-axes-column" :size="22" class="text-ink-gray-4 mx-auto" />
            <p class="text-sm text-ink-gray-7 mt-2">Couldn't load the summary.</p>
            <Button class="mx-auto mt-3" variant="subtle" theme="gray" @click="summary.fetch()">Try again</Button>
          </div>

          <!-- choice charts -->
          <div v-for="c in (summary.data?.charts || [])" :key="c.fieldname" class="border border-outline-gray-1 rounded-md bg-surface-white p-[18px]">
            <span class="text-sm font-medium text-ink-gray-9">{{ c.label }}</span>
            <div class="flex flex-col gap-3 mt-4">
              <div v-for="d in c.data" :key="d.label" class="flex flex-col gap-1.5">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-sm text-ink-gray-7 truncate">{{ d.label }}</span>
                  <span class="text-sm text-ink-gray-5 whitespace-nowrap">{{ d.n }} · {{ Math.round((d.n / summary.data.total) * 100) }}%</span>
                </div>
                <div class="bar-track"><div class="bar-fill" :style="{ width: `${(d.n / maxN(c.data)) * 100}%` }" /></div>
              </div>
            </div>
          </div>

          <!-- rating breakdown -->
          <div v-if="summary.data?.rating" class="border border-outline-gray-1 rounded-md bg-surface-white p-[18px]">
            <span class="text-sm font-medium text-ink-gray-9">{{ summary.data.rating.label }}</span>
            <div class="flex items-center gap-3 mt-4">
              <span class="text-[38px] font-medium text-ink-gray-9">{{ summary.data.rating.average }}</span>
              <span class="text-xs text-ink-gray-5">from {{ summary.data.rating.count }} ratings</span>
            </div>
            <div class="flex flex-col gap-1.5 mt-4">
              <div v-for="s in [5, 4, 3, 2, 1]" :key="s" class="flex items-center gap-2">
                <span class="text-xs text-ink-gray-5 w-2.5">{{ s }}</span>
                <Icon name="star" :size="11" style="color:var(--amber-500);fill:var(--amber-500)" />
                <div class="bar-track flex-1"><div class="bar-fill" :style="{ width: `${summary.data.rating.count ? (summary.data.rating.buckets[s] / summary.data.rating.count) * 100 : 0}%`, background: 'var(--amber-400)' }" /></div>
                <span class="text-xs text-ink-gray-5 w-8 text-right">{{ summary.data.rating.count ? Math.round((summary.data.rating.buckets[s] / summary.data.rating.count) * 100) : 0 }}%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- INDIVIDUAL -->
        <div v-else class="border border-outline-gray-1 rounded-md overflow-hidden bg-surface-white">
          <div class="flex items-center gap-3 px-3 py-2 border-b border-outline-gray-1 bg-surface-gray-1 text-xs text-ink-gray-5">
            <span class="w-[150px] font-mono">name</span>
            <span class="flex-1">Respondent</span>
            <span v-if="subs.data?.has_workflow" class="w-[100px]">State</span>
            <span class="w-16 text-right">Created</span>
          </div>
          <div v-if="!subs.data?.rows?.length" class="text-sm text-ink-gray-5 text-center py-10">No responses yet.</div>
          <div v-for="r in (subs.data?.rows || [])" :key="r.name"
               class="flex items-center gap-3 px-3 py-2 cursor-pointer border-t border-outline-gray-1 first:border-t-0 hover:bg-surface-gray-1"
               @click="openRecord(r.name)">
            <span class="w-[150px] font-mono text-[11.5px] text-ink-gray-5 truncate">{{ r.name }}</span>
            <div class="flex items-center gap-2.5 flex-1 min-w-0">
              <Avatar :label="r[subs.data.display_fields[0]?.fieldname] || r.name" size="sm" />
              <div class="flex flex-col min-w-0">
                <span class="text-sm text-ink-gray-9 truncate">{{ r[subs.data.display_fields[0]?.fieldname] || '-' }}</span>
                <span class="text-[11px] text-ink-gray-5 truncate">{{ r[subs.data.display_fields[1]?.fieldname] || '' }}</span>
              </div>
            </div>
            <span v-if="subs.data?.has_workflow" class="w-[100px]">
              <Badge v-if="r.workflow_state" :theme="stateTheme[r.workflow_state] || 'gray'" :label="r.workflow_state" />
            </span>
            <span class="w-16 text-right text-sm text-ink-gray-5">{{ fmtDate(r.creation) }}</span>
          </div>
        </div>
      </div>

      <!-- record drawer -->
      <template v-if="openRec">
        <div class="absolute inset-0 bg-black/20 z-[55]" @click="openRec = null" />
        <div class="dev-panel" style="width:420px" v-if="drawer">
          <div class="flex items-center justify-between px-4 border-b border-outline-gray-1 h-[52px] shrink-0">
            <div class="flex items-center gap-2">
              <Avatar :label="drawer.fields[0]?.value || drawer.name" size="md" />
              <div class="flex flex-col leading-tight">
                <span class="text-sm font-medium text-ink-gray-9">{{ drawer.fields[0]?.value || drawer.name }}</span>
                <span class="text-[11px] text-ink-gray-5 font-mono">{{ drawer.name }}</span>
              </div>
            </div>
            <Button variant="ghost" theme="gray" @click="openRec = null"><Icon name="x" :size="16" /></Button>
          </div>

          <div v-if="drawer.workflow_state" class="px-4 py-3 border-b border-outline-gray-1 flex items-center justify-between shrink-0">
            <div class="flex items-center gap-2">
              <span class="text-xs text-ink-gray-5">Workflow state</span>
              <Badge :theme="stateTheme[drawer.workflow_state] || 'gray'" :label="drawer.workflow_state" />
            </div>
            <div class="flex gap-1">
              <Button variant="subtle" theme="gray" size="sm" @click="setState('Waitlist')">Waitlist</Button>
              <Button variant="solid" theme="gray" size="sm" @click="setState('Confirmed')">Confirm</Button>
            </div>
          </div>

          <div class="flex-1 overflow-y-auto p-4">
            <span class="text-[10px] text-ink-gray-5 font-mono uppercase tracking-wider">Record fields</span>
            <div class="border border-outline-gray-1 rounded-md overflow-hidden bg-surface-white mt-2">
              <div class="flex items-center justify-between px-3 py-2.5 border-t border-outline-gray-1 first:border-t-0">
                <span class="text-[12px] text-ink-gray-5 font-mono">name</span>
                <span class="text-sm text-ink-gray-9 truncate max-w-[220px] text-right">{{ drawer.name }}</span>
              </div>
              <div v-for="f in drawer.fields" :key="f.fieldname" class="flex items-center justify-between px-3 py-2.5 border-t border-outline-gray-1">
                <span class="text-[12px] text-ink-gray-5 font-mono">{{ f.fieldname }}</span>
                <span class="text-sm text-ink-gray-9 truncate max-w-[220px] text-right">{{ f.value || '-' }}</span>
              </div>
            </div>

            <template v-for="(vals, label) in drawer.multi" :key="label">
              <span class="text-[10px] text-ink-gray-5 font-mono uppercase tracking-wider block mt-4.5 mt-4">{{ label }}</span>
              <div class="flex flex-wrap gap-1.5 mt-2">
                <Badge v-for="v in vals" :key="v" theme="gray" :label="v" />
                <span v-if="!vals.length" class="text-sm text-ink-gray-5">-</span>
              </div>
            </template>

            <div class="flex items-start gap-2 mt-5">
              <Icon name="shield-check" :size="14" class="text-ink-green-600 mt-px shrink-0" />
              <span class="text-[12px] text-ink-gray-5">Stored in <span class="font-mono text-ink-gray-7">{{ drawer.doctype }}</span>, validated server-side and audited in the version log.</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
