<script setup>
import { computed, ref, watch } from 'vue'
import QRCode from 'qrcode'
import { Autocomplete, Avatar, Button, Dialog, Dropdown, createResource, toast } from 'frappe-ui'
import { call } from '../data/call'
import { session } from '../data/session'
import Icon from './Icon.vue'

// Frappe Drive-style share dialog: add people, list people with access, general access.
const open = defineModel({ default: false })
const props = defineProps({ form: { type: Object, default: null } })
const emit = defineEmits(['changed'])

const publicUrl = computed(() => `${location.origin}/forms/f/${props.form?.slug}`)
const embedCode = computed(
  () => `<iframe src="${publicUrl.value}" width="100%" height="600" frameborder="0" style="border:0"></iframe>`,
)
// Embedding only works on domains the owner allow-lists in Form settings; without them the
// browser refuses to frame the form, so we don't hand out a snippet that would render blank.
const embedEnabled = computed(() => !!(props.form?.embed_allowed_domains || '').trim())
const qr = ref('')
const showQr = ref(false)
watch(
  () => [open.value, props.form?.slug, props.form?.status],
  () => {
    showQr.value = false
    if (open.value && props.form?.status === 'Published') {
      QRCode.toDataURL(publicUrl.value, { width: 240, margin: 1 }).then((d) => (qr.value = d)).catch(() => (qr.value = ''))
    }
  },
  { immediate: true },
)

const pickUser = ref(null)
const pickAccess = ref('edit')
const sharing = ref(false)
const users = createResource({ url: 'forms.admin.list_users' })
const shares = createResource({ url: 'forms.admin.list_shares', makeParams: () => ({ name: props.form?.name }) })

watch(open, (isOpen) => {
  if (!isOpen || !props.form) return
  pickUser.value = null
  pickAccess.value = 'edit'
  if (!users.data) users.fetch()
  shares.reload()
})

// Users not already on the access list (and not the owner).
const userOptions = computed(() => {
  const taken = new Set([...(shares.data || []).map((s) => s.user), props.form?.owner].filter(Boolean))
  return (users.data || [])
    .filter((u) => !taken.has(u.name))
    .map((u) => ({ label: u.full_name || u.name, value: u.name, description: u.name }))
})

async function addPerson() {
  if (!pickUser.value?.value) return
  sharing.value = true
  try {
    await call('forms.admin.share_form', { name: props.form.name, user: pickUser.value.value, write: pickAccess.value === 'edit' ? 1 : 0 })
    pickUser.value = null
    shares.reload()
    emit('changed')
  } finally {
    sharing.value = false
  }
}
async function setAccess(s, write) {
  await call('forms.admin.share_form', { name: props.form.name, user: s.user, write })
  shares.reload()
}
async function removeAccess(s) {
  await call('forms.admin.unshare_form', { name: props.form.name, user: s.user })
  toast.success(`Removed ${s.full_name || s.user}`)
  shares.reload()
  emit('changed')
}
function accessMenu(s) {
  return [
    { label: 'Can edit', icon: s.write ? 'check' : '', onClick: () => setAccess(s, 1) },
    { label: 'Can view', icon: !s.write ? 'check' : '', onClick: () => setAccess(s, 0) },
    { label: 'Remove access', icon: 'trash-2', onClick: () => removeAccess(s) },
  ]
}
function copyLink() {
  navigator.clipboard?.writeText(publicUrl.value)
  toast.success('Link copied')
}
function copyEmbed() {
  navigator.clipboard?.writeText(embedCode.value)
  toast.success('Embed code copied')
}
</script>

