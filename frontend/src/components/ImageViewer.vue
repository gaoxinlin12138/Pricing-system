<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

const props = defineProps<{ src: string; title?: string; subtitle?: string }>()
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
  <div class="viewer-mask" role="dialog" aria-modal="true" :aria-label="props.title || '图片预览'" @click.self="emit('close')">
    <figure class="viewer">
      <img :src="props.src" :alt="props.title || '图片预览'" />
      <figcaption>
        <div>
          <b>{{ props.title || '图片预览' }}</b>
          <small v-if="props.subtitle">{{ props.subtitle }}</small>
        </div>
        <button type="button" class="btn btn-sm" @click="emit('close')">关闭</button>
      </figcaption>
    </figure>
  </div>
</template>
