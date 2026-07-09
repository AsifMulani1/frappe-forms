<script setup>
import { Button, FormControl, Switch } from 'frappe-ui'
import Icon from '../Icon.vue'
import FieldTypePicker from './FieldTypePicker.vue'
import { FT, isLayout, canHaveOther, canShuffleOptions, isText, isGrid, canBeConditionSource, isGradable, hasOptions } from '../../fieldTypes'
import { prefs } from '../../data/prefs'
import { optionsArray, rowsArray, scaleRange, correctSet, isCorrect, quizOptions, setLine, addLine, removeLine, toggleLine } from './fieldEditing'

import { ref } from 'vue'

const props = defineProps({
  form: Object,
  selectedId: String,
})
const emit = defineEmits([
  'select', 'update-meta', 'update-field', 'delete', 'duplicate', 'move', 'reorder', 'add',
])

// Pointer-based reorder. The grabbed card follows the pointer via transform; neighbours slide
// out of the way (CSS-transitioned) to reveal the drop slot. Drop thresholds use the cards'
// original centers, so variable card heights are handled correctly.
const canvasEl = ref(null)
const drag = ref(null)

function startDrag(e, i) {
  if (e.button) return
  e.preventDefault()
  const cards = [...canvasEl.value.querySelectorAll('.q-card')]
  const rows = cards.map((el) => {
    const r = el.getBoundingClientRect()
    return { center: r.top + r.height / 2 }
  })
  drag.value = { from: i, to: i, startY: e.clientY, dy: 0, rows, slot: cards[i].getBoundingClientRect().height + 16 }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', endDrag, { once: true })
  document.body.style.userSelect = 'none'
}
function onDragMove(e) {
  const d = drag.value
  if (!d) return
  d.dy = e.clientY - d.startY
  let to = d.from
  for (let j = d.from + 1; j < d.rows.length; j++) if (e.clientY > d.rows[j].center) to = j
  for (let j = d.from - 1; j >= 0; j--) if (e.clientY < d.rows[j].center) to = j
  d.to = to
}
function endDrag() {
  const d = drag.value
  window.removeEventListener('pointermove', onDragMove)
  document.body.style.userSelect = ''
  if (d && d.to !== d.from) emit('reorder', d.from, d.to)
  drag.value = null
}
function cardStyle(i) {
  const d = drag.value
  if (!d) return null
  if (i === d.from) return { transform: `translateY(${d.dy}px) scale(1.01)` }
  let shift = 0
  if (d.from < d.to && i > d.from && i <= d.to) shift = -d.slot
  else if (d.from > d.to && i >= d.to && i < d.from) shift = d.slot
  return { transform: `translateY(${shift}px)` }
}

// Option/grid-row editing wraps the pure helpers in fieldEditing.js and emits the result.
function setOption(field, i, val) { emit('update-field', field.name, { options: setLine(field.options, i, val) }) }
function addOption(field) { emit('update-field', field.name, { options: addLine(field.options, 'Option') }) }
function removeOption(field, i) { emit('update-field', field.name, { options: removeLine(field.options, i) }) }
function setRow(field, i, val) { emit('update-field', field.name, { grid_rows: setLine(field.grid_rows, i, val) }) }
function addRow(field) { emit('update-field', field.name, { grid_rows: addLine(field.grid_rows, 'Row') }) }
function removeRow(field, i) { emit('update-field', field.name, { grid_rows: removeLine(field.grid_rows, i) }) }

// Conditional logic: fields ABOVE this one that can drive its visibility (saved, choice-like).
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

// Quiz: mark correct option(s); correct_answer is stored newline-joined.
function toggleCorrect(field, opt) {
  emit('update-field', field.name, { correct_answer: toggleLine(field.correct_answer, opt) })
}
</script>

