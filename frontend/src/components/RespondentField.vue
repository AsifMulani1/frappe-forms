<script setup>
// Presentational renderer for one respondent field. All answer state lives in the parent
// (PublicForm); this component only draws a field type and emits the user's interactions up.
import { DatePicker, FormControl, TimePicker } from 'frappe-ui'
import Icon from './Icon.vue'
import SignaturePad from './SignaturePad.vue'

const props = defineProps({
  field: { type: Object, required: true },
  value: { default: undefined },
  options: { type: Array, default: () => [] },
  error: { default: false },
  otherOn: { type: Boolean, default: false },
  otherText: { type: String, default: '' },
  uploading: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
})

const emit = defineEmits([
  'set', 'toggleCb', 'selectChoice', 'selectOther', 'setOther', 'onDropdown',
  'setGridMc', 'toggleGridCb', 'upload', 'clearFile',
])

// Linear-scale tick values, clamped to a sane 1..5 fallback for a bad min/max.
function scaleRange(f) {
  let lo = Number.isFinite(+f.scale_min) ? +f.scale_min : 1
  let hi = Number.isFinite(+f.scale_max) ? +f.scale_max : 5
  if (hi <= lo || hi - lo > 14) { lo = 1; hi = 5 }
  return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
}
function gridMcChecked(row, col) { return (props.value || {})[row] === col }
function gridCbChecked(row, col) {
  const v = (props.value || {})[row]
  return Array.isArray(v) && v.includes(col)
}
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <div class="flex flex-col gap-1">
      <span class="text-md font-medium text-ink-gray-9 leading-snug">
        {{ field.label }}<span v-if="field.reqd" class="text-ink-red-400 ml-0.5">*</span>
      </span>
      <span v-if="field.help_text" class="text-sm text-ink-gray-5 leading-snug">{{ field.help_text }}</span>
    </div>

    <FormControl v-if="field.field_type === 'short_answer'" type="text" size="lg" placeholder="Your answer"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    <FormControl v-else-if="field.field_type === 'email'" type="email" size="lg" placeholder="name@example.com"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    <FormControl v-else-if="field.field_type === 'number'" type="number" size="lg" placeholder="0"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    <FormControl v-else-if="field.field_type === 'phone'" type="tel" size="lg" placeholder="+1 (555) 000-0000"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    <div v-else-if="field.field_type === 'time'" class="r-picker">
      <TimePicker placeholder="Select time"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    </div>
    <FormControl v-else-if="field.field_type === 'paragraph'" type="textarea" size="lg" :rows="4" placeholder="Your answer"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    <FormControl v-else-if="field.field_type === 'address'" type="textarea" size="lg" :rows="3" placeholder="Street, city, state, ZIP"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    <div v-else-if="field.field_type === 'date'" class="r-picker">
      <DatePicker placeholder="Select date"
           :modelValue="value || ''" @update:modelValue="emit('set', $event)" />
    </div>
    <template v-else-if="field.field_type === 'dropdown'">
      <FormControl type="select" size="lg"
           :options="[{ label: 'Choose an option', value: '' }, ...options.map((o) => ({ label: o, value: o })), ...(field.has_other ? [{ label: 'Other…', value: '__other__' }] : [])]"
           :modelValue="otherOn ? '__other__' : (value || '')" @update:modelValue="emit('onDropdown', $event)" />
      <FormControl v-if="field.has_other && otherOn" type="text" size="lg" placeholder="Your answer"
           :modelValue="otherText || ''" @update:modelValue="emit('setOther', $event)" />
    </template>

    <!-- file upload -->
    <label v-else-if="field.field_type === 'file_upload'"
           class="flex items-center gap-2.5 h-10 px-3 rounded-md bg-surface-gray-2 hover:bg-surface-gray-3 transition-colors cursor-pointer">
      <input type="file" class="hidden" @change="emit('upload', $event)" />
      <Icon :name="value ? 'file-check-2' : 'paperclip'" :size="16" class="text-ink-gray-6 shrink-0" />
      <span class="text-base text-ink-gray-8 truncate flex-1">
        {{ uploading ? 'Uploading…' : (fileName || 'Choose a file') }}
      </span>
      <button v-if="value" type="button" class="text-ink-gray-4 hover:text-ink-gray-7 shrink-0" @click.prevent.stop="emit('clearFile')"><Icon name="x" :size="15" /></button>
    </label>

    <!-- signature -->
    <SignaturePad v-else-if="field.field_type === 'signature'"
           :modelValue="value" @update:modelValue="emit('set', $event)" />

    <div v-else-if="field.field_type === 'rating'" class="flex gap-1">
      <span v-for="s in 5" :key="s" class="star" :class="{ on: s <= (value || 0) }" @click="emit('set', s)">
        <Icon name="star" :size="28" :style="{ fill: s <= (value || 0) ? 'var(--amber-500)' : 'none' }" />
      </span>
    </div>

    <div v-else-if="field.field_type === 'linear_scale'" class="flex items-end gap-x-5 gap-y-2 flex-wrap pt-1">
      <span v-if="field.min_label" class="text-xs text-ink-gray-5 shrink-0">{{ field.min_label }}</span>
      <div class="flex items-center gap-3.5">
        <button v-for="n in scaleRange(field)" :key="n" type="button" class="flex flex-col items-center gap-1.5"
                @click="emit('set', n)">
          <span class="text-sm text-ink-gray-6">{{ n }}</span>
          <span class="r-radio" :style="value === n ? 'border-color:var(--accent)' : ''">
            <span v-if="value === n" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" />
          </span>
        </button>
      </div>
      <span v-if="field.max_label" class="text-xs text-ink-gray-5 shrink-0">{{ field.max_label }}</span>
    </div>

    <div v-else-if="field.field_type === 'mc_grid' || field.field_type === 'checkbox_grid'" class="overflow-x-auto -mx-1 px-1">
      <table class="r-grid">
        <thead>
          <tr>
            <th></th>
            <th v-for="col in field.options" :key="col" class="px-3 pb-2 text-sm font-normal text-ink-gray-6 text-center">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in field.grid_rows" :key="row" class="border-t border-outline-gray-1">
            <td class="py-2.5 pr-4 text-base text-ink-gray-8">{{ row }}</td>
            <td v-for="col in field.options" :key="col" class="px-3 text-center">
              <button v-if="field.field_type === 'mc_grid'" type="button" class="r-radio mx-auto"
                      :style="gridMcChecked(row, col) ? 'border-color:var(--accent)' : ''" @click="emit('setGridMc', { row, col })">
                <span v-if="gridMcChecked(row, col)" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" />
              </button>
              <button v-else type="button" class="r-cb mx-auto" :class="{ 'grid-cb-on': gridCbChecked(row, col) }" @click="emit('toggleGridCb', { row, col })">
                <Icon v-if="gridCbChecked(row, col)" name="check" :size="12" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="field.field_type === 'yes_no'" class="flex gap-2">
      <div v-for="o in ['Yes', 'No']" :key="o" class="r-choice boxed min-w-[92px] flex-none"
           :class="{ sel: value === o }" @click="emit('set', o)">
        <span class="r-radio"><span v-if="value === o" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
        <span class="text-base text-ink-gray-8">{{ o }}</span>
      </div>
    </div>

    <div v-else-if="field.field_type === 'single_choice'" class="flex flex-col gap-1">
      <div v-for="o in options" :key="o" class="r-choice"
           :class="{ sel: !otherOn && value === o }" @click="emit('selectChoice', o)">
        <span class="r-radio"><span v-if="!otherOn && value === o" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
        <span class="text-base text-ink-gray-8">{{ o }}</span>
      </div>
      <div v-if="field.has_other" class="r-choice" :class="{ sel: otherOn }" @click="emit('selectOther')">
        <span class="r-radio"><span v-if="otherOn" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
        <span class="text-base text-ink-gray-8 shrink-0">Other:</span>
        <input class="ml-1 flex-1 bg-transparent outline-none border-b border-outline-gray-2 focus:border-outline-gray-4 text-base text-ink-gray-8 py-0.5"
               :value="otherText || ''" placeholder="Your answer"
               @click.stop @input="emit('setOther', $event.target.value)" />
      </div>
    </div>

    <div v-else-if="field.field_type === 'checkboxes'" class="flex flex-col gap-1">
      <div v-for="o in options" :key="o" class="r-choice"
           :class="{ sel: (value || []).includes(o) }" @click="emit('toggleCb', o)">
        <span class="r-cb"><Icon v-if="(value || []).includes(o)" name="check" :size="12" /></span>
        <span class="text-base text-ink-gray-8">{{ o }}</span>
      </div>
    </div>

    <span v-if="error" class="text-xs text-ink-red-500 flex items-center gap-1">
      <Icon name="circle-alert" :size="12" />{{ typeof error === 'string' ? error : 'This field is required.' }}
    </span>
  </div>
</template>
