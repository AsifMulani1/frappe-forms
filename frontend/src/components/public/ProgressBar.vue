<script setup>
// Thin sticky progress bar at the top of the respondent view. Presentational only.
defineProps({ show: Boolean, pct: Number, done: Boolean })
</script>

<template>
  <div v-if="show" class="h-[3px] bg-surface-gray-2 sticky top-0 z-10">
    <div class="h-full transition-all" :style="{ width: `${done ? 100 : pct}%`, background: 'var(--accent)' }" />
  </div>
</template>