<template>
  <div class="flex-1 overflow-auto bg-surface-base">
    <div ref="canvasEl" class="max-w-[720px] mx-auto px-3 pt-7 pb-20 sm:px-6">
      <!-- form header card -->
      <div class="public-card overflow-hidden mb-4 cursor-pointer"
           :class="{ 'ring-1 ring-ink-gray-9': selectedId === null }"
           @click="emit('select', null)">
        <img v-if="form.cover_image" :src="form.cover_image" alt="Cover" class="w-full h-[160px] object-cover" />
        <div class="px-4 py-5 sm:px-6">
          <input class="edit-line text-[22px] font-medium text-ink-gray-9" :value="form.title"
                 placeholder="Form title" @click.stop
                 @input="emit('update-meta', { title: $event.target.value })" />
          <textarea class="edit-line text-sm text-ink-gray-6 mt-1.5 resize-none leading-relaxed" rows="2"
                    :value="form.description" placeholder="Form description" @click.stop
                    @input="emit('update-meta', { description: $event.target.value })" />
        </div>
      </div>

      <!-- question cards, each preceded by a hover-reveal insert point -->
      <template v-for="(f, i) in form.fields" :key="f.name">
        <div class="insert-gap">
          <FieldTypePicker @pick="emit('add', $event, i)">
            <template #trigger="{ toggle, isOpen }">
              <button type="button" class="insert-btn" :class="{ 'is-open': isOpen }" title="Insert field here" @click.stop="toggle">
                <Icon name="plus" :size="14" />
              </button>
            </template>
          </FieldTypePicker>
        </div>
        <div class="q-card group" :class="{ selected: selectedId === f.name, dragging: drag && drag.from === i }"
             :style="cardStyle(i)"
             @click="emit('select', f.name)">
        <div class="relative flex items-center gap-1">
          <!-- drag handle: hover-reveal, centered on the label line, tucked in the left gutter -->
          <span class="drag-handle absolute -left-5 top-1/2 -translate-y-1/2 text-ink-gray-3 hover:text-ink-gray-6 cursor-grab opacity-0 group-hover:opacity-100 transition-opacity touch-none"
                title="Drag to reorder" @click.stop @pointerdown="startDrag($event, i)">
            <Icon name="grip-vertical" :size="15" />
          </span>
          <input class="edit-line min-w-0 max-w-full" style="field-sizing:content;width:auto"
                 :class="isLayout(f.field_type) ? 'text-[18px] font-semibold text-ink-gray-9' : 'text-[15px] font-medium text-ink-gray-9'"
                 :value="f.label" :placeholder="isLayout(f.field_type) ? 'Section title' : 'Question label'"
                 @click.stop @input="emit('update-field', f.name, { label: $event.target.value })" />
          <span v-if="f.reqd && !isLayout(f.field_type)" class="text-base text-ink-red-500 shrink-0 -ml-0.5" title="Required">*</span>
          <!-- actions on the same row as the label, so selecting never grows the card -->
          <div v-if="selectedId === f.name" class="flex items-center gap-0.5 shrink-0 ml-auto pl-2" @click.stop>
            <button class="p-1 rounded hover:bg-surface-gray-2 text-ink-gray-6 disabled:opacity-30" :disabled="i === 0" title="Move up" @click="emit('move', f.name, -1)"><Icon name="chevron-up" :size="15" /></button>
            <button class="p-1 rounded hover:bg-surface-gray-2 text-ink-gray-6 disabled:opacity-30" :disabled="i === form.fields.length - 1" title="Move down" @click="emit('move', f.name, 1)"><Icon name="chevron-down" :size="15" /></button>
            <button class="p-1 rounded hover:bg-surface-gray-2 text-ink-gray-6" title="Duplicate" @click="emit('duplicate', f.name)"><Icon name="copy" :size="14" /></button>
            <button class="p-1 rounded hover:bg-surface-gray-2 text-ink-red-500" title="Delete" @click="emit('delete', f.name)"><Icon name="trash-2" :size="14" /></button>
          </div>
        </div>
        <input v-if="f.help_text || selectedId === f.name" class="edit-line text-[13px] text-ink-gray-5 mb-1"
               :value="f.help_text" :placeholder="isLayout(f.field_type) ? 'Add a subtitle (optional)' : 'Add a description (optional)'"
               @click.stop @input="emit('update-field', f.name, { help_text: $event.target.value })" />
        <div v-if="isLayout(f.field_type)" class="inline-flex items-center gap-1 mt-1 text-[11px] font-medium text-ink-gray-5 bg-surface-gray-2 rounded px-1.5 py-0.5 w-fit">
          <Icon name="corner-down-right" :size="11" />Starts a new page for respondents
        </div>

        <!-- preview controls (none for display-only blocks like section headers) -->
        <div v-if="!isLayout(f.field_type)" class="mt-2.5">
          <div v-if="['short_answer', 'email', 'number', 'phone'].includes(f.field_type)" class="prev-input max-w-[340px] gap-2">
            <Icon v-if="f.field_type === 'phone'" name="phone" :size="14" class="text-ink-gray-4" />
            <span>{{ f.field_type === 'email' ? 'name@example.com' : f.field_type === 'number' ? '0' : f.field_type === 'phone' ? '+1 (555) 000-0000' : 'Short answer text' }}</span>
          </div>
          <div v-else-if="['paragraph', 'address'].includes(f.field_type)" class="prev-input items-start pt-2.5" style="height:60px">{{ f.field_type === 'address' ? 'Street, city, state, ZIP' : 'Long answer text' }}</div>
          <div v-else-if="f.field_type === 'time'" class="prev-input max-w-[160px] gap-2">
            <Icon name="clock" :size="14" class="text-ink-gray-4" /><span>--:--</span>
          </div>
          <div v-else-if="f.field_type === 'file_upload'" class="prev-input justify-center border-dashed gap-2 max-w-[340px] text-ink-gray-5">
            <Icon name="paperclip" :size="14" class="text-ink-gray-4" /><span>Click to upload a file</span>
          </div>
          <div v-else-if="f.field_type === 'signature'" class="border border-dashed border-outline-gray-2 rounded-md bg-surface-gray-1 flex items-center justify-center text-ink-gray-4 gap-2 max-w-[340px]" style="height:90px">
            <Icon name="pen-line" :size="16" /><span class="text-sm">Sign here</span>
          </div>
          <div v-else-if="f.field_type === 'dropdown'" class="prev-input max-w-[340px] justify-between">
            <span>Choose an option</span><Icon name="chevron-down" :size="15" class="text-ink-gray-4" />
          </div>
          <div v-else-if="f.field_type === 'date'" class="prev-input max-w-[220px] gap-2">
            <Icon name="calendar" :size="14" class="text-ink-gray-4" /><span>dd / mm / yyyy</span>
          </div>
          <div v-else-if="f.field_type === 'rating'" class="flex gap-1">
            <Icon v-for="s in 5" :key="s" name="star" :size="22" class="text-ink-gray-3" />
          </div>
          <div v-else-if="f.field_type === 'linear_scale'" class="flex items-center gap-3">
            <span v-if="f.min_label" class="text-sm text-ink-gray-5">{{ f.min_label }}</span>
            <div class="flex items-center gap-3">
              <div v-for="n in scaleRange(f)" :key="n" class="flex flex-col items-center gap-1">
                <span class="text-[12px] text-ink-gray-6">{{ n }}</span><span class="prev-radio" />
              </div>
            </div>
            <span v-if="f.max_label" class="text-sm text-ink-gray-5">{{ f.max_label }}</span>
          </div>

          <!-- grid (rows x columns) -->
          <div v-else-if="isGrid(f.field_type)" class="overflow-x-auto">
            <table class="grid-prev">
              <thead>
                <tr>
                  <th class="w-[120px]"></th>
                  <th v-for="(col, ci) in optionsArray(f)" :key="ci">
                    <input v-if="selectedId === f.name" class="edit-line text-[12px] text-center w-[72px]" :value="col"
                           :placeholder="`Col ${ci + 1}`" @click.stop @input="setOption(f, ci, $event.target.value)" />
                    <span v-else class="text-[12px] text-ink-gray-6">{{ col }}</span>
                  </th>
                  <th v-if="selectedId === f.name" class="w-7">
                    <button class="text-ink-gray-4 hover:text-ink-gray-7" title="Add column" @click.stop="addOption(f)"><Icon name="plus" :size="13" /></button>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in rowsArray(f)" :key="ri">
                  <td class="text-left">
                    <input v-if="selectedId === f.name" class="edit-line text-[13px]" :value="row"
                           :placeholder="`Row ${ri + 1}`" @click.stop @input="setRow(f, ri, $event.target.value)" />
                    <span v-else class="text-[13px] text-ink-gray-7">{{ row }}</span>
                  </td>
                  <td v-for="(col, ci) in optionsArray(f)" :key="ci" class="text-center">
                    <span :class="f.field_type === 'mc_grid' ? 'prev-radio' : 'prev-check'" class="inline-block" />
                  </td>
                  <td v-if="selectedId === f.name" class="text-center">
                    <button v-if="rowsArray(f).length > 1" class="text-ink-gray-4 hover:text-ink-gray-7" title="Remove row" @click.stop="removeRow(f, ri)"><Icon name="x" :size="13" /></button>
                  </td>
                </tr>
                <tr v-if="selectedId === f.name">
                  <td class="text-left"><button class="text-sm text-ink-gray-6 hover:text-ink-gray-9" @click.stop="addRow(f)">+ Add row</button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else-if="f.field_type === 'yes_no'" class="flex items-center gap-2">
            <span class="prev-radio" /><span class="text-sm text-ink-gray-5">Yes</span>
          </div>
          <div v-else-if="['single_choice', 'checkboxes'].includes(f.field_type)" class="flex flex-col gap-2.5">
            <div v-for="(opt, oi) in optionsArray(f)" :key="oi" class="opt-row">
              <span :class="f.field_type === 'single_choice' ? 'prev-radio' : 'prev-check'" />
              <input v-if="selectedId === f.name" class="edit-line text-[13px]" :value="opt" :placeholder="`Option ${oi + 1}`"
                     @click.stop @input="setOption(f, oi, $event.target.value)" />
              <span v-else class="text-sm text-ink-gray-7">{{ opt }}</span>
              <button v-if="selectedId === f.name && optionsArray(f).length > 1" class="p-0.5 rounded hover:bg-surface-gray-2 text-ink-gray-4"
                      title="Remove option" @click.stop="removeOption(f, oi)"><Icon name="x" :size="13" /></button>
            </div>
            <div v-if="f.has_other" class="opt-row">
              <span :class="f.field_type === 'single_choice' ? 'prev-radio' : 'prev-check'" />
              <span class="text-sm text-ink-gray-5 italic">Other…</span>
            </div>
            <div v-if="selectedId === f.name" class="opt-row cursor-pointer" @click.stop="addOption(f)">
              <span :class="f.field_type === 'single_choice' ? 'prev-radio' : 'prev-check'" style="opacity:.4" />
              <span class="text-sm text-ink-gray-6">Add option</span>
            </div>
          </div>
          <!-- dropdown "Other" hint -->
          <div v-if="f.field_type === 'dropdown' && f.has_other" class="text-[12px] text-ink-gray-5 italic mt-1.5">+ Other…</div>
        </div>

        <!-- inline field controls (minimal mode): change type + required + per-type options -->
        <div v-if="!prefs.devMode && selectedId === f.name"
             class="flex flex-col gap-3 mt-4 pt-3 border-t border-outline-gray-1" @click.stop>
          <div class="flex items-center gap-3">
            <FieldTypePicker title="Change type" :selected="f.field_type"
                             @pick="emit('update-field', f.name, { field_type: $event })">
              <template #trigger="{ toggle }">
                <button @click="toggle"
                        class="inline-flex items-center gap-1.5 h-7 px-2 rounded-md border border-outline-gray-2 text-sm text-ink-gray-7 hover:bg-surface-gray-2 transition-colors">
                  <Icon :name="FT[f.field_type].icon" :size="14" />{{ FT[f.field_type].label }}
                  <Icon name="chevron-down" :size="13" class="text-ink-gray-4" />
                </button>
              </template>
            </FieldTypePicker>
            <div v-if="!isLayout(f.field_type)" class="ml-auto flex items-center gap-2">
              <span class="text-sm text-ink-gray-7">Required</span>
              <Switch :modelValue="!!f.reqd" @update:modelValue="emit('update-field', f.name, { reqd: $event ? 1 : 0 })" />
            </div>
          </div>

          <!-- linear scale: range + end labels -->
          <div v-if="f.field_type === 'linear_scale'" class="flex flex-wrap items-end gap-3">
            <label class="flex flex-col gap-1"><span class="text-[12px] text-ink-gray-6">From</span>
              <select class="cfg-input w-[64px]" :value="f.scale_min ?? 1" @change="emit('update-field', f.name, { scale_min: +$event.target.value })">
                <option v-for="n in [0, 1]" :key="n" :value="n">{{ n }}</option>
              </select></label>
            <label class="flex flex-col gap-1"><span class="text-[12px] text-ink-gray-6">To</span>
              <select class="cfg-input w-[64px]" :value="f.scale_max ?? 5" @change="emit('update-field', f.name, { scale_max: +$event.target.value })">
                <option v-for="n in [2, 3, 4, 5, 6, 7, 8, 9, 10]" :key="n" :value="n">{{ n }}</option>
              </select></label>
            <input class="cfg-input flex-1 min-w-[120px]" :value="f.min_label" placeholder="Label for low (optional)"
                   @input="emit('update-field', f.name, { min_label: $event.target.value })" />
            <input class="cfg-input flex-1 min-w-[120px]" :value="f.max_label" placeholder="Label for high (optional)"
                   @input="emit('update-field', f.name, { max_label: $event.target.value })" />
          </div>

          <!-- number: min / max -->
          <div v-if="f.field_type === 'number'" class="flex items-end gap-3">
            <input class="cfg-input w-[100px]" :value="f.min_value" placeholder="Min" inputmode="numeric"
                   @input="emit('update-field', f.name, { min_value: $event.target.value })" />
            <input class="cfg-input w-[100px]" :value="f.max_value" placeholder="Max" inputmode="numeric"
                   @input="emit('update-field', f.name, { max_value: $event.target.value })" />
          </div>

          <!-- text: max length -->
          <div v-if="isText(f.field_type)" class="flex items-center gap-2">
            <span class="text-sm text-ink-gray-7">Max length</span>
            <input class="cfg-input w-[100px]" :value="f.max_length || ''" placeholder="No limit" inputmode="numeric"
                   @input="emit('update-field', f.name, { max_length: +$event.target.value || 0 })" />
          </div>

          <!-- choice: shuffle + other -->
          <div v-if="canShuffleOptions(f.field_type)" class="flex flex-wrap items-center gap-x-6 gap-y-2">
            <label class="flex items-center gap-2"><Switch :modelValue="!!f.shuffle_options" @update:modelValue="emit('update-field', f.name, { shuffle_options: $event ? 1 : 0 })" /><span class="text-sm text-ink-gray-7">Shuffle options</span></label>
            <label v-if="canHaveOther(f.field_type)" class="flex items-center gap-2"><Switch :modelValue="!!f.has_other" @update:modelValue="emit('update-field', f.name, { has_other: $event ? 1 : 0 })" /><span class="text-sm text-ink-gray-7">Add “Other”</span></label>
          </div>

          <!-- conditional logic: show this field only when a prior field matches -->
          <div v-if="!isLayout(f.field_type) && priorSources(f).length" class="flex flex-col gap-2 pt-1">
            <div class="flex items-center gap-2 text-[12px] text-ink-gray-6"><Icon name="git-branch" :size="13" />Conditional logic</div>
            <div class="flex flex-wrap items-center gap-2">
              <select class="cfg-input min-w-[150px]" :value="f.condition_field || ''"
                      @change="emit('update-field', f.name, { condition_field: $event.target.value })">
                <option value="">Always show</option>
                <option v-for="s in priorSources(f)" :key="s.field_key" :value="s.field_key">Show if “{{ s.label }}”</option>
              </select>
              <template v-if="f.condition_field">
                <select class="cfg-input w-[120px]" :value="f.condition_operator || 'equals'"
                        @change="emit('update-field', f.name, { condition_operator: $event.target.value })">
                  <option value="equals">equals</option>
                  <option value="not_equals">is not</option>
                  <option value="contains">contains</option>
                </select>
                <select v-if="conditionValueOptions(f).length" class="cfg-input min-w-[120px]" :value="f.condition_value || ''"
                        @change="emit('update-field', f.name, { condition_value: $event.target.value })">
                  <option value="">Choose a value</option>
                  <option v-for="v in conditionValueOptions(f)" :key="v" :value="v">{{ v }}</option>
                </select>
                <input v-else class="cfg-input min-w-[120px]" :value="f.condition_value" placeholder="Value"
                       @input="emit('update-field', f.name, { condition_value: $event.target.value })" />
              </template>
            </div>
          </div>

          <!-- quiz: points + correct answer(s) -->
          <div v-if="form.is_quiz && isGradable(f.field_type)" class="flex flex-col gap-2 pt-1 border-t border-outline-gray-1">
            <div class="flex items-center gap-2">
              <Icon name="award" :size="13" class="text-ink-gray-6" />
              <span class="text-sm text-ink-gray-7">Points</span>
              <input class="cfg-input w-[80px]" :value="f.points || ''" placeholder="0" inputmode="numeric"
                     @input="emit('update-field', f.name, { points: +$event.target.value || 0 })" />
            </div>
            <div class="flex flex-col gap-1.5">
              <span class="text-[12px] text-ink-gray-6">Correct answer</span>
              <div v-if="hasOptions(f.field_type) || f.field_type === 'yes_no'" class="flex flex-wrap gap-1.5">
                <button v-for="o in quizOptions(f)" :key="o" type="button"
                        class="px-2.5 h-7 rounded-md border text-sm transition-colors"
                        :class="isCorrect(f, o) ? 'border-ink-green-500 bg-surface-green-2 text-ink-green-700' : 'border-outline-gray-2 text-ink-gray-7 hover:bg-surface-gray-2'"
                        @click="toggleCorrect(f, o)">
                  <Icon v-if="isCorrect(f, o)" name="check" :size="12" class="inline -mt-0.5 mr-1" />{{ o }}
                </button>
              </div>
              <input v-else class="cfg-input max-w-[280px]" :value="f.correct_answer" placeholder="Expected answer"
                     @input="emit('update-field', f.name, { correct_answer: $event.target.value })" />
            </div>
          </div>
        </div>
        </div>
      </template>

      <!-- empty state -->
      <div v-if="!form.fields.length" class="flex flex-col items-center justify-center text-center border border-dashed border-outline-gray-2 rounded-[10px] bg-surface-base py-12">
        <Icon name="plus-circle" :size="26" class="text-ink-gray-4" />
        <span class="text-base text-ink-gray-7 mt-3">No fields yet</span>
        <span class="text-sm text-ink-gray-5 mt-1">Add your first field to get started.</span>
        <FieldTypePicker class="mt-4" @pick="emit('add', $event, 0)">
          <template #trigger="{ toggle }">
            <Button variant="solid" theme="gray" @click="toggle">
              <template #prefix><Icon name="plus" :size="15" /></template>Add field
            </Button>
          </template>
        </FieldTypePicker>
      </div>

      <div v-else class="flex justify-center mt-4">
        <FieldTypePicker placement="top" @pick="emit('add', $event)">
          <template #trigger="{ toggle }">
            <Button variant="outline" theme="gray" @click="toggle">
              <template #prefix><Icon name="plus" :size="15" /></template>Add field
            </Button>
          </template>
        </FieldTypePicker>
      </div>
    </div>
  </div>
</template>
