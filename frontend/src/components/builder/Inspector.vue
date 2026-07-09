<script setup>
import { computed, watch } from 'vue'
import { FormControl, Switch, createResource } from 'frappe-ui'
import Icon from '../Icon.vue'
import { FIELD_TYPES, FT, hasOptions, canHaveOther, canShuffleOptions, isText, canBeConditionSource, isGradable } from '../../fieldTypes'
import { prefs } from '../../data/prefs'

// Per-field inspector for dev mode — only mounts when a field is selected. Form-level settings
// (including storage/DocType config) live in the Form settings dialog, so there's no form branch.
const props = defineProps({ form: Object, field: Object })
const emit = defineEmits(['update-field', 'open-dev'])

// Conditional logic + quiz helpers (mirror Canvas; dev mode edits fields through this sidebar).
function priorSources(field) {
  const out = []
  for (const f of props.form.fields) {
    if (f.name === field.name) break
    if (canBeConditionSource(f.field_type) && f.field_key) out.push(f)
  }
  return out
}
function controllingField(field) {
  return props.form.fields.find((f) => f.field_key === field.condition_field)
}
function conditionValueOptions(field) {
  const ctrl = controllingField(field)
  if (!ctrl) return []
  if (ctrl.field_type === 'yes_no') return ['Yes', 'No']
  return (ctrl.options || '').split('\n').filter(Boolean)
}
function quizOptions(field) {
  if (field.field_type === 'yes_no') return ['Yes', 'No']
  return (field.options || '').split('\n').filter(Boolean)
}
function correctSet(field) {
  return (field.correct_answer || '').split('\n').filter(Boolean)
}
function isCorrect(field, opt) {
  return correctSet(field).includes(opt)
}
function toggleCorrect(field, opt) {
  const set = new Set(correctSet(field))
  if (set.has(opt)) set.delete(opt)
  else set.add(opt)
  emit('update-field', field.name, { correct_answer: [...set].join('\n') })
}

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
</script>

