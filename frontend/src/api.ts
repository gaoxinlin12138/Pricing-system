export type Role = 'admin' | 'employee'

export interface Session {
  username: string
  role: Role
}

export interface Body {
  id: number
  name: string
  model: string
  description: string
  image_url: string
  cost?: string
  active?: boolean
  version?: number
  updated_at?: string
}

export interface Accessory {
  id: number
  name: string
  model: string
  category: string
  image_url: string
  description: string
  attributes: Record<string, string>
  default_qty: string
  min_qty: string
  max_qty: string
  cost?: string
  active?: boolean
  version?: number
  updated_at?: string
}

export interface BundleItem {
  id: number
  accessory: Accessory
  quantity: string
  position: number
}

export interface BundleSummary {
  id: number
  name: string
  code: string
  description: string
  image_url: string
  version: number
  body: Body | null
  item_count: number
}

export interface BundleDetail extends BundleSummary {
  items: BundleItem[]
  replacement_candidates: Record<string, Accessory[]>
}

export interface AdminBundle extends BundleDetail {
  active: boolean
  updated_at: string
}

export interface QuoteLine {
  accessory_id: number
  name: string
  model: string
  quantity: string
  bundle_item_id?: number
  line_cost?: string
}

export interface BundleQuotePreview {
  bundle?: { id: number; name: string; code: string; version: number; description: string; image_url: string }
  body: { id: number; name: string; model: string }
  lines: QuoteLine[]
  original_bundle_items?: Array<{
    bundle_item_id: number
    accessory_id: number
    name: string
    model: string
    category: string
    quantity: string
    position: number
  }>
  replacements?: Array<{
    bundle_item_id?: number | null
    original_accessory_id: number
    original_name: string
    replacement_accessory_id: number
    replacement_name: string
    category: string
  }>
  set_quantity: number
  unit_price: string
  final_price: string
  quote_valid_days: number
  pricing?: { multiplier: string; labor_fee: string }
  quote_no?: string
  created_at?: string
  valid_until?: string
  status?: string
  private?: Record<string, string>
}

export interface QuoteSummary {
  quote_no: string
  created_at: string
  valid_until: string
  status: string
  set_quantity: number
  unit_price: string
  final_price: string
  bundle_name: string
  body_name: string
  replacement_count: number
  username?: string
}

export interface QuoteDetail extends Omit<BundleQuotePreview, 'private'> {
  quote_no: string
  created_at: string
  valid_until: string
  status: string
}

export interface PricingSettings {
  multiplier: string
  labor_fee: string
  quote_valid_days: number
}

export interface QuoteSettings {
  quote_valid_days: number
}

export interface AdminUser {
  id: number
  username: string
  role: Role
  active: boolean
  last_login: string | null
  created_at: string
}

export interface AuditLog {
  id: number
  username: string
  action: string
  action_label: string
  target_type: string
  target_type_label: string
  target_id: string | null
  target_label: string | null
  target_deleted: boolean
  detail: Record<string, unknown>
  created_at: string
}

export interface CategorySchema {
  category: string
  note?: string
  fields: Array<{
    key: string
    label: string
    type: 'text' | 'select'
    unit?: string
    options?: string[]
  }>
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> | undefined) }
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(path, { credentials: 'include', ...options, headers })
  } catch {
    throw new ApiError('连不上服务器，请确认后端是否还在运行。', 0)
  }

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/api/auth/login')) {
      window.dispatchEvent(new CustomEvent('pricing:session-expired'))
    }
    throw new ApiError(payload.message || payload.detail || `请求失败（${response.status}）`, response.status)
  }
  return payload as T
}

export function money(value: string | number | undefined | null): string {
  const number = Number(value ?? 0)
  if (!Number.isFinite(number)) return '0.00'
  return number.toFixed(2)
}

export function roundMoney(value: number): string {
  // 先按分取整再四舍五入，避免 1015.5×1.13 这类浮点误差导致与后端 Decimal 差 1 分。
  const cents = Number((value * 100).toFixed(6))
  return (Math.round(cents) / 100).toFixed(2)
}

export function qty(value: string | number | undefined | null): string {
  const number = Number(value ?? 0)
  if (!Number.isFinite(number)) return '0'
  return String(Math.round(number * 1000) / 1000)
}

export function statusLabel(status: string): string {
  return { saved: '有效', active: '有效', void: '已作废', expired: '已过期' }[status] || status
}

export function formatDate(value: string | undefined | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

export async function uploadImage(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  const result = await api<{ url: string }>('/api/admin/uploads', { method: 'POST', body: form })
  return result.url
}

/**
 * 上传接口返回的是带端口的绝对地址；开发/部署时端口可能变化。
 * 统一把 /uploads/ 路径转成同源相对路径，由 Vite 代理或 Nginx 转发。
 */
export function imageSrc(url: string | undefined | null): string {
  if (!url) return ''
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.pathname.startsWith('/uploads/')) return parsed.pathname
    return url
  } catch {
    return url
  }
}
