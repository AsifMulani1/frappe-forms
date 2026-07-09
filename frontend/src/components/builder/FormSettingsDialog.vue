<script setup>
import { computed, ref, watch } from 'vue'
import {
  Badge, Button, DateTimePicker, FileUploader, FormControl, Switch, TabButtons, createResource,
  SettingsDialog, SettingsSidebar, SettingsNavGroup, SettingsNavItem,
  SettingsContent, SettingsPanel, SettingsHeader, SettingsBody, SettingsRow,
} from 'frappe-ui'
import Icon from '../Icon.vue'
import { prefs } from '../../data/prefs'

// Form-level settings, opened from the builder's gear icon. Per-field settings live inline on
// the card (direct manipulation); these form-wide options are touched rarely, so they live in a
// modal rather than a standing sidebar. The dev-only "Developer" tab folds in the storage/DocType
// config that used to live in the inspector, so there's one home for form settings in every mode.
//
// Layout is frappe-ui's SettingsDialog: left-nav grouped tabs, one panel each. The settings
// cluster into distinct concerns, so a tab per concern beats one long scroll — people edit
// settings one at a time and jump straight to the group they want.
const open = defineModel({ default: false })
const props = defineProps({ form: { type: Object, default: null } })
const emit = defineEmits(['update-meta', 'open-dev'])

const set = (patch) => emit('update-meta', patch)

// Land on Access each time the dialog opens; reka-ui keeps selection otherwise.
const tab = ref('access')
watch(open, (isOpen) => { if (isOpen) tab.value = 'access' })

// Developer tab: storage mode + linked-DocType mapping. Mirrors the inspector's dev block so the
// two never drift; the resource lazily loads the target DocType's fields to count mappings.
const linked = computed(() => props.form?.storage_mode === 'Linked')
const targetFields = createResource({
  url: 'forms.admin.target_doctype_fields',
  makeParams: () => ({ doctype: props.form.target_doctype }),
})
function refreshTargets() {
  if (linked.value && props.form?.target_doctype) targetFields.fetch()
}
watch(() => props.form?.target_doctype, refreshTargets)
watch(() => props.form?.storage_mode, (m) => { if (m === 'Linked') refreshTargets() })
const mappedCount = computed(() => (props.form?.fields || []).filter((f) => f.mapped_field).length)
function setStorage(mode) {
  set({ storage_mode: mode })
  if (mode === 'Linked' && !props.form.target_doctype) {
    set({ target_doctype: 'Contact' })
    setTimeout(refreshTargets, 50)
  }
}
function openDev() {
  open.value = false
  emit('open-dev')
}

// Nav is data-driven so the sidebar and panels can't drift out of sync.
const NAV = [
  { group: 'Form', items: [
    { value: 'access', label: 'Access', icon: 'lock' },
    { value: 'schedule', label: 'Schedule', icon: 'calendar-clock' },
    { value: 'quiz', label: 'Quiz', icon: 'award' },
    { value: 'experience', label: 'Experience', icon: 'sparkles' },
  ] },
  { group: 'After submit', items: [
    { value: 'notifications', label: 'Notifications', icon: 'bell' },
    { value: 'responses', label: 'Responses', icon: 'inbox' },
    { value: 'sharing', label: 'Sharing', icon: 'share-2' },
  ] },
]

const CATEGORIES = ['', 'HR', 'Support', 'Events', 'Feedback', 'Other']
function onCover(file) {
  set({ cover_image: file.file_url })
}
</script>

