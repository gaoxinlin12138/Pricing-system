import { reactive } from 'vue'

export interface ConfirmOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

interface ConfirmState {
  open: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
  danger: boolean
  resolve: ((confirmed: boolean) => void) | null
}

export const confirmState = reactive<ConfirmState>({
  open: false,
  title: '',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
  resolve: null,
})

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  if (confirmState.resolve) {
    const previous = confirmState.resolve
    confirmState.resolve = null
    previous(false)
  }
  confirmState.title = options.title
  confirmState.message = options.message
  confirmState.confirmText = options.confirmText || '确定'
  confirmState.cancelText = options.cancelText || '取消'
  confirmState.danger = options.danger ?? false
  confirmState.open = true
  return new Promise((resolve) => {
    confirmState.resolve = resolve
  })
}

export function resolveConfirm(confirmed: boolean): void {
  const resolve = confirmState.resolve
  confirmState.resolve = null
  confirmState.open = false
  resolve?.(confirmed)
}
