<script setup>
import { computed, watch } from 'vue'
import { Badge, Button, FormControl, Switch, TabButtons, createResource } from 'frappe-ui'
import Icon from '../Icon.vue'
import { FIELD_TYPES, FT, hasOptions } from '../../fieldTypes'
import { prefs } from '../../data/prefs'

const props = defineProps({ form: Object, field: Object })
const emit = defineEmits(['update-meta', 'update-field', 'open-dev'])

const linked = computed(() => props.form.storage_mode === 'Linked')
const fieldTypeOptions = FIELD_TYPES.map((t) => ({ label: t.label, value: t.id }))

const targetFields = createResource({
  url: 'forms.admin.target_doctype_fields',
  makeParams: () => ({ doctype: props.form.target_doctype }),
})
function refreshTargets() {
  if (linked.value && props.form.target_doctype) targetFields.fetch()
}
watch(() => props.form.target_doctype, refreshTargets)
watch(() => props.form.storage_mode, (m) => { if (m === 'Linked') refreshTargets() })

const mapOptions = computed(() => [
  { label: '- Not mapped -', value: '' },
  ...(targetFields.data || []).map((tf) => ({ label: `${tf.label} · ${tf.fieldname}`, value: tf.fieldname })),
])
const mappedCount = computed(() => props.form.fields.filter((f) => f.mapped_field).length)

function setStorage(mode) {
  emit('update-meta', { storage_mode: mode })
  if (mode === 'Linked' && !props.form.target_doctype) {
    emit('update-meta', { target_doctype: 'Contact' })
    setTimeout(refreshTargets, 50)
  }
}
</script>

