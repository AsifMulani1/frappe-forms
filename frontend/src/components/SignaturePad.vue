<script setup>
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'

// Minimal pointer-drawn signature pad. Emits a PNG data-URL (stored in Frappe's Signature field).
const emit = defineEmits(['update:modelValue'])
const canvas = ref(null)
let ctx
let drawing = false
let last = null
let dirty = false

function pos(e) {
  const r = canvas.value.getBoundingClientRect()
  return { x: e.clientX - r.left, y: e.clientY - r.top }
}
function start(e) {
  drawing = true
  last = pos(e)
  canvas.value.setPointerCapture?.(e.pointerId)
}
function move(e) {
  if (!drawing) return
  const p = pos(e)
  ctx.beginPath()
  ctx.moveTo(last.x, last.y)
  ctx.lineTo(p.x, p.y)
  ctx.stroke()
  last = p
  dirty = true
}
function end() {
  if (!drawing) return
  drawing = false
  if (dirty) emit('update:modelValue', canvas.value.toDataURL('image/png'))
}
function clear() {
  ctx.clearRect(0, 0, canvas.value.width, canvas.value.height)
  dirty = false
  emit('update:modelValue', '')
}

onMounted(() => {
  const c = canvas.value
  const ratio = window.devicePixelRatio || 1
  c.width = c.clientWidth * ratio
  c.height = c.clientHeight * ratio
  ctx = c.getContext('2d')
  ctx.scale(ratio, ratio)
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  // Canvas needs a concrete color, so resolve the frappe-ui ink token at runtime.
  ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--ink-gray-9').trim() || '#171717'
})
</script>

<template>
  <div class="flex flex-col gap-2">
    <canvas ref="canvas"
            class="w-full h-[150px] rounded-md bg-surface-gray-2 touch-none cursor-crosshair"
            @pointerdown="start" @pointermove="move" @pointerup="end" @pointerleave="end" />
    <Button variant="ghost" theme="gray" size="sm" label="Clear" class="self-start" @click="clear" />
  </div>
</template>
