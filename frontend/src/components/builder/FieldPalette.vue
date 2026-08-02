<script setup>
import Icon from '../Icon.vue'
import { FIELD_TYPES } from '../../fieldTypes'
import { prefs } from '../../data/prefs'
defineEmits(['add'])
</script>

<template>
  <aside class="w-[248px] h-full shrink-0 border-r border-outline-gray-1 bg-surface-base flex flex-col overflow-y-auto">
    <div class="px-4 py-3 border-b border-outline-gray-1">
      <span class="text-xs text-ink-gray-5">Add a field</span>
    </div>
    <div class="flex flex-col px-2 py-2 gap-0.5">
      <div v-for="t in FIELD_TYPES" :key="t.id" class="palette-item" :title="`Add ${t.label}`" @click="$emit('add', t.id)">
        <span class="pi-icon"><Icon :name="t.icon" :size="15" /></span>
        <div class="flex flex-col gap-px flex-1 min-w-0">
          <span class="text-sm text-ink-gray-8">{{ t.label }}</span>
          <span class="text-2xs text-ink-gray-5 truncate">{{ t.note }}</span>
        </div>
        <Icon name="plus" :size="14" class="text-ink-gray-4" />
      </div>
    </div>
    <div class="px-4 py-3 border-t border-outline-gray-1 mt-auto">
      <div class="flex items-start gap-2">
        <Icon name="info" :size="14" class="text-ink-gray-5 mt-px shrink-0" />
        <span class="text-2xs text-ink-gray-5">
          {{ prefs.devMode
            ? 'Each field becomes a Frappe DocField. Open Developer view to see the schema.'
            : 'Click or drag a field to add it. Drag fields in the form to reorder.' }}
        </span>
      </div>
    </div>
  </aside>
</template>