<template>
  <Dialog v-model="open" :options="{ title: form ? `Share “${form.title}”` : 'Share' }">
    <template #body-content>
      <!-- add people -->
      <div class="flex items-center gap-2">
        <div class="flex-1 min-w-0 ac-white">
          <Autocomplete :options="userOptions" v-model="pickUser" placeholder="Add people by name or email" />
        </div>
        <Dropdown :options="[
          { label: 'Can edit', onClick: () => (pickAccess = 'edit') },
          { label: 'Can view', onClick: () => (pickAccess = 'view') },
        ]">
          <Button variant="outline" theme="gray">
            {{ pickAccess === 'edit' ? 'Can edit' : 'Can view' }}
            <template #suffix><Icon name="chevron-down" :size="14" /></template>
          </Button>
        </Dropdown>
        <Button variant="solid" theme="gray" :loading="sharing" :disabled="!pickUser" @click="addPerson">Add</Button>
      </div>

      <!-- people with access -->
      <div class="mt-6">
        <p class="text-xs text-ink-gray-5 mb-1">People with access</p>
        <div class="flex flex-col">
          <!-- owner -->
          <div class="flex items-center gap-3 py-2.5">
            <Avatar :label="form?.owner_fullname" size="xl" />
            <div class="flex flex-col flex-1 min-w-0">
              <span class="text-base text-ink-gray-9 truncate">
                {{ form?.owner_fullname }}<span v-if="form?.owner === session.user" class="text-ink-gray-5"> (you)</span>
              </span>
              <span class="text-xs text-ink-gray-5 truncate">{{ form?.owner }}</span>
            </div>
            <span class="text-sm text-ink-gray-5 shrink-0 pr-2">Owner</span>
          </div>
          <!-- shared users -->
          <div v-for="s in (shares.data || [])" :key="s.user" class="flex items-center gap-3 py-2.5">
            <Avatar :label="s.full_name" size="xl" />
            <div class="flex flex-col flex-1 min-w-0">
              <span class="text-base text-ink-gray-9 truncate">{{ s.full_name }}</span>
              <span class="text-xs text-ink-gray-5 truncate">{{ s.user }}</span>
            </div>
            <Dropdown :options="accessMenu(s)">
              <Button variant="ghost" theme="gray" class="shrink-0">
                {{ s.write ? 'Can edit' : 'Can view' }}
                <template #suffix><Icon name="chevron-down" :size="14" /></template>
              </Button>
            </Dropdown>
          </div>
        </div>
      </div>

      <!-- general access -->
      <div class="mt-5 pt-5 border-t border-outline-gray-1">
        <p class="text-xs text-ink-gray-5 mb-2">General access</p>
        <div class="flex items-center gap-3">
          <span class="w-9 h-9 rounded-full bg-surface-gray-2 flex items-center justify-center text-ink-gray-7 shrink-0">
            <Icon :name="form?.status === 'Published' ? 'globe' : 'lock'" :size="17" />
          </span>
          <div class="flex flex-col flex-1 min-w-0">
            <span class="text-base text-ink-gray-9">{{ form?.status === 'Published' ? 'Anyone with the link' : 'Restricted' }}</span>
            <span class="text-xs text-ink-gray-5">
              {{ form?.status === 'Published'
                ? 'Anyone with the link can respond to this form.'
                : 'Only the owner and people added above can open this form.' }}
            </span>
          </div>
          <Button v-if="form?.status === 'Published'" variant="subtle" theme="gray" class="shrink-0" @click="copyLink">
            <template #prefix><Icon name="link" :size="14" /></template>
            Copy link
          </Button>
        </div>

        <!-- embed + QR (published only) -->
        <div v-if="form?.status === 'Published'" class="mt-4 flex flex-col gap-3">
          <div v-if="embedEnabled" class="flex items-center gap-2">
            <code class="flex-1 min-w-0 truncate text-xs text-ink-gray-6 bg-surface-gray-2 rounded-md px-2.5 py-2 font-mono">{{ embedCode }}</code>
            <Button variant="subtle" theme="gray" class="shrink-0" @click="copyEmbed">
              <template #prefix><Icon name="code-2" :size="14" /></template>Copy embed
            </Button>
          </div>
          <p v-else class="text-xs text-ink-gray-5">
            To embed this form on another site, add that site under
            <span class="text-ink-gray-7">Form settings → Embedding</span>.
          </p>
          <div>
            <button class="flex items-center gap-1.5 text-sm text-ink-gray-6 hover:text-ink-gray-9" @click="showQr = !showQr">
              <Icon :name="showQr ? 'chevron-down' : 'chevron-right'" :size="15" />QR code
            </button>
            <div v-if="showQr && qr" class="flex flex-col items-center gap-2 mt-3">
              <img :src="qr" alt="QR code" class="w-[180px] h-[180px] rounded-lg border border-outline-gray-1" />
              <a :href="qr" download="form-qr.png" class="text-sm text-ink-gray-6 hover:text-ink-gray-9 flex items-center gap-1">
                <Icon name="download" :size="14" />Download QR
              </a>
            </div>
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>