<template>
  <aside class="w-[312px] h-full shrink-0 border-l border-outline-gray-1 bg-surface-white flex flex-col overflow-y-auto">
    <!-- FORM SETTINGS -->
    <template v-if="!field">
      <div class="px-4 py-3 border-b border-outline-gray-1"><span class="text-sm font-medium text-ink-gray-9">Form settings</span></div>

      <div class="flex items-center justify-between px-4 py-3 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">Status</span>
        <Badge :theme="form.status === 'Published' ? 'green' : 'gray'" :label="form.status" />
      </div>

      <div v-if="prefs.devMode" class="flex flex-col gap-2 px-4 py-3.5 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">Where submissions go</span>
        <TabButtons
          :buttons="[{ label: 'New collection', value: 'Collection' }, { label: 'Link existing', value: 'Linked' }]"
          :modelValue="form.storage_mode" @update:modelValue="setStorage($event)" />
        <span class="text-[11.5px] text-ink-gray-5">
          {{ linked ? 'Saved as records of an existing DocType - no schema change on publish.' : 'A dedicated DocType is created for this form on publish.' }}
        </span>
      </div>

      <div v-if="prefs.devMode && linked" class="flex flex-col gap-2 px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="select" label="Target DocType"
          :options="[{ label: 'Contact', value: 'Contact' }, { label: 'ToDo', value: 'ToDo' }]"
          :modelValue="form.target_doctype" @update:modelValue="emit('update-meta', { target_doctype: $event })" />
        <div><Badge :theme="mappedCount < form.fields.length ? 'orange' : 'green'" :label="`${mappedCount}/${form.fields.length} mapped`" /></div>
      </div>
      <div v-else-if="prefs.devMode" class="flex flex-col gap-1.5 px-4 py-3.5 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">New DocType</span>
        <div class="flex items-center gap-2 h-8 px-2.5 rounded bg-surface-gray-2 text-ink-gray-8">
          <Icon name="database" :size="14" class="text-ink-gray-6" /><span class="font-mono text-[13px]">{{ form.doctype_name || '-' }}</span>
        </div>
      </div>

      <div class="px-4 py-3.5 border-b border-outline-gray-1 flex flex-col gap-3">
        <FormControl type="textarea" label="Thank-you message" :rows="3"
          placeholder="Shown to respondents after they submit."
          :modelValue="form.thank_you_message" @update:modelValue="emit('update-meta', { thank_you_message: $event })" />
        <div>
          <FormControl type="text" label="Redirect URL after submit"
            placeholder="https://example.com/thanks"
            :modelValue="form.redirect_url" @update:modelValue="emit('update-meta', { redirect_url: $event })" />
          <span class="text-[11.5px] text-ink-gray-5 mt-1 block">Optional. If set, respondents go here instead of the thank-you screen.</span>
        </div>
      </div>

      <div class="flex flex-col gap-3 px-4 py-3.5 border-b border-outline-gray-1">
        <Switch :modelValue="!!form.collect_email" label="Collect email addresses" @update:modelValue="emit('update-meta', { collect_email: $event ? 1 : 0 })" />
        <Switch :modelValue="!form.allow_multiple" label="One response per user" @update:modelValue="emit('update-meta', { allow_multiple: $event ? 0 : 1 })" />
        <Switch :modelValue="!!form.login_required" label="Login required" @update:modelValue="emit('update-meta', { login_required: $event ? 1 : 0 })" />
        <Switch :modelValue="!!form.is_template" label="Use as template" @update:modelValue="emit('update-meta', { is_template: $event ? 1 : 0 })" />
      </div>

      <div v-if="prefs.devMode" class="px-4 py-3.5 mt-auto">
        <Button variant="subtle" theme="gray" class="w-full" @click="emit('open-dev')">
          <template #prefix><Icon name="code-2" :size="15" /></template>Open Developer view
        </Button>
      </div>
    </template>

    <!-- FIELD SETTINGS -->
    <template v-else>
      <div class="px-4 py-3 border-b border-outline-gray-1 flex items-center justify-between">
        <span class="text-sm font-medium text-ink-gray-9">Field settings</span>
        <span v-if="prefs.devMode" class="q-num flex items-center gap-1">
          <Icon v-if="field.fieldname" name="lock" :size="11" class="text-ink-gray-5" />{{ field.fieldname || '-' }}
        </span>
      </div>

      <div class="px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="select" label="Field type" :options="fieldTypeOptions"
          :modelValue="field.field_type" @update:modelValue="emit('update-field', field.name, { field_type: $event })" />
      </div>
      <div class="px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="text" label="Label" :modelValue="field.label" @update:modelValue="emit('update-field', field.name, { label: $event })" />
      </div>
      <div class="px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="text" label="Help text" placeholder="Optional" :modelValue="field.help_text" @update:modelValue="emit('update-field', field.name, { help_text: $event })" />
      </div>

      <div v-if="prefs.devMode" class="flex flex-col gap-1.5 px-4 py-3.5 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">Column name</span>
        <div class="flex items-center justify-between h-8 px-2.5 rounded bg-surface-gray-2 font-mono text-[13px]">
          <span class="text-ink-gray-8">{{ field.fieldname || '(derived at publish)' }}</span>
          <Icon :name="field.fieldname ? 'lock' : 'pencil'" :size="13" class="text-ink-gray-5" />
        </div>
        <span class="text-[11.5px] text-ink-gray-5">
          {{ field.fieldname ? 'Frozen at publish - relabeling won’t rename the column or orphan data.' : 'Derived from the label until you publish, then frozen.' }}
        </span>
      </div>

      <div v-if="prefs.devMode && linked" class="px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="select" label="Maps to field" :options="mapOptions"
          :modelValue="field.mapped_field || ''" @update:modelValue="emit('update-field', field.name, { mapped_field: $event })" />
        <span class="text-[11.5px] text-ink-gray-5 mt-1.5 block">
          {{ field.mapped_field ? `Fills ${form.target_doctype}.${field.mapped_field}` : 'Not mapped - ignored on submit.' }}
        </span>
      </div>

      <div v-if="hasOptions(field.field_type)" class="px-4 py-3.5 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">Options</span>
        <span class="text-[11.5px] text-ink-gray-5 block mt-1">Edit options inline on the card.</span>
      </div>

      <div class="flex flex-col gap-3 px-4 py-3.5 border-b border-outline-gray-1">
        <Switch :modelValue="!!field.reqd" label="Required field" @update:modelValue="emit('update-field', field.name, { reqd: $event ? 1 : 0 })" />
        <span v-if="field.field_type === 'email'" class="text-[11.5px] text-ink-gray-5">Checks for a valid email address.</span>
        <span v-if="field.field_type === 'number'" class="text-[11.5px] text-ink-gray-5">Whole numbers only.</span>
      </div>

      <div v-if="prefs.devMode" class="px-4 py-3.5 mt-auto bg-surface-gray-1">
        <div class="flex items-center justify-between mb-2">
          <span class="text-[10.5px] text-ink-gray-5 font-mono uppercase tracking-wider">Compiles to</span>
          <button class="text-xs text-ink-gray-7 hover:text-ink-gray-9" @click="emit('open-dev')">View schema →</button>
        </div>
        <div class="flex flex-col gap-1.5 font-mono text-[12px]">
          <div class="flex justify-between"><span class="text-ink-gray-5">fieldtype</span><span class="text-ink-gray-9">{{ FT[field.field_type].doctype }}</span></div>
          <div class="flex justify-between"><span class="text-ink-gray-5">reqd</span><span class="text-ink-gray-9">{{ field.reqd ? '1' : '0' }}</span></div>
        </div>
      </div>
    </template>
  </aside>
</template>