<template>
  <SettingsDialog v-if="form" v-model="open" v-model:tab="tab">
    <template #title>Form settings</template>

    <SettingsSidebar>
      <SettingsNavGroup v-for="g in NAV" :key="g.group" :label="g.group">
        <SettingsNavItem v-for="it in g.items" :key="it.value" :value="it.value">
          <template #prefix><Icon :name="it.icon" :size="16" class="text-ink-gray-6" /></template>
          {{ it.label }}
        </SettingsNavItem>
      </SettingsNavGroup>
      <SettingsNavGroup v-if="prefs.devMode" label="Advanced">
        <SettingsNavItem value="developer">
          <template #prefix><Icon name="code-2" :size="16" class="text-ink-gray-6" /></template>
          Developer
        </SettingsNavItem>
      </SettingsNavGroup>
    </SettingsSidebar>

    <SettingsContent>
      <!-- Access -->
      <SettingsPanel value="access">
        <SettingsHeader title="Access" description="Control who can respond and how." />
        <SettingsBody>
          <div class="pt-9 divide-y divide-outline-gray-1">
            <SettingsRow title="Collect email addresses">
              <Switch :modelValue="!!form.collect_email" @update:modelValue="set({ collect_email: $event ? 1 : 0 })" />
            </SettingsRow>
            <SettingsRow title="One response per user"
              description="Enforced by signed-in user, or by collected email for guests.">
              <Switch :modelValue="!form.allow_multiple" @update:modelValue="set({ allow_multiple: $event ? 0 : 1 })" />
            </SettingsRow>
            <SettingsRow title="Login required">
              <Switch :modelValue="!!form.login_required" @update:modelValue="set({ login_required: $event ? 1 : 0 })" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Schedule -->
      <SettingsPanel value="schedule">
        <SettingsHeader title="Schedule" description="Open, close, and cap responses." />
        <SettingsBody>
          <div class="pt-9 flex flex-col gap-7">
            <div class="flex flex-col gap-2">
              <span class="text-sm font-medium text-ink-gray-7">Opens on</span>
              <DateTimePicker :modelValue="form.opens_on" placeholder="Open immediately" @update:modelValue="set({ opens_on: $event })" />
            </div>
            <div class="flex flex-col gap-2">
              <span class="text-sm font-medium text-ink-gray-7">Closes on</span>
              <DateTimePicker :modelValue="form.closes_on" placeholder="No closing date" @update:modelValue="set({ closes_on: $event })" />
            </div>
            <FormControl type="number" label="Response limit"
              description="Stop accepting after this many responses. 0 = unlimited (Collection forms)."
              :modelValue="form.response_limit || ''" @update:modelValue="set({ response_limit: +$event || 0 })" />
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Quiz -->
      <SettingsPanel value="quiz">
        <SettingsHeader title="Quiz" description="Grade responses and show scores." />
        <SettingsBody>
          <div class="pt-9 divide-y divide-outline-gray-1">
            <SettingsRow title="Make this a quiz"
              description="Set points and correct answers per question on each field.">
              <Switch :modelValue="!!form.is_quiz" @update:modelValue="set({ is_quiz: $event ? 1 : 0 })" />
            </SettingsRow>
            <SettingsRow v-if="form.is_quiz" title="Show score after submit">
              <Switch :modelValue="!!form.show_score" @update:modelValue="set({ show_score: $event ? 1 : 0 })" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Experience -->
      <SettingsPanel value="experience">
        <SettingsHeader title="Respondent experience" description="What people see while filling and after submitting." />
        <SettingsBody>
          <div class="pt-9 flex flex-col gap-7">
            <FormControl type="textarea" label="Thank-you message" :rows="3"
              placeholder="Shown to respondents after they submit."
              :modelValue="form.thank_you_message" @update:modelValue="set({ thank_you_message: $event })" />
            <FormControl type="text" label="Redirect URL after submit"
              placeholder="https://example.com/thanks"
              description="Optional. If set, respondents go here instead of the thank-you screen."
              :modelValue="form.redirect_url" @update:modelValue="set({ redirect_url: $event })" />

            <div class="flex flex-col gap-2">
              <span class="text-sm font-medium text-ink-gray-7">Cover image</span>
              <div v-if="form.cover_image" class="relative rounded-lg overflow-hidden border border-outline-gray-1 w-full">
                <img :src="form.cover_image" alt="Cover" class="w-full h-[140px] object-cover" />
                <button class="absolute top-2 right-2 w-7 h-7 rounded-full bg-surface-base/90 hover:bg-surface-base flex items-center justify-center text-ink-gray-7 shadow"
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

            <div class="divide-y divide-outline-gray-1">
              <SettingsRow title="Show progress bar">
                <Switch :modelValue="form.show_progress !== 0" @update:modelValue="set({ show_progress: $event ? 1 : 0 })" />
              </SettingsRow>
              <SettingsRow title="Shuffle question order">
                <Switch :modelValue="!!form.shuffle_questions" @update:modelValue="set({ shuffle_questions: $event ? 1 : 0 })" />
              </SettingsRow>
            </div>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Notifications -->
      <SettingsPanel value="notifications">
        <SettingsHeader title="Notifications" description="Emails sent when responses come in." />
        <SettingsBody>
          <div class="pt-9 divide-y divide-outline-gray-1">
            <SettingsRow title="Email me on new response">
              <Switch :modelValue="!!form.notify_on_response" @update:modelValue="set({ notify_on_response: $event ? 1 : 0 })" />
            </SettingsRow>
            <div v-if="form.notify_on_response" class="py-3.5">
              <FormControl type="text" label="Notification email"
                placeholder="Defaults to the form owner"
                :modelValue="form.notify_email" @update:modelValue="set({ notify_email: $event })" />
            </div>
            <SettingsRow title="Email respondents a receipt">
              <Switch :modelValue="!!form.email_receipt" @update:modelValue="set({ email_receipt: $event ? 1 : 0 })" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Responses -->
      <SettingsPanel value="responses">
        <SettingsHeader title="Responses" description="How respondents manage what they submitted." />
        <SettingsBody>
          <div class="pt-9 divide-y divide-outline-gray-1">
            <SettingsRow title="Allow editing responses">
              <Switch :modelValue="!!form.allow_edit" @update:modelValue="set({ allow_edit: $event ? 1 : 0 })" />
            </SettingsRow>
            <SettingsRow title="Show respondents their submissions">
              <Switch :modelValue="!!form.show_my_submissions" @update:modelValue="set({ show_my_submissions: $event ? 1 : 0 })" />
            </SettingsRow>
            <SettingsRow v-if="form.show_my_submissions" title="Allow deleting responses">
              <Switch :modelValue="!!form.allow_delete" @update:modelValue="set({ allow_delete: $event ? 1 : 0 })" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Sharing -->
      <SettingsPanel value="sharing">
        <SettingsHeader title="Sharing" description="Embed on other sites and reuse as a template." />
        <SettingsBody>
          <div class="pt-9 flex flex-col gap-7">
            <FormControl type="textarea" label="Allowed embedding domains" :rows="3"
              placeholder="https://example.com&#10;https://blog.example.com"
              description="One site per line. The published form can be embedded via iframe only on these domains. Leave empty to disable embedding."
              :modelValue="form.embed_allowed_domains" @update:modelValue="set({ embed_allowed_domains: $event })" />
            <div class="divide-y divide-outline-gray-1">
              <SettingsRow title="Use as template"
                description="Offer this form as a starting point when creating new forms.">
                <Switch :modelValue="!!form.is_template" @update:modelValue="set({ is_template: $event ? 1 : 0 })" />
              </SettingsRow>
            </div>
            <FormControl v-if="form.is_template" type="select" label="Template category"
              :options="CATEGORIES.map((c) => ({ label: c || 'Uncategorized', value: c }))"
              :modelValue="form.category || ''" @update:modelValue="set({ category: $event })" />
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- Developer (dev mode only) -->
      <SettingsPanel v-if="prefs.devMode" value="developer">
        <SettingsHeader title="Developer" description="Where and how submissions are stored.">
          <template #actions>
            <Button variant="subtle" theme="gray" @click="openDev">
              <template #prefix><Icon name="code-2" :size="15" /></template>Developer view
            </Button>
          </template>
        </SettingsHeader>
        <SettingsBody>
          <div class="pt-9 flex flex-col gap-7">
            <div class="flex flex-col gap-2">
              <span class="text-sm font-medium text-ink-gray-7">Where submissions go</span>
              <TabButtons
                :buttons="[{ label: 'New collection', value: 'Collection' }, { label: 'Link existing', value: 'Linked' }]"
                :modelValue="form.storage_mode" @update:modelValue="setStorage($event)" />
              <span class="text-[13px] leading-5 text-ink-gray-5">
                {{ linked ? 'Saved as records of an existing DocType — no schema change on publish.' : 'A dedicated DocType is created for this form on publish.' }}
              </span>
            </div>

            <template v-if="linked">
              <FormControl type="select" label="Target DocType"
                :options="[{ label: 'Contact', value: 'Contact' }, { label: 'ToDo', value: 'ToDo' }]"
                :modelValue="form.target_doctype" @update:modelValue="set({ target_doctype: $event })" />
              <div class="flex flex-col gap-2">
                <Badge :theme="mappedCount < form.fields.length ? 'orange' : 'green'"
                  :label="`${mappedCount}/${form.fields.length} fields mapped`" />
                <span class="text-[13px] leading-5 text-ink-gray-5">Map each field to a target column from the field's inspector panel.</span>
              </div>
              <div class="divide-y divide-outline-gray-1">
                <SettingsRow title="Apply document permissions"
                  :description="form.apply_doc_perms ? 'Submitter must be signed in and permitted to create the target record.' : 'Submissions are inserted as the system (guests allowed).'">
                  <Switch :modelValue="!!form.apply_doc_perms" @update:modelValue="set({ apply_doc_perms: $event ? 1 : 0 })" />
                </SettingsRow>
              </div>
            </template>

            <div v-else class="flex flex-col gap-2">
              <span class="text-sm font-medium text-ink-gray-7">Generated DocType</span>
              <div class="flex items-center gap-2 h-9 px-2.5 rounded bg-surface-gray-2 text-ink-gray-8">
                <Icon name="database" :size="14" class="text-ink-gray-6" />
                <span class="font-mono text-[13px]">{{ form.doctype_name || '— created on publish —' }}</span>
              </div>
            </div>
          </div>
        </SettingsBody>
      </SettingsPanel>
    </SettingsContent>
  </SettingsDialog>
</template>