<template>
  <aside class="w-[312px] h-full shrink-0 border-l border-outline-gray-1 bg-surface-base flex flex-col overflow-y-auto">
    <!-- FIELD SETTINGS -->
    <template v-if="field">
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

      <!-- linear scale -->
      <div v-if="field.field_type === 'linear_scale'" class="flex flex-col gap-3 px-4 py-3.5 border-b border-outline-gray-1">
        <div class="flex gap-2">
          <FormControl type="select" label="From" class="flex-1" :options="[{ label: '0', value: 0 }, { label: '1', value: 1 }]"
            :modelValue="field.scale_min ?? 1" @update:modelValue="emit('update-field', field.name, { scale_min: +$event })" />
          <FormControl type="select" label="To" class="flex-1" :options="[2,3,4,5,6,7,8,9,10].map((n) => ({ label: `${n}`, value: n }))"
            :modelValue="field.scale_max ?? 5" @update:modelValue="emit('update-field', field.name, { scale_max: +$event })" />
        </div>
        <FormControl type="text" label="Low label" placeholder="Optional" :modelValue="field.min_label" @update:modelValue="emit('update-field', field.name, { min_label: $event })" />
        <FormControl type="text" label="High label" placeholder="Optional" :modelValue="field.max_label" @update:modelValue="emit('update-field', field.name, { max_label: $event })" />
      </div>

      <!-- number bounds -->
      <div v-if="field.field_type === 'number'" class="flex gap-2 px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="text" label="Min" placeholder="None" class="flex-1" :modelValue="field.min_value" @update:modelValue="emit('update-field', field.name, { min_value: $event })" />
        <FormControl type="text" label="Max" placeholder="None" class="flex-1" :modelValue="field.max_value" @update:modelValue="emit('update-field', field.name, { max_value: $event })" />
      </div>

      <!-- text validation -->
      <div v-if="isText(field.field_type)" class="flex flex-col gap-3 px-4 py-3.5 border-b border-outline-gray-1">
        <FormControl type="number" label="Max length" placeholder="No limit" :modelValue="field.max_length || ''" @update:modelValue="emit('update-field', field.name, { max_length: +$event || 0 })" />
        <FormControl type="text" label="Pattern (regex)" placeholder="Optional" :modelValue="field.validation_pattern" @update:modelValue="emit('update-field', field.name, { validation_pattern: $event })" />
        <FormControl type="text" label="Custom error" placeholder="Optional" :modelValue="field.error_message" @update:modelValue="emit('update-field', field.name, { error_message: $event })" />
      </div>

      <!-- choice: shuffle + other -->
      <div v-if="canShuffleOptions(field.field_type)" class="flex flex-col gap-3 px-4 py-3.5 border-b border-outline-gray-1">
        <Switch :modelValue="!!field.shuffle_options" label="Shuffle options" @update:modelValue="emit('update-field', field.name, { shuffle_options: $event ? 1 : 0 })" />
        <Switch v-if="canHaveOther(field.field_type)" :modelValue="!!field.has_other" label="Add “Other” option" @update:modelValue="emit('update-field', field.name, { has_other: $event ? 1 : 0 })" />
      </div>

      <div class="flex flex-col gap-3 px-4 py-3.5 border-b border-outline-gray-1">
        <Switch :modelValue="!!field.reqd" label="Required field" @update:modelValue="emit('update-field', field.name, { reqd: $event ? 1 : 0 })" />
        <span v-if="field.field_type === 'email'" class="text-[11.5px] text-ink-gray-5">Checks for a valid email address.</span>
        <span v-if="field.field_type === 'number'" class="text-[11.5px] text-ink-gray-5">Whole numbers only.</span>
      </div>

      <!-- conditional logic -->
      <div v-if="priorSources(field).length" class="flex flex-col gap-2 px-4 py-3.5 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">Conditional logic</span>
        <FormControl type="select" :modelValue="field.condition_field || ''"
          :options="[{ label: 'Always show', value: '' }, ...priorSources(field).map((s) => ({ label: `Show if “${s.label}”`, value: s.field_key }))]"
          @update:modelValue="emit('update-field', field.name, { condition_field: $event })" />
        <template v-if="field.condition_field">
          <FormControl type="select" :modelValue="field.condition_operator || 'equals'"
            :options="[{ label: 'equals', value: 'equals' }, { label: 'is not', value: 'not_equals' }, { label: 'contains', value: 'contains' }]"
            @update:modelValue="emit('update-field', field.name, { condition_operator: $event })" />
          <FormControl v-if="conditionValueOptions(field).length" type="select" :modelValue="field.condition_value || ''"
            :options="[{ label: 'Choose a value', value: '' }, ...conditionValueOptions(field).map((v) => ({ label: v, value: v }))]"
            @update:modelValue="emit('update-field', field.name, { condition_value: $event })" />
          <FormControl v-else type="text" placeholder="Value" :modelValue="field.condition_value"
            @update:modelValue="emit('update-field', field.name, { condition_value: $event })" />
        </template>
      </div>

      <!-- quiz: points + correct answer -->
      <div v-if="form.is_quiz && isGradable(field.field_type)" class="flex flex-col gap-2.5 px-4 py-3.5 border-b border-outline-gray-1">
        <span class="text-xs text-ink-gray-7">Quiz</span>
        <FormControl type="number" label="Points" :modelValue="field.points || ''"
          @update:modelValue="emit('update-field', field.name, { points: +$event || 0 })" />
        <span class="text-[11.5px] text-ink-gray-5">Correct answer</span>
        <div v-if="hasOptions(field.field_type) || field.field_type === 'yes_no'" class="flex flex-wrap gap-1.5">
          <button v-for="o in quizOptions(field)" :key="o" type="button"
                  class="px-2.5 h-7 rounded-md border text-sm transition-colors"
                  :class="isCorrect(field, o) ? 'border-ink-green-500 bg-surface-green-2 text-ink-green-700' : 'border-outline-gray-2 text-ink-gray-7 hover:bg-surface-gray-2'"
                  @click="toggleCorrect(field, o)">{{ o }}</button>
        </div>
        <FormControl v-else type="text" placeholder="Expected answer" :modelValue="field.correct_answer"
          @update:modelValue="emit('update-field', field.name, { correct_answer: $event })" />
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
