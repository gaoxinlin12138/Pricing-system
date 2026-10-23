<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { confirmState, resolveConfirm } from '../ui/confirm'

const cancelEl = ref<HTMLButtonElement | null>(null)
let previousOverflow = ''

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !confirmState.open) return
  event.preventDefault()
  event.stopPropagation()
  resolveConfirm(false)
}

watch(
  () => confirmState.open,
  async (open) => {
    if (open) {
      previousOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      document.addEventListener('keydown', onKeydown, true)
      await nextTick()
      cancelEl.value?.focus()
    } else {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeydown, true)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown, true)
  document.body.style.overflow = previousOverflow
})
</script>

<template>
  <Teleport to="body">
    <div v-if="confirmState.open" class="confirm-mask" @click.self="resolveConfirm(false)">
      <div class="confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-message">
        <div class="confirm-head">
          <span class="confirm-icon" :class="{ 'is-danger': confirmState.danger }" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none">
              <path d="M10 3.5l6.5 12h-13L10 3.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
              <path d="M10 8v3.2M10 13.6v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          </span>
          <div class="confirm-copy">
            <h3 id="confirm-dialog-title" class="confirm-title">{{ confirmState.title }}</h3>
            <p id="confirm-dialog-message" class="confirm-message">{{ confirmState.message }}</p>
          </div>
        </div>
        <div class="confirm-actions">
          <button ref="cancelEl" type="button" class="btn" @click="resolveConfirm(false)">{{ confirmState.cancelText }}</button>
          <button
            type="button"
            class="btn"
            :class="confirmState.danger ? 'btn-danger' : 'btn-primary'"
            @click="resolveConfirm(true)"
          >
            {{ confirmState.confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
