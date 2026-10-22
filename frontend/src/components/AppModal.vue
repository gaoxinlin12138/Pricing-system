<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

defineProps<{
  title: string
  subtitle?: string
  wide?: boolean
}>()

const emit = defineEmits<{ (event: 'close'): void }>()

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.body.style.overflow = 'hidden'
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
      <div class="modal-head">
        <div>
          <h3 class="modal-title">{{ title }}</h3>
          <p v-if="subtitle" class="modal-sub">{{ subtitle }}</p>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="关闭" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <slot />
      </div>
      <div v-if="$slots.footer" class="modal-foot">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
