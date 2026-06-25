<script setup>
import { computed, reactive, ref } from 'vue'
import { Button, DatePicker, FormControl, TimePicker, toast } from 'frappe-ui'
import { call } from '../data/call'
import Icon from '../components/Icon.vue'
import SignaturePad from '../components/SignaturePad.vue'

const props = defineProps({ slug: String })

const form = ref(null)
const notFound = ref(false)
const answers = reactive({})
const errors = reactive({})
const submitting = ref(false)
const done = ref(null)
const redirecting = ref(false)
const hp = ref('') // honeypot
const uploading = reactive({})
const fileNames = reactive({})

async function load() {
  try {
    form.value = await call('forms.api.get_public_form', { slug: props.slug })
    // Count this open for the completion funnel (fire-and-forget).
    call('forms.api.track_view', { slug: props.slug }).catch(() => {})
  } catch (e) {
    notFound.value = true
  }
}
load()

// Section headers carry no answer - exclude them from the progress count.
const questions = computed(() => (form.value?.fields || []).filter((f) => f.field_type !== 'section_header'))
const total = computed(() => questions.value.length)
const answered = computed(() =>
  questions.value.filter((f) => {
    const v = answers[f.fieldname]
    return Array.isArray(v) ? v.length : v !== undefined && v !== '' && v !== null
  }).length,
)
const pct = computed(() => (total.value ? Math.round((answered.value / total.value) * 100) : 0))

function setVal(fn, v) {
  answers[fn] = v
  errors[fn] = false
}

async function uploadFile(f, e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading[f.fieldname] = true
  errors[f.fieldname] = false
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('slug', props.slug)
    fd.append('fieldname', f.fieldname)
    const headers = {}
    if (window.csrf_token && window.csrf_token !== '{{ csrf_token }}') headers['X-Frappe-CSRF-Token'] = window.csrf_token
    const res = await fetch('/api/method/forms.api.upload_submission_file', { method: 'POST', headers, body: fd })
    const json = await res.json()
    if (!res.ok) throw new Error(json?.message || 'Upload failed')
    answers[f.fieldname] = json.message.file_url
    fileNames[f.fieldname] = json.message.file_name
  } catch (err) {
    toast.error('Upload failed — check the file size (max 10 MB) and type.')
  } finally {
    uploading[f.fieldname] = false
    e.target.value = ''
  }
}
function clearFile(f) {
  delete answers[f.fieldname]
  delete fileNames[f.fieldname]
}
function toggleCb(fn, opt) {
  const arr = Array.isArray(answers[fn]) ? [...answers[fn]] : []
  const i = arr.indexOf(opt)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(opt)
  setVal(fn, arr)
}

