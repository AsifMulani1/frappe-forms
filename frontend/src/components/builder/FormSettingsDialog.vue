<script setup>
import { Dialog, FileUploader, FormControl, Switch } from 'frappe-ui'
import Icon from '../Icon.vue'

// Form-level settings, opened from the builder's gear icon. Per-field settings live inline on
// the card (direct manipulation); these form-wide options are touched rarely, so they live in a
// quiet sheet rather than a standing sidebar. Developer/storage options stay in the dev inspector.
const open = defineModel({ default: false })
const props = defineProps({ form: { type: Object, default: null } })
const emit = defineEmits(['update-meta'])

const set = (patch) => emit('update-meta', patch)

const CATEGORIES = ['', 'HR', 'Support', 'Events', 'Feedback', 'Other']
function onCover(file) {
  set({ cover_image: file.file_url })
}
</script>

<template>
  <Dialog v-model="open" :options="{ title: 'Form settings' }">
    <template #body-content>
      <div v-if="form" class="flex flex-col">
        <div class="flex flex-col gap-4 pb-4">
          <FormControl type="textarea" label="Thank-you message" :rows="3"
            placeholder="Shown to respondents after they submit."
            :modelValue="form.thank_you_message" @update:modelValue="set({ thank_you_message: $event })" />
          <FormControl type="text" label="Redirect URL after submit"
            placeholder="https://example.com/thanks"
            description="Optional. If set, respondents go here instead of the thank-you screen."
            :modelValue="form.redirect_url" @update:modelValue="set({ redirect_url: $event })" />
        </div>

        <!-- Cover image -->
        <div class="flex flex-col gap-2 py-4 border-t border-outline-gray-1">
          <span class="text-xs text-ink-gray-5">Cover image</span>
          <div v-if="form.cover_image" class="relative rounded-lg overflow-hidden border border-outline-gray-1 w-full">
            <img :src="form.cover_image" alt="Cover" class="w-full h-[140px] object-cover" />
            <button class="absolute top-2 right-2 w-7 h-7 rounded-full bg-surface-white/90 hover:bg-surface-white flex items-center justify-center text-ink-gray-7 shadow"
                    @click="set({ cover_image: '' })"><Icon name="x" :size="15" /></button>
          </div>
          <FileUploader v-else :fileTypes="['image/*']" @success="onCover">
            <template #default="{ openFileSelector, uploading, progress }">
              <button class="w-full flex flex-col items-center justify-center gap-2 h-[140px] rounded-lg border border-dashed border-outline-gray-2 text-ink-gray-5 hover:border-outline-gray-3 hover:text-ink-gray-7 hover:bg-surface-gray-1 transition-colors"
                      @click="openFileSelector">
                <Icon name="image" :size="20" />
                <span class="text-sm">{{ uploading ? `Uploading ${progress}%` : 'Add a cover image' }}</span>
              </button>
            </template>
          </FileUploader>
        </div>

        <div class="flex flex-col gap-3.5 pt-4 border-t border-outline-gray-1">
          <Switch :modelValue="!!form.collect_email" label="Collect email addresses" @update:modelValue="set({ collect_email: $event ? 1 : 0 })" />
          <Switch :modelValue="!form.allow_multiple" label="One response per user" @update:modelValue="set({ allow_multiple: $event ? 0 : 1 })" />
          <Switch :modelValue="!!form.login_required" label="Login required" @update:modelValue="set({ login_required: $event ? 1 : 0 })" />
          <Switch :modelValue="!!form.is_template" label="Use as template" @update:modelValue="set({ is_template: $event ? 1 : 0 })" />
          <FormControl v-if="form.is_template" type="select" label="Template category"
            :options="CATEGORIES.map((c) => ({ label: c || 'Uncategorized', value: c }))"
            :modelValue="form.category || ''" @update:modelValue="set({ category: $event })" />
        </div>
      </div>
    </template>
  </Dialog>
</template>
