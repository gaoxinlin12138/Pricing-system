<script setup lang="ts">
import { ref } from 'vue'
import { imageSrc, uploadImage } from '../../api'
import { toast } from '../../ui/toast'

const props = defineProps<{ modelValue: string; label?: string }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()

const ALLOWED = ['image/jpeg', 'image/png', 'image/webp']
const MAX_SIZE = 5 * 1024 * 1024

const input = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const dragging = ref(false)

function validate(file: File): string {
  if (!ALLOWED.includes(file.type)) return '只支持 JPG、PNG 或 WebP 图片'
  if (file.size > MAX_SIZE) return `图片不能超过 5MB（当前 ${(file.size / 1024 / 1024).toFixed(1)}MB）`
  return ''
}

async function upload(file: File) {
  const problem = validate(file)
  if (problem) {
    toast(problem, 'err')
    return
  }
  busy.value = true
  try {
    emit('update:modelValue', await uploadImage(file))
    toast('图片已上传', 'ok')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}

async function onPick(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) await upload(file)
  if (input.value) input.value.value = ''
}

async function onDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) await upload(file)
}

function clear() {
  emit('update:modelValue', '')
}
</script>

<template>
  <div class="field">
    <span>{{ props.label || '图片' }} <small>JPG / PNG / WebP，不超过 5MB，支持拖拽</small></span>
    <div
      class="image-drop"
      :class="{ 'is-active': dragging, 'has-image': props.modelValue }"
      @dragover.prevent="dragging = true"
      @dragenter.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <div class="image-drop-preview">
        <img v-if="props.modelValue" :src="imageSrc(props.modelValue)" alt="图片预览" />
        <div v-else class="image-drop-empty">
          拖拽图片到这里<br />
          <small>或点击右侧按钮选择</small>
        </div>
      </div>
      <div class="row wrap">
        <button type="button" class="btn btn-sm" :disabled="busy" @click="input?.click()">
          {{ busy ? '上传中…' : props.modelValue ? '更换图片' : '选择图片' }}
        </button>
        <button v-if="props.modelValue" type="button" class="btn btn-sm btn-ghost" @click="clear">移除</button>
        <span v-if="busy" class="badge">上传中…</span>
      </div>
      <input ref="input" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="onPick" />
    </div>
  </div>
</template>
