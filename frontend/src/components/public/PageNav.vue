<script setup>
// The card footer: Back / Next / Submit plus the page indicator (multi-page) or Clear (single-page).
import { Button } from 'frappe-ui'
defineProps({
  multiPage: Boolean, currentPage: Number, isLastPage: Boolean,
  submitting: Boolean, editing: Boolean, pageCount: Number,
})
defineEmits(['prev', 'next', 'submit', 'reset'])
</script>

<template>
  <div class="flex items-center justify-between border-t border-outline-gray-1 pt-5 mt-1">
    <div class="flex items-center gap-2">
      <Button v-if="multiPage && currentPage > 0" variant="outline" theme="gray" size="lg" @click="$emit('prev')">Back</Button>
      <Button v-if="!isLastPage" variant="solid" theme="gray" size="lg" @click="$emit('next')">Next</Button>
      <Button v-else variant="solid" theme="gray" size="lg" :loading="submitting" @click="$emit('submit')">{{ editing ? 'Update' : 'Submit' }}</Button>
    </div>
    <span v-if="multiPage" class="text-sm text-ink-gray-5">Page {{ currentPage + 1 }} of {{ pageCount }}</span>
    <button v-else class="text-sm text-ink-gray-5" @click="$emit('reset')">Clear form</button>
  </div>
</template>
