<script setup>
import { Button } from 'frappe-ui'
// The signed-in respondent's own past submissions, with edit/delete affordances. Presentational;
// the parent owns the data and performs the delete.
defineProps({ subs: Array, meta: Object, slug: String })
defineEmits(['delete'])

function fmtDate(dt) {
  if (!dt) return ''
  try { return new Date(dt.replace(' ', 'T')).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) } catch { return dt }
}
</script>

<template>
  <div v-if="subs.length" class="public-card p-4 mb-4 sm:p-5">
    <div class="flex items-center justify-between mb-1.5">
      <span class="text-sm font-medium text-ink-gray-9">Your responses</span>
      <span class="text-xs text-ink-gray-5">{{ subs.length }}</span>
    </div>
    <div class="flex flex-col divide-y divide-outline-gray-1">
      <div v-for="s in subs" :key="s.name" class="flex items-center gap-3 py-2.5">
        <div class="flex flex-col min-w-0 flex-1">
          <span class="text-sm text-ink-gray-8 truncate">{{ s.label }}</span>
          <span class="text-[11px] text-ink-gray-5">{{ fmtDate(s.creation) }}</span>
        </div>
        <a v-if="s.edit_param && meta.can_edit" :href="`/forms/f/${slug}?${s.edit_param}`"
           class="text-sm text-ink-gray-7 hover:text-ink-gray-9">Edit</a>
        <Button v-if="meta.can_delete" variant="ghost" theme="red" size="sm" label="Delete" @click="$emit('delete', s.name)" />
      </div>
    </div>
  </div>
</template>
