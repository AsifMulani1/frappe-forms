<script setup>
import { computed, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import Icon from '../Icon.vue'
import { FT } from '../../fieldTypes'

const props = defineProps({ form: Object, slug: String })
const emit = defineEmits(['close'])
const tab = ref('json')

const linked = computed(() => props.form.storage_mode === 'Linked')

const preview = createResource({
  url: 'forms.admin.preview',
  makeParams: () => ({ slug: props.slug }),
  auto: true,
})
watch(() => props.form.storage_mode, () => preview.fetch())

function highlightJSON(obj) {
  let json = JSON.stringify(obj, null, 2) || ''
  json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?)/g,
    (m) => {
      let cls = 'tok-num'
      if (/^"/.test(m)) cls = /:$/.test(m) ? 'tok-key' : 'tok-str'
      else if (/true|false|null/.test(m)) cls = 'tok-bool'
      return `<span class="${cls}">${m}</span>`
    },
  )
}

const perms = computed(() => preview.data?.permissions || [])
</script>

<template>
  <div class="dev-panel">
    <div class="flex items-center justify-between px-4 border-b border-outline-gray-1 h-[52px] shrink-0">
      <div class="flex items-center gap-2">
        <span class="w-[26px] h-[26px] rounded-[7px] bg-surface-gray-7 flex items-center justify-center text-white">
          <Icon name="code-2" :size="14" />
        </span>
        <div class="flex flex-col leading-tight">
          <span class="text-sm font-medium text-ink-gray-9">Developer view</span>
          <span class="text-[11px] text-ink-gray-5">{{ linked ? `Web Form → ${form.target_doctype}` : 'New DocType schema' }}</span>
        </div>
      </div>
      <Button variant="ghost" theme="gray" @click="emit('close')"><Icon name="x" :size="16" /></Button>
    </div>

    <div class="px-4 border-b border-outline-gray-1 flex items-center gap-4 h-10 shrink-0">
      <span v-for="t in [['json', linked ? 'Web Form' : 'Schema'], ['map', 'Mapping'], ['guard', 'Guardrails']]" :key="t[0]"
            class="text-sm cursor-pointer" :class="tab === t[0] ? 'text-ink-gray-9 font-medium' : 'text-ink-gray-5'"
            @click="tab = t[0]">{{ t[1] }}</span>
    </div>

    <div class="flex-1 overflow-y-auto p-4">
      <!-- JSON -->
      <template v-if="tab === 'json'">
        <div class="flex items-center justify-between mb-2.5">
          <div class="flex items-center gap-2">
            <Icon :name="linked ? 'link' : 'database'" :size="14" class="text-ink-gray-6" />
            <span class="font-mono text-sm text-ink-gray-8">{{ preview.data?.name }}</span>
          </div>
          <span class="flex items-center gap-1.5 text-xs text-ink-green-600">
            <span class="w-[7px] h-[7px] rounded-full bg-green-500" />in sync
          </span>
        </div>
        <div class="code-surface" v-if="preview.data">
          <pre v-html="highlightJSON(preview.data)" />
        </div>
        <div v-else class="text-sm text-ink-gray-5">Compiling…</div>
        <div class="flex items-start gap-2 mt-3">
          <Icon name="git-branch" :size="14" class="text-ink-gray-5 mt-px shrink-0" />
          <span class="text-[12px] text-ink-gray-5">
            <template v-if="linked">Publishing binds to <span class="font-mono text-ink-gray-7">{{ form.target_doctype }}</span> - no migration runs; submissions inherit its permissions &amp; workflow.</template>
            <template v-else>Publishing runs <span class="font-mono text-ink-gray-7">bench migrate</span> once to create the DocType. Later edits are additive-only, so submitted data is never dropped.</template>
          </span>
        </div>
      </template>

      <!-- MAPPING -->
      <template v-else-if="tab === 'map'">
        <div class="grid grid-cols-[1fr_auto_1fr] gap-2.5 text-[10px] text-ink-gray-5 font-mono uppercase tracking-wider pb-2">
          <span>Form field</span><span /><span>{{ linked ? `${form.target_doctype} field` : 'DocField' }}</span>
        </div>
        <div v-for="f in form.fields" :key="f.name"
             class="grid grid-cols-[1fr_auto_1fr] gap-2.5 items-center py-2 border-t border-outline-gray-1"
             :style="{ opacity: linked && !f.mapped_field ? 0.5 : 1 }">
          <div class="flex items-center gap-2 min-w-0">
            <Icon :name="FT[f.field_type].icon" :size="14" class="text-ink-gray-6" />
            <div class="flex flex-col min-w-0">
              <span class="text-sm text-ink-gray-9 truncate">{{ f.label }}</span>
              <span class="text-[11px] text-ink-gray-5">{{ FT[f.field_type].label }}{{ f.reqd ? ' · required' : '' }}</span>
            </div>
          </div>
          <Icon :name="linked && !f.mapped_field ? 'x' : 'arrow-right'" :size="14" class="text-ink-gray-4" />
          <div class="flex flex-col min-w-0 font-mono text-[12px]">
            <span class="text-ink-gray-9 truncate">{{ linked ? (f.mapped_field || 'ignored') : FT[f.field_type].doctype }}</span>
            <span class="text-ink-gray-5 truncate flex items-center gap-1">
              <Icon v-if="f.fieldname" name="lock" :size="10" />{{ linked ? (f.mapped_field ? form.target_doctype : 'not mapped') : (f.fieldname || '(derived)') }}
            </span>
          </div>
        </div>
      </template>

      <!-- GUARDRAILS -->
      <template v-else>
        <div class="border border-outline-gray-2 rounded-md bg-surface-white p-3.5 mb-2.5">
          <div class="flex items-center gap-2 mb-1.5"><Icon name="shield" :size="15" class="text-ink-gray-7" /><span class="text-sm font-medium text-ink-gray-9">Guest submissions are governed</span></div>
          <p class="text-xs text-ink-gray-6 leading-relaxed">The public form posts through one whitelisted, rate-limited endpoint that validates every field server-side and inserts with <span class="font-mono">ignore_permissions</span> - guests never get broad create perms.</p>
          <div class="border border-outline-gray-1 rounded bg-surface-gray-1 font-mono text-[11px] p-2 mt-2" v-if="!linked">
            <div v-for="p in perms" :key="p.role" class="flex justify-between">
              <span class="text-ink-gray-6">{{ p.role }}</span>
              <span class="text-ink-gray-9">{{ (p.read?'r':'-')+' '+(p.write?'w':'-')+' '+(p.create?'c':'-')+' '+(p.delete?'d':'-') }}</span>
            </div>
          </div>
        </div>
        <div class="border border-outline-gray-2 rounded-md bg-surface-white p-3.5 mb-2.5">
          <div class="flex items-center gap-2 mb-1.5"><Icon name="lock" :size="15" class="text-ink-gray-7" /><span class="text-sm font-medium text-ink-gray-9">Field names freeze at publish</span></div>
          <p class="text-xs text-ink-gray-6 leading-relaxed">A column name is derived from its label only until you publish; after that it’s frozen, so relabeling never renames the column or orphans stored answers.</p>
          <div class="flex flex-wrap gap-1.5 mt-2">
            <span v-for="f in form.fields" :key="f.name" class="inline-flex items-center gap-1 border border-outline-gray-2 rounded font-mono text-[10.5px] px-1.5 py-0.5">
              <Icon v-if="f.fieldname" name="lock" :size="9" />{{ f.fieldname || '(derived)' }}
            </span>
          </div>
        </div>
        <div class="border border-outline-gray-2 rounded-md bg-surface-white p-3.5 mb-2.5">
          <div class="flex items-center gap-2 mb-1.5"><Icon name="git-merge" :size="15" class="text-ink-gray-7" /><span class="text-sm font-medium text-ink-gray-9">Edits are additive-only</span></div>
          <p class="text-xs text-ink-gray-6 leading-relaxed">New fields are added as nullable columns; removed fields are hidden, not dropped - historical submissions keep their data.</p>
        </div>
        <div class="border border-outline-gray-2 rounded-md bg-surface-white p-3.5">
          <div class="flex items-center gap-2 mb-1.5"><Icon name="table" :size="15" class="text-ink-gray-7" /><span class="text-sm font-medium text-ink-gray-9">Checkboxes become a child table</span></div>
          <p class="text-xs text-ink-gray-6 leading-relaxed">A multi-select compiles to <span class="font-mono">Table MultiSelect</span> backed by an option master + child link table, so each selected option is its own governed row.</p>
        </div>
      </template>
    </div>
  </div>
</template>
