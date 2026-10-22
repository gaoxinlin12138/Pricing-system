import { reactive } from 'vue'

export type ToastKind = 'info' | 'ok' | 'err'

export interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

export const toasts = reactive<ToastItem[]>([])

let sequence = 0

export function toast(message: string, kind: ToastKind = 'info'): void {
  const id = ++sequence
  toasts.push({ id, message, kind })
  while (toasts.length > 3) toasts.shift()
  window.setTimeout(() => {
    const index = toasts.findIndex((item) => item.id === id)
    if (index >= 0) toasts.splice(index, 1)
  }, 3000)
}
