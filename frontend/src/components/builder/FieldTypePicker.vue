<script setup>
import { Popover } from 'frappe-ui'
import Icon from '../Icon.vue'
import { FIELD_TYPES } from '../../fieldTypes'

// On-demand field-type picker (replaces the standing left palette). The parent supplies its own
// trigger via the #trigger slot (a button, a hover "+", etc.); picking a type emits `pick`.
defineProps({ placement: { type: String, default: 'bottom' } })
const emit = defineEmits(['pick'])
</script>

<template>
  <Popover :placement="placement">
    <template #target="{ togglePopover, isOpen }">
      <slot name="trigger" :toggle="togglePopover" :isOpen="isOpen" />
    </template>
    <template #body="{ close }">
      <div class="w-[300px] max-h-[min(28rem,var(--reka-popover-content-available-height))] overflow-y-auto rounded-xl border border-outline-gray-1 bg-surface-white shadow-2xl p-2 mt-1.5">
        <div class="px-1.5 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Add a field</div>
        <div class="grid grid-cols-2 gap-0.5">
          <button v-for="t in FIELD_TYPES" :key="t.id" type="button"
                  class="flex items-center gap-2 px-2 py-2 rounded-lg text-left hover:bg-surface-gray-2 transition-colors"
                  @click="emit('pick', t.id); close()">
            <Icon :name="t.icon" :size="16" class="text-ink-gray-6 shrink-0" />
            <span class="text-[13px] text-ink-gray-8 truncate">{{ t.label }}</span>
          </button>
        </div>
      </div>
    </template>
  </Popover>
</template>
