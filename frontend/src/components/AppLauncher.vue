<script setup>
import { Dialog } from 'frappe-ui'
import Icon from './Icon.vue'

defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])

// The Frappe workspace suite - app-launcher chrome (Forms is the active product).
const SUITE = [
  { id: 'docs', name: 'Docs', icon: 'file-text', color: 'var(--blue-500)' },
  { id: 'sheets', name: 'Sheets', icon: 'table-2', color: 'var(--green-600)' },
  { id: 'slides', name: 'Slides', icon: 'presentation', color: 'var(--orange-500)' },
  { id: 'mail', name: 'Mail', icon: 'mail', color: 'var(--red-500)' },
  { id: 'calendar', name: 'Calendar', icon: 'calendar', color: 'var(--violet-500)' },
  { id: 'meet', name: 'Meet', icon: 'video', color: 'var(--teal-600)' },
  { id: 'drive', name: 'Drive', icon: 'hard-drive', color: 'var(--cyan-600)' },
  { id: 'gameplan', name: 'Gameplan', icon: 'messages-square', color: 'var(--pink-600)' },
  { id: 'forms', name: 'Forms', icon: 'clipboard-list', color: 'var(--blue-500)', current: true },
]
</script>

<template>
  <Dialog
    :modelValue="modelValue"
    @update:modelValue="$emit('update:modelValue', $event)"
    :options="{ title: 'Frappe workspace' }"
  >
    <template #body-content>
      <p class="text-sm text-ink-gray-5 -mt-2 mb-4">Acme Inc · 9 apps</p>
      <div class="grid grid-cols-3 gap-1">
        <div v-for="a in SUITE" :key="a.id" class="app-tile" :style="{ cursor: a.current ? 'pointer' : 'default' }">
          <span class="glyph" :style="{ background: a.color }"><Icon :name="a.icon" :size="22" /></span>
          <span class="text-[12.5px] text-ink-gray-8">{{ a.name }}</span>
          <span v-if="a.current" class="text-[11px] ink-accent -mt-0.5">Open</span>
        </div>
      </div>
    </template>
  </Dialog>
</template>