async function submit() {
  let bad = false
  for (const f of form.value.fields) {
    if (!f.reqd) continue
    const v = answers[f.fieldname]
    if (Array.isArray(v) ? !v.length : v === undefined || v === '') {
      errors[f.fieldname] = true
      bad = true
    }
  }
  if (bad) return
  submitting.value = true
  try {
    const res = await call('forms.api.submit', {
      slug: props.slug,
      data: JSON.stringify(answers),
      hp: hp.value,
    })
    // Redirect to the configured URL if set (overrides the thank-you screen).
    const url = (form.value.redirect_url || '').trim()
    if (url && /^(https?:\/\/|\/)/.test(url)) {
      done.value = res.name
      redirecting.value = true
      setTimeout(() => { window.location.href = url }, 900)
      return
    }
    done.value = res.name
  } catch (e) {
    toast.error(e.messages?.[0] || 'Submission failed. Please check your answers.')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="min-h-full overflow-auto bg-surface-gray-1" :data-accent="form?.accent || 'blue'">
    <div v-if="notFound" class="flex flex-col items-center justify-center h-screen text-center px-6">
      <Icon name="file-question" :size="34" class="text-ink-gray-4" />
      <h1 class="text-xl text-ink-gray-9 mt-3">Form not available</h1>
      <p class="text-sm text-ink-gray-5 mt-1">This form doesn’t exist or isn’t published yet.</p>
    </div>

    <template v-else-if="form">
      <!-- progress -->
      <div class="h-[3px] bg-surface-gray-2 sticky top-0 z-10">
        <div class="h-full transition-all" :style="{ width: `${done ? 100 : pct}%`, background: 'var(--accent)' }" />
      </div>

      <div class="max-w-[600px] mx-auto px-5 pt-8 pb-16">
        <template v-if="!done">
          <img v-if="form.cover_image" :src="form.cover_image" alt="" class="w-full h-[180px] object-cover rounded-xl mb-6" />
          <div class="mb-7">
            <h1 class="text-2xl font-semibold text-ink-gray-9 tracking-tight">{{ form.title }}</h1>
            <p v-if="form.description" class="text-base text-ink-gray-6 mt-2">{{ form.description }}</p>
            <div class="flex items-center gap-1.5 mt-3.5">
              <span class="text-ink-red-500 text-sm">*</span><span class="text-sm text-ink-gray-5">Indicates a required question</span>
            </div>
          </div>

          <div class="public-card p-7">
            <!-- honeypot -->
            <input v-model="hp" type="text" tabindex="-1" autocomplete="off"
                   class="absolute opacity-0 pointer-events-none -z-10 h-0 w-0" aria-hidden="true" />

            <template v-for="f in form.fields" :key="f.fieldname">
            <!-- display-only section header -->
            <div v-if="f.field_type === 'section_header'" class="mb-6 pt-5 mt-1 border-t border-outline-gray-1 first:border-0 first:pt-0 first:mt-0">
              <h2 class="text-lg font-semibold text-ink-gray-9">{{ f.label }}</h2>
              <p v-if="f.help_text" class="text-sm text-ink-gray-5 mt-1">{{ f.help_text }}</p>
            </div>

            <div v-else class="flex flex-col gap-2 mb-6">
              <div class="flex flex-col gap-0.5">
                <span class="text-[15px] font-medium text-ink-gray-9">
                  {{ f.label }}<span v-if="f.reqd" class="text-ink-red-500 ml-0.5">*</span>
                </span>
                <span v-if="f.help_text" class="text-sm text-ink-gray-5">{{ f.help_text }}</span>
              </div>

              <FormControl v-if="f.field_type === 'short_answer'" type="text" size="lg" placeholder="Your answer"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'email'" type="email" size="lg" placeholder="name@example.com"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'number'" type="number" size="lg" placeholder="0"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'phone'" type="tel" size="lg" placeholder="+1 (555) 000-0000"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <div v-else-if="f.field_type === 'time'" class="r-picker">
                <TimePicker placeholder="Select time"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              </div>
              <FormControl v-else-if="f.field_type === 'paragraph'" type="textarea" size="lg" :rows="4" placeholder="Your answer"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <FormControl v-else-if="f.field_type === 'address'" type="textarea" size="lg" :rows="3" placeholder="Street, city, state, ZIP"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              <div v-else-if="f.field_type === 'date'" class="r-picker">
                <DatePicker placeholder="Select date"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />
              </div>
              <FormControl v-else-if="f.field_type === 'dropdown'" type="select" size="lg"
                     :options="[{ label: 'Choose an option', value: '' }, ...f.options.map((o) => ({ label: o, value: o }))]"
                     :modelValue="answers[f.fieldname] || ''" @update:modelValue="setVal(f.fieldname, $event)" />

              <!-- file upload -->
              <label v-else-if="f.field_type === 'file_upload'"
                     class="flex items-center gap-2.5 h-10 px-3 rounded-md bg-surface-gray-2 hover:bg-surface-gray-3 transition-colors cursor-pointer">
                <input type="file" class="hidden" @change="uploadFile(f, $event)" />
                <Icon :name="answers[f.fieldname] ? 'file-check-2' : 'paperclip'" :size="16" class="text-ink-gray-6 shrink-0" />
                <span class="text-base text-ink-gray-8 truncate flex-1">
                  {{ uploading[f.fieldname] ? 'Uploading…' : (fileNames[f.fieldname] || 'Choose a file') }}
                </span>
                <button v-if="answers[f.fieldname]" type="button" class="text-ink-gray-4 hover:text-ink-gray-7 shrink-0" @click.prevent.stop="clearFile(f)"><Icon name="x" :size="15" /></button>
              </label>

              <!-- signature -->
              <SignaturePad v-else-if="f.field_type === 'signature'"
                     :modelValue="answers[f.fieldname]" @update:modelValue="setVal(f.fieldname, $event)" />

              <div v-else-if="f.field_type === 'rating'" class="flex gap-1">
                <span v-for="s in 5" :key="s" class="star" :class="{ on: s <= (answers[f.fieldname] || 0) }" @click="setVal(f.fieldname, s)">
                  <Icon name="star" :size="28" :style="{ fill: s <= (answers[f.fieldname] || 0) ? 'var(--amber-500)' : 'none' }" />
                </span>
              </div>

              <div v-else-if="f.field_type === 'yes_no'" class="flex gap-2">
                <div v-for="o in ['Yes', 'No']" :key="o" class="r-choice min-w-[92px] flex-none"
                     :class="{ sel: answers[f.fieldname] === o }" @click="setVal(f.fieldname, o)">
                  <span class="r-radio"><span v-if="answers[f.fieldname] === o" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
                  <span class="text-base text-ink-gray-8">{{ o }}</span>
                </div>
              </div>

              <div v-else-if="f.field_type === 'single_choice'" class="flex flex-col gap-2">
                <div v-for="o in f.options" :key="o" class="r-choice" :class="{ sel: answers[f.fieldname] === o }" @click="setVal(f.fieldname, o)">
                  <span class="r-radio"><span v-if="answers[f.fieldname] === o" style="width:9px;height:9px;border-radius:50%;background:var(--accent)" /></span>
                  <span class="text-base text-ink-gray-8">{{ o }}</span>
                </div>
              </div>

              <div v-else-if="f.field_type === 'checkboxes'" class="flex flex-col gap-2">
                <div v-for="o in f.options" :key="o" class="r-choice"
                     :class="{ sel: (answers[f.fieldname] || []).includes(o) }" @click="toggleCb(f.fieldname, o)">
                  <span class="r-cb"><Icon v-if="(answers[f.fieldname] || []).includes(o)" name="check" :size="12" /></span>
                  <span class="text-base text-ink-gray-8">{{ o }}</span>
                </div>
              </div>

              <span v-if="errors[f.fieldname]" class="text-xs text-ink-red-500 flex items-center gap-1">
                <Icon name="circle-alert" :size="12" />This field is required.
              </span>
            </div>
            </template>

            <div class="flex items-center justify-between border-t border-outline-gray-1 pt-5 mt-1">
              <Button variant="solid" theme="gray" size="lg" :loading="submitting" @click="submit">Submit</Button>
              <button class="text-sm text-ink-gray-5" @click="Object.keys(answers).forEach((k) => delete answers[k])">Clear form</button>
            </div>
          </div>

          <div class="flex items-center justify-between mt-4.5 px-1 mt-4">
            <span class="text-xs text-ink-gray-5 font-medium">Frappe Forms</span>
            <span class="text-xs text-ink-gray-4">Never submit passwords through Frappe Forms.</span>
          </div>
        </template>

        <!-- success -->
        <div v-else class="public-card text-center px-8 py-12">
          <span class="w-[52px] h-[52px] rounded-[14px] bg-surface-green-2 flex items-center justify-center mx-auto text-green-600">
            <Icon name="check" :size="26" />
          </span>
          <h2 class="text-xl font-semibold text-ink-gray-9 mt-4">Response received</h2>
          <p v-if="redirecting" class="text-base text-ink-gray-6 mt-2 flex items-center justify-center gap-2">
            <Icon name="loader" :size="16" class="animate-spin" />Redirecting you now…
          </p>
          <p v-else class="text-base text-ink-gray-6 mt-2 max-w-[420px] mx-auto">
            {{ form.thank_you_message || 'Thanks! Your response has been recorded.' }}
          </p>
          <p class="text-xs text-ink-gray-5 mt-3">Saved as record <span class="font-mono text-ink-gray-7">{{ done }}</span></p>
          <Button v-if="!redirecting" variant="outline" theme="gray" class="mt-6" @click="done = null; Object.keys(answers).forEach((k) => delete answers[k])">
            Submit another response
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
