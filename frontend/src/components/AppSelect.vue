<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, type CSSProperties } from 'vue'

interface SelectOption {
  value: string | number
  label: string
  image?: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue?: string | number | null
    options: SelectOption[]
    placeholder?: string
    disabled?: boolean
    ariaLabel?: string
    menuLabel?: string
    clearable?: boolean
  }>(),
  { modelValue: null, placeholder: '请选择', disabled: false, ariaLabel: '', menuLabel: '', clearable: false },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: string | number): void
  (event: 'change', value: string | number): void
}>()

const instanceId = `app-select-${useId()}`

const triggerEl = ref<HTMLButtonElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const open = ref(false)
const activeIndex = ref(-1)
const menuStyle = ref<CSSProperties>({})
let trackFrame = 0

const selected = computed(() => props.options.find((option) => Object.is(option.value, props.modelValue)) || null)
const displayLabel = computed(() => selected.value?.label || props.placeholder)
const hasImages = computed(() => props.options.some((option) => !!option.image))

function isSelected(option: SelectOption): boolean {
  return Object.is(option.value, props.modelValue)
}

function firstEnabledIndex(): number {
  return props.options.findIndex((option) => !option.disabled)
}

function lastEnabledIndex(): number {
  for (let index = props.options.length - 1; index >= 0; index -= 1) {
    if (!props.options[index].disabled) return index
  }
  return -1
}

function scrollActiveIntoView() {
  const active = menuEl.value?.querySelector<HTMLElement>('.app-select-option.is-active')
  active?.scrollIntoView({ block: 'nearest' })
}

function setActive(index: number) {
  activeIndex.value = index
  nextTick(scrollActiveIntoView)
}

function moveActive(step: number) {
  if (!props.options.length) return
  let index = activeIndex.value
  for (let count = 0; count < props.options.length; count += 1) {
    index = (index + step + props.options.length) % props.options.length
    if (!props.options[index].disabled) {
      setActive(index)
      return
    }
  }
}

