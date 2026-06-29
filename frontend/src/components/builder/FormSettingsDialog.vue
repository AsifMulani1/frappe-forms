<script setup>
import { ref, watch } from 'vue'
import { Dialog, FileUploader, FormControl, Switch } from 'frappe-ui'
import Icon from '../Icon.vue'

// Form-level settings, opened from the builder's gear icon. Per-field settings live inline on
// the card (direct manipulation); these form-wide options are touched rarely, so they live in a
// quiet sheet rather than a standing sidebar. Developer/storage options stay in the dev inspector.
//
// Layout follows progressive disclosure: the handful of settings most forms change are grouped
// under quiet section headers; the rarely-touched long tail stays collapsed behind "Advanced".
const open = defineModel({ default: false })
const props = defineProps({ form: { type: Object, default: null } })
const emit = defineEmits(['update-meta'])

const set = (patch) => emit('update-meta', patch)

const showAdvanced = ref(false)

// Auto-expand Advanced when any of its settings is already active, so an enabled option is
// never hidden behind a collapsed section.
watch(open, (isOpen) => {
  if (!isOpen || !props.form) return
  const f = props.form
  showAdvanced.value = !!(f.shuffle_questions || f.email_receipt || f.allow_edit
    || f.show_my_submissions || f.allow_delete || f.is_template)
})

const CATEGORIES = ['', 'HR', 'Support', 'Events', 'Feedback', 'Other']
function onCover(file) {
  set({ cover_image: file.file_url })
}
</script>

<template>
  <Dialog v-model="open" :options="{ title: 'Form settings' }">
    <template #body-content>
      <div v-if="form" class="flex flex-col gap-6">
        <!-- Who can respond -->
        <section class="flex flex-col gap-3.5">
          <span class="text-xs text-ink-gray-5">Who can respond</span>
          <Switch :modelValue="!!form.collect_email" label="Collect email addresses" @update:modelValue="set({ collect_email: $event ? 1 : 0 })" />
          <Switch :modelValue="!form.allow_multiple" label="One response per user" @update:modelValue="set({ allow_multiple: $event ? 0 : 1 })" />
          <Switch :modelValue="!!form.login_required" label="Login required" @update:modelValue="set({ login_required: $event ? 1 : 0 })" />
        </section>

        <!-- Respondent experience -->
        <section class="flex flex-col gap-4">
          <span class="text-xs text-ink-gray-5">Respondent experience</span>
          <FormControl type="textarea" label="Thank-you message" :rows="3"
            placeholder="Shown to respondents after they submit."
            :modelValue="form.thank_you_message" @update:modelValue="set({ thank_you_message: $event })" />
          <FormControl type="text" label="Redirect URL after submit"
            placeholder="https://example.com/thanks"
            description="Optional. If set, respondents go here instead of the thank-you screen."
            :modelValue="form.redirect_url" @update:modelValue="set({ redirect_url: $event })" />

          <div class="flex flex-col gap-2">
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

          <Switch :modelValue="form.show_progress !== 0" label="Show progress bar" @update:modelValue="set({ show_progress: $event ? 1 : 0 })" />
        </section>

        <!-- Advanced (collapsed by default) -->
        <section class="flex flex-col gap-3.5 pt-2 border-t border-outline-gray-1">
          <button class="flex items-center gap-1.5 -mb-1 text-xs text-ink-gray-5 hover:text-ink-gray-7 transition-colors"
                  @click="showAdvanced = !showAdvanced">
            <Icon :name="showAdvanced ? 'chevron-down' : 'chevron-right'" :size="14" />
            Advanced
          </button>
          <template v-if="showAdvanced">
            <Switch :modelValue="!!form.shuffle_questions" label="Shuffle question order" @update:modelValue="set({ shuffle_questions: $event ? 1 : 0 })" />
            <Switch :modelValue="!!form.email_receipt" label="Email respondents a receipt" @update:modelValue="set({ email_receipt: $event ? 1 : 0 })" />
            <Switch :modelValue="!!form.allow_edit" label="Allow editing responses" @update:modelValue="set({ allow_edit: $event ? 1 : 0 })" />
            <Switch :modelValue="!!form.show_my_submissions" label="Show respondents their submissions" @update:modelValue="set({ show_my_submissions: $event ? 1 : 0 })" />
            <Switch v-if="form.show_my_submissions" :modelValue="!!form.allow_delete" label="Allow deleting responses" @update:modelValue="set({ allow_delete: $event ? 1 : 0 })" />
            <Switch :modelValue="!!form.is_template" label="Use as template" @update:modelValue="set({ is_template: $event ? 1 : 0 })" />
            <FormControl v-if="form.is_template" type="select" label="Template category"
              :options="CATEGORIES.map((c) => ({ label: c || 'Uncategorized', value: c }))"
              :modelValue="form.category || ''" @update:modelValue="set({ category: $event })" />
          </template>
        </section>
      </div>
    </template>
  </Dialog>
</template>
