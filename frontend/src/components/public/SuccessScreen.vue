<script setup>
// The post-submit confirmation: acknowledgement, optional quiz score, thank-you / redirect notice,
// the edit-later link, and "Submit another". Presentational; the parent owns the actions.
import { Button } from 'frappe-ui'
import Icon from '../Icon.vue'
defineProps({
  form: Object, editing: Boolean, submitResult: Object,
  redirecting: Boolean, editUrl: String,
})
defineEmits(['copy', 'another'])
</script>

<template>
  <div class="public-card text-center px-5 py-12 sm:px-8">
    <span class="w-[52px] h-[52px] rounded-[14px] bg-surface-green-2 flex items-center justify-center mx-auto text-green-600">
      <Icon name="check" :size="26" />
    </span>
    <h2 class="text-xl font-semibold text-ink-gray-9 mt-4">{{ editing ? 'Response updated' : 'Response received' }}</h2>

    <!-- quiz score -->
    <div v-if="submitResult && submitResult.show_score && submitResult.max_score" class="mt-4 mx-auto inline-flex flex-col items-center rounded-xl bg-surface-gray-1 px-6 py-4">
      <span class="text-xs text-ink-gray-5">Your score</span>
      <span class="text-2xl font-semibold text-ink-gray-9 mt-1">{{ +submitResult.score.toFixed(2) }} / {{ +submitResult.max_score.toFixed(2) }}</span>
    </div>

    <p v-if="redirecting" class="text-base text-ink-gray-6 mt-2 flex items-center justify-center gap-2">
      <Icon name="loader" :size="16" class="animate-spin" />Redirecting you now…
    </p>
    <p v-else class="text-base text-ink-gray-6 mt-2 max-w-[420px] mx-auto">
      {{ form.thank_you_message || 'Thanks! Your response has been recorded.' }}
    </p>

    <div v-if="form.allow_edit && editUrl && !redirecting" class="mt-5 mx-auto max-w-[440px] text-left bg-surface-gray-1 rounded-lg p-3.5">
      <div class="flex items-center gap-1.5 text-sm text-ink-gray-7 mb-2"><Icon name="pencil" :size="13" />Edit your response later</div>
      <div class="flex items-center gap-2">
        <input readonly class="cfg-input flex-1 text-xs" :value="editUrl" @focus="$event.target.select()" />
        <Button variant="subtle" theme="gray" @click="$emit('copy')">Copy</Button>
      </div>
    </div>

    <Button v-if="!redirecting && !editing" variant="outline" theme="gray" class="mt-6" @click="$emit('another')">
      Submit another response
    </Button>
  </div>
</template>
