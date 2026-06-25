<script setup>
import { computed } from 'vue'
import * as lucide from 'lucide-vue-next'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  strokeWidth: { type: [Number, String], default: 1.75 },
})

// Map kebab-case lucide names ("circle-dot") to the PascalCase component export.
const cmp = computed(() => {
  const pascal = props.name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('')
  return lucide[pascal] || lucide['Square']
})
</script>

<template>
  <component :is="cmp" :size="Number(size)" :stroke-width="Number(strokeWidth)" />
</template>
