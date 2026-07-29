<script setup>
import { computed } from 'vue'

// Renders a lucide icon via frappe-ui's `lucide-*` mask classes (from the
// tailwind lucideIconsPlugin) — no per-icon Vue component, so lucide-vue-next
// is no longer bundled. The class is dynamic, so every name used here must be
// safelisted in tailwind.config.js. Size drives `font-size` because the mask
// class sizes itself as a `1em` square; colour inherits via `currentColor`.
const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
})

const iconClass = computed(() =>
  props.name.startsWith('lucide-') ? props.name : `lucide-${props.name}`,
)
const fontSize = computed(() => `${Number(props.size)}px`)
</script>

<template>
  <span :class="[iconClass, 'inline-block']" :style="{ fontSize }" aria-hidden="true" />
</template>