function reposition() {
  const trigger = triggerEl.value
  if (!trigger || !open.value) return
  const rect = trigger.getBoundingClientRect()
  // 下拉始终在触发器下方展开；触发器滚出弹窗内容区时才关闭。
  const scrollParent = trigger.closest('.modal-body') as HTMLElement | null
  const bodyRect = scrollParent?.getBoundingClientRect()
  if (bodyRect && (rect.bottom < bodyRect.top || rect.top > bodyRect.bottom)) {
    close()
    return
  }
  const gap = 6
  const viewportW = window.innerWidth
  const below = window.innerHeight - rect.bottom - gap - 8
  const available = Math.max(60, Math.min(340, below))
  const width = Math.min(Math.max(rect.width, 180), 560, viewportW - 16)
  const left = Math.min(Math.max(8, rect.left), viewportW - width - 8)
  const top = rect.bottom + gap
  menuStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${width}px`,
    maxHeight: `${available}px`,
  }
}

function trackPosition() {
  if (!open.value) return
  reposition()
  trackFrame = requestAnimationFrame(trackPosition)
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !open.value) return
  // 先关下拉，避免同一次 Esc 把外层弹窗也关掉。
  event.preventDefault()
  event.stopPropagation()
  close()
  triggerEl.value?.focus()
}

function addListeners() {
  document.addEventListener('pointerdown', onPointerDown, true)
  document.addEventListener('keydown', onDocumentKeydown, true)
  document.addEventListener('scroll', reposition, true)
  window.addEventListener('resize', reposition)
  cancelAnimationFrame(trackFrame)
  trackFrame = requestAnimationFrame(trackPosition)
}

function removeListeners() {
  document.removeEventListener('pointerdown', onPointerDown, true)
  document.removeEventListener('keydown', onDocumentKeydown, true)
  document.removeEventListener('scroll', reposition, true)
  window.removeEventListener('resize', reposition)
  cancelAnimationFrame(trackFrame)
  trackFrame = 0
}

function openMenu() {
  if (props.disabled || open.value) return
  open.value = true
  const current = props.options.findIndex((option) => isSelected(option) && !option.disabled)
  activeIndex.value = current >= 0 ? current : firstEnabledIndex()
  reposition()
  nextTick(() => {
    reposition()
    scrollActiveIntoView()
    addListeners()
  })
}

function close() {
  if (!open.value) return
  open.value = false
  activeIndex.value = -1
  removeListeners()
}

function toggle() {
  if (open.value) close()
  else openMenu()
}

function clearSelection() {
  if (!props.clearable || props.disabled) return
  close()
  emit('update:modelValue', '')
  emit('change', '')
  triggerEl.value?.focus()
}

function choose(option: SelectOption) {
  if (option.disabled) return
  const changed = !isSelected(option)
  close()
  if (changed) {
    emit('update:modelValue', option.value)
    emit('change', option.value)
  }
  triggerEl.value?.focus()
}

function onPointerDown(event: PointerEvent) {
  const target = event.target as Node | null
  if (!target) return
  if (triggerEl.value?.contains(target) || menuEl.value?.contains(target)) return
  close()
}

function onKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  if (props.clearable && selected.value && (event.key === 'Delete' || event.key === 'Backspace')) {
    event.preventDefault()
    clearSelection()
    return
  }
  if (!open.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
      event.preventDefault()
      openMenu()
      if (event.key === 'ArrowUp') moveActive(-1)
    }
    return
  }
  switch (event.key) {
    case 'Escape':
      event.preventDefault()
      event.stopPropagation()
      close()
      break
    case 'Tab':
      close()
      break
    case 'ArrowDown':
      event.preventDefault()
      moveActive(1)
      break
    case 'ArrowUp':
      event.preventDefault()
      moveActive(-1)
      break
    case 'Home':
      event.preventDefault()
      setActive(firstEnabledIndex())
      break
    case 'End':
      event.preventDefault()
      setActive(lastEnabledIndex())
      break
    case 'Enter':
    case ' ': {
      event.preventDefault()
      const option = props.options[activeIndex.value]
      if (option) choose(option)
      break
    }
    default:
      break
  }
}

function optionId(index: number) {
  return `${instanceId}-option-${index}`
}

onBeforeUnmount(removeListeners)
</script>

<template>
  <div class="app-select">
    <button
      ref="triggerEl"
      type="button"
      class="app-select-trigger"
      :class="{ 'is-open': open }"
      :disabled="disabled"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="`${instanceId}-menu`"
      :aria-activedescendant="open && activeIndex >= 0 ? optionId(activeIndex) : undefined"
      :aria-label="ariaLabel || undefined"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span v-if="selected?.image" class="app-select-trigger-thumb" aria-hidden="true">
        <img :src="selected.image" alt="" />
      </span>
      <span class="app-select-value" :class="{ 'is-placeholder': !selected, 'has-clear': clearable && selected }" :title="displayLabel">{{ displayLabel }}</span>
      <svg class="app-select-chevron" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M6 8l4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <button
      v-if="clearable && selected && !disabled"
      type="button"
      class="app-select-clear"
      :aria-label="ariaLabel ? `清空${ariaLabel}` : '清空当前选项'"
      :title="ariaLabel ? `清空${ariaLabel}` : '清空当前选项'"
      @click.stop="clearSelection"
    >
      <svg viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
      </svg>
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        :id="`${instanceId}-menu`"
        ref="menuEl"
        class="app-select-menu"
        :style="menuStyle"
        role="listbox"
        :aria-label="ariaLabel || undefined"
      >
        <p v-if="menuLabel" class="app-select-menu-head" role="presentation">{{ menuLabel }}</p>
        <button
          v-for="(option, index) in options"
          :id="optionId(index)"
          :key="`${option.value}-${index}`"
          type="button"
          class="app-select-option"
          :class="{ 'is-active': index === activeIndex, 'is-selected': isSelected(option), 'is-disabled': option.disabled }"
          role="option"
          :aria-selected="isSelected(option)"
          :disabled="option.disabled"
          @click="choose(option)"
          @mouseenter="activeIndex = index"
        >
          <span class="app-select-option-main">
            <span v-if="hasImages" class="app-select-option-thumb" aria-hidden="true">
              <img v-if="option.image" :src="option.image" alt="" />
              <span v-else>✧</span>
            </span>
            <span class="app-select-option-label" :title="option.label">{{ option.label }}</span>
          </span>
          <svg v-if="isSelected(option)" class="app-select-check" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M4 10.5l3.5 3.5L16 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <p v-if="!options.length" class="app-select-empty">暂无可选项</p>
      </div>
    </Teleport>
  </div>
</template>
