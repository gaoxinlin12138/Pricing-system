<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  api,
  formatDate,
  imageSrc,
  money,
  qty,
  statusLabel,
  type Accessory,
  type BundleDetail,
  type BundleItem,
  type BundleQuotePreview,
  type BundleSummary,
  type QuoteDetail,
  type QuoteSummary,
} from '../api'
import { toast } from '../ui/toast'
import AppModal from './AppModal.vue'
import ImageViewer from './ImageViewer.vue'

const bundles = ref<BundleSummary[]>([])
const quotes = ref<QuoteSummary[]>([])
const loading = ref(true)
const query = ref('')
const step = ref(1)
/** 第二步点击「确认报价」后才允许进入第三步并试算。 */
const confirmed = ref(false)
const setCount = ref(1)
const MAX_SET_COUNT = 99
const BODY_CATEGORY = '主体'
const DEFAULT_MULTIPLIER = 1.5
const DEFAULT_LABOR_FEE = 80
// 每次报价独立维护，不会修改后台默认计价设置或其它套装。
const quoteMultiplier = ref(DEFAULT_MULTIPLIER)
const quoteLaborFee = ref(DEFAULT_LABOR_FEE)
const pricingDefaults = reactive({ multiplier: DEFAULT_MULTIPLIER, labor_fee: DEFAULT_LABOR_FEE })

const selected = ref<BundleDetail | null>(null)
const draft = reactive<Record<number, { accessory_id: number; quantity: number }>>({})
const bodyDraft = ref<number | null>(null)
const preview = ref<BundleQuotePreview | null>(null)
const previewing = ref(false)
const previewError = ref('')
const saving = ref(false)
const savedQuote = ref<{ quote_no: string; final_price: string; valid_until: string } | null>(null)

const replacingItem = ref<BundleItem | null>(null)
const replacingBody = ref(false)

const quoteDetail = ref<QuoteDetail | null>(null)
const quoteDetailOpen = ref(false)
const viewer = ref<{ src: string; title: string; subtitle?: string } | null>(null)

const searchInput = ref<HTMLInputElement | null>(null)

const filteredBundles = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return bundles.value
  return bundles.value.filter((bundle) =>
    [bundle.name, bundle.code, bundle.description, bundle.body?.name, bundle.body?.model]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(needle),
  )
})

const lines = computed(() => {
  if (!selected.value) return []
  return selected.value.items.map((item) => {
    const entry = draft[item.id] || { accessory_id: item.accessory.id, quantity: Number(item.quantity) }
    const options = selected.value?.replacement_candidates?.[item.accessory.category] || []
    const replacement = options.find((option) => option.id === entry.accessory_id)
    const accessory: Accessory = replacement || item.accessory
    return {
      item,
      accessory,
      quantity: entry.quantity,
      changed: accessory.id !== item.accessory.id,
    }
  })
})

const bodyAccessory = computed(() => {
  const original = selected.value?.body
  if (!original) return null
  const selectedId = bodyDraft.value ?? original.id
  return selected.value?.replacement_candidates?.[BODY_CATEGORY]?.find((option) => option.id === selectedId) || original
})

const bodyChanged = computed(() => !!selected.value?.body && bodyAccessory.value?.id !== selected.value.body.id)

const replacedCount = computed(() => lines.value.filter((line) => line.changed).length + (bodyChanged.value ? 1 : 0))

const candidateList = computed(() => {
  if (replacingBody.value) return selected.value?.replacement_candidates?.[BODY_CATEGORY] || []
  const item = replacingItem.value
  if (!item || !selected.value) return []
  return selected.value.replacement_candidates?.[item.accessory.category] || []
})

const replacementTarget = computed(() => {
  if (replacingBody.value && bodyAccessory.value) {
    return { name: bodyAccessory.value.name, category: BODY_CATEGORY, currentId: bodyAccessory.value.id }
  }
  if (replacingItem.value) {
    return { name: replacingItem.value.accessory.name, category: replacingItem.value.accessory.category, currentId: draft[replacingItem.value.id]?.accessory_id }
  }
  return null
})

function buildPayload() {
  if (!selected.value) return null
  return {
    bundle_id: selected.value.id,
    body_id: bodyDraft.value ?? selected.value.body?.id,
    set_quantity: setCount.value,
    multiplier: Number(quoteMultiplier.value),
    labor_fee: Number(quoteLaborFee.value),
    lines: selected.value.items.map((item) => ({
      bundle_item_id: item.id,
      accessory_id: draft[item.id]?.accessory_id ?? item.accessory.id,
      quantity: draft[item.id]?.quantity ?? Number(item.quantity),
    })),
  }
}

function normalizePricingInputs() {
  const multiplier = Number(quoteMultiplier.value)
  const laborFee = Number(quoteLaborFee.value)
  quoteMultiplier.value = Number.isFinite(multiplier) ? Math.max(1, multiplier) : DEFAULT_MULTIPLIER
  quoteLaborFee.value = Number.isFinite(laborFee) ? Math.max(0, laborFee) : DEFAULT_LABOR_FEE
}

function pricingChanged() {
  normalizePricingInputs()
  preview.value = null
  previewError.value = ''
  savedQuote.value = null
  if (step.value === 3 && confirmed.value) void runPreview()
}

async function load() {
  loading.value = true
  try {
    const [bundleRows, quoteRows, defaults] = await Promise.all([
      api<BundleSummary[]>('/api/catalog/bundles'),
      api<QuoteSummary[]>('/api/quotes'),
      api<{ multiplier: string; labor_fee: string }>('/api/pricing-defaults'),
    ])
    bundles.value = bundleRows
    quotes.value = quoteRows
    const defaultMultiplier = Number(defaults.multiplier)
    const defaultLaborFee = Number(defaults.labor_fee)
    pricingDefaults.multiplier = Number.isFinite(defaultMultiplier) && defaultMultiplier >= 1 ? defaultMultiplier : DEFAULT_MULTIPLIER
    pricingDefaults.labor_fee = Number.isFinite(defaultLaborFee) && defaultLaborFee >= 0 ? defaultLaborFee : DEFAULT_LABOR_FEE
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    loading.value = false
  }
}

async function openBundle(bundle: BundleSummary) {
  try {
    const detail = await api<BundleDetail>(`/api/catalog/bundles/${bundle.id}`)
    selected.value = detail
    Object.keys(draft).forEach((key) => delete draft[Number(key)])
    detail.items.forEach((item) => {
      draft[item.id] = { accessory_id: item.accessory.id, quantity: Number(item.quantity) }
    })
    bodyDraft.value = detail.body?.id || null
    confirmed.value = false
    setCount.value = 1
    quoteMultiplier.value = pricingDefaults.multiplier
    quoteLaborFee.value = pricingDefaults.labor_fee
    savedQuote.value = null
    preview.value = null
    previewError.value = ''
    step.value = 2
    window.scrollTo({ top: 0 })
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}

function backToSearch() {
  confirmed.value = false
  setCount.value = 1
  step.value = 1
  selected.value = null
  bodyDraft.value = null
  closeReplacement()
  preview.value = null
  previewError.value = ''
}

function normalizeSetCount() {
  const value = Math.round(Number(setCount.value) || 1)
  setCount.value = Math.min(MAX_SET_COUNT, Math.max(1, value))
}

function stepSetCount(delta: number) {
  const current = Math.min(MAX_SET_COUNT, Math.max(1, Math.round(Number(setCount.value) || 1)))
  setCount.value = Math.min(MAX_SET_COUNT, Math.max(1, current + delta))
}

function qtyBounds(accessory: Accessory) {
  return { min: Number(accessory.min_qty || 0), max: Number(accessory.max_qty || 99) }
}

function clampQuantity(accessory: Accessory, value: number) {
  const { min, max } = qtyBounds(accessory)
  if (!Number.isFinite(value)) return Math.max(min, 1)
  return Math.min(max, Math.max(min, value))
}

function setQuantity(itemId: number, value: number, accessory: Accessory) {
  if (!draft[itemId]) return
  draft[itemId].quantity = clampQuantity(accessory, Number(value))
  confirmed.value = false
  savedQuote.value = null
}

function applyReplacement(accessory: Accessory) {
  if (replacingBody.value) {
    bodyDraft.value = accessory.id
    replacingBody.value = false
    confirmed.value = false
    savedQuote.value = null
    return
  }
  const item = replacingItem.value
  if (!item || !draft[item.id]) return
  draft[item.id].accessory_id = accessory.id
  draft[item.id].quantity = clampQuantity(accessory, draft[item.id].quantity)
  replacingItem.value = null
  confirmed.value = false
  savedQuote.value = null
}

function restoreBody() {
  bodyDraft.value = selected.value?.body?.id || null
  confirmed.value = false
  savedQuote.value = null
}

function closeReplacement() {
  replacingItem.value = null
  replacingBody.value = false
}

function restoreOriginal(item: BundleItem) {
  if (!draft[item.id]) return
  draft[item.id].accessory_id = item.accessory.id
  draft[item.id].quantity = Number(item.quantity)
  confirmed.value = false
  savedQuote.value = null
}

async function runPreview() {
  normalizeSetCount()
  const payload = buildPayload()
  if (!payload) return
  previewing.value = true
  try {
    preview.value = await api<BundleQuotePreview>('/api/quotes/preview', { method: 'POST', body: JSON.stringify(payload) })
  } catch (exception) {
    preview.value = null
    previewError.value = (exception as Error).message
  } finally {
    previewing.value = false
  }
}

async function saveQuote() {
  normalizeSetCount()
  const payload = buildPayload()
  if (!payload || saving.value) return
  saving.value = true
  previewError.value = ''
  try {
    const created = await api<{ quote_no: string; final_price: string; valid_until: string }>('/api/quotes', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    savedQuote.value = created
    preview.value = await api<BundleQuotePreview>('/api/quotes/preview', { method: 'POST', body: JSON.stringify(payload) })
    quotes.value = await api<QuoteSummary[]>('/api/quotes')
    toast(`报价单 ${created.quote_no} 已保存，原预设套装未被修改`, 'ok')
  } catch (exception) {
    previewError.value = (exception as Error).message
    toast((exception as Error).message, 'err')
  } finally {
    saving.value = false
  }
}

function restart() {
  step.value = 1
  confirmed.value = false
  setCount.value = 1
  quoteMultiplier.value = pricingDefaults.multiplier
  quoteLaborFee.value = pricingDefaults.labor_fee
  selected.value = null
  bodyDraft.value = null
  closeReplacement()
  savedQuote.value = null
  preview.value = null
  query.value = ''
}

function goStep(target: 1 | 2 | 3) {
  if (target === 1) {
    // 通过步骤条回到搜索时保留当前选择，但返回 02 后需要重新确认。
    confirmed.value = false
    step.value = 1
    return
  }
  if (!selected.value) return
  if (target === 3 && !confirmed.value) return
  if (target === 2) confirmed.value = false
  step.value = target
}

function confirmQuote() {
  if (!selected.value) return
  normalizeSetCount()
  normalizePricingInputs()
  confirmed.value = true
  step.value = 3
}

const unitPrice = computed(() => {
  if (!preview.value) return null
  if (preview.value.unit_price) return Number(preview.value.unit_price)
  const quantity = Number(preview.value.set_quantity) || 1
  return Number(preview.value.final_price) / quantity
})

const unitPriceText = computed(() => {
  if (unitPrice.value !== null) return `¥ ${money(unitPrice.value)}`
  if (previewError.value) return '—'
  return previewing.value ? '计算中…' : '—'
})

const totalPriceText = computed(() => {
  if (unitPrice.value !== null) return `¥ ${money(unitPrice.value * Math.max(1, setCount.value))}`
  if (previewError.value) return '—'
  return previewing.value ? '计算中…' : '—'
})

async function openQuote(quoteNo: string) {
  try {
    quoteDetail.value = await api<QuoteDetail>(`/api/quotes/${quoteNo}`)
    quoteDetailOpen.value = true
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}

function openImage(src: string | undefined | null, title: string, subtitle?: string) {
  if (!src) return
  viewer.value = { src: imageSrc(src), title, subtitle }
}

function quoteReplacementNames(): string[] {
  const detail = quoteDetail.value
  if (!detail) return []
  return (detail.replacements || []).map((item) => `${item.original_name} → ${item.replacement_name}`)
}

function lineReplaced(name: string): boolean {
  const detail = quoteDetail.value
  if (!detail) return false
  return (detail.replacements || []).some((item) => item.replacement_name === name)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== '/' || step.value !== 1) return
  const target = event.target as HTMLElement | null
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  event.preventDefault()
  searchInput.value?.focus()
}

// 第二步不计算价格，避免员工通过反复替换配件反推单件成本；进入第三步才试算。
watch(step, (value) => {
  if (value === 3 && selected.value && confirmed.value) {
    void runPreview()
    return
  }
  preview.value = null
  previewError.value = ''
  previewing.value = false
})

onMounted(() => {
  void load()
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="content">
    <div class="page-head">
      <div>
        <p class="eyebrow">员工报价台</p>
        <h1 class="page-title">从预设套装开始报价</h1>
        <p class="page-sub">搜索套装 → 查看配件并按需替换 → 计算对外售价并保存报价单。保存只记录本次组合，不会改动原套装。</p>
      </div>
    </div>

    <div class="stepper">
      <button class="step" :class="{ active: step === 1, done: step > 1 }" @click="goStep(1)">
        <span class="step-no">01</span>搜索套装
      </button>
      <button class="step" :class="{ active: step === 2, done: step > 2 }" :disabled="!selected" @click="goStep(2)">
        <span class="step-no">02</span>查看与替换
      </button>
      <button
        class="step"
        :class="{ active: step === 3 }"
        :disabled="!selected || !confirmed"
        :title="!selected ? '请先选择套装' : !confirmed ? '请先在第二步确认报价' : '查看最终售价并保存报价单'"
        @click="goStep(3)"
      >
        <span class="step-no">03</span>确认并保存报价
      </button>
    </div>

    <div class="employee-grid">
      <section class="card">
        <div class="card-body">
          <!-- 步骤一：搜索 -->
          <template v-if="step === 1">
            <div class="page-head" style="margin-bottom: 16px">
              <div>
                <h2 class="card-title">预设套装</h2>
                <p class="page-sub">支持搜索套装名称、主体名称或型号。</p>
              </div>
              <span class="badge">{{ filteredBundles.length }} 套可报价</span>
            </div>

            <div class="toolbar">
              <div class="search">
                <span class="search-icon">⌕</span>
                <input ref="searchInput" v-model="query" class="input" placeholder="搜索套装或主体，按 / 快速聚焦" />
              </div>
            </div>

            <div v-if="loading" class="bundle-grid">
              <div v-for="index in 3" :key="index" class="skeleton" style="height: 220px"></div>
            </div>

            <div v-else-if="filteredBundles.length" class="bundle-grid">
              <button v-for="bundle in filteredBundles" :key="bundle.id" class="bundle-card" @click="openBundle(bundle)">
                <span class="bundle-media">
                  <img v-if="bundle.image_url" :src="imageSrc(bundle.image_url)" :alt="bundle.name" />
                  <span v-else class="bundle-media-empty">✦</span>
                  <span class="bundle-count">{{ bundle.item_count }} 个配件</span>
                </span>
                <span class="bundle-copy">
                  <strong>{{ bundle.name }}</strong>
                  <small>{{ bundle.code ? `${bundle.code} · ` : '' }}{{ bundle.body?.name }} · {{ bundle.body?.model }}</small>
                  <p>{{ bundle.description || '暂无说明' }}</p>
                </span>
              </button>
            </div>

            <div v-else class="empty">
              <span class="empty-icon">✦</span>
              <strong>{{ query ? '没有匹配的套装' : '还没有可报价的套装' }}</strong>
              <p>{{ query ? '换个关键词试试，或者清空搜索条件。' : '请管理员先在后台「套装」里创建预设套装，这里就会自动出现。' }}</p>
              <button v-if="query" class="btn btn-sm" @click="query = ''">清空搜索</button>
            </div>
          </template>

          <!-- 步骤二：查看与替换 -->
          <template v-else-if="step === 2 && selected">
            <div class="bundle-header">
              <div>
                <p class="eyebrow">STEP 02 · 套装明细</p>
                <h2>{{ selected.name }}</h2>
                <p class="page-sub">{{ selected.description || '暂无说明' }}</p>
              </div>
              <button class="btn btn-sm" @click="backToSearch">← 返回搜索</button>
            </div>

            <div class="bundle-hero">
              <button
                type="button"
                class="bundle-hero-media"
                :class="{ 'is-empty': !selected.image_url }"
                :disabled="!selected.image_url"
                :title="selected.image_url ? '点击查看大图' : '暂无套装成品图'"
                @click="openImage(selected.image_url, selected.name, selected.code ? `套装成品图 · ${selected.code}` : '套装成品图')"
              >
                <img v-if="selected.image_url" :src="imageSrc(selected.image_url)" :alt="selected.name" />
                <span v-else class="hero-empty">
                  <span>✦</span>
                  <small>暂无套装成品图</small>
                </span>
              </button>
              <div class="bundle-hero-info">
                <div class="row wrap">
                  <span class="badge">v{{ selected.version }}</span>
                  <span v-if="selected.code" class="badge mono">{{ selected.code }}</span>
                  <span class="badge">{{ selected.items.length + 1 }} 件物料</span>
                </div>
                <p class="hero-caption">套装成品</p>
                <h3>{{ selected.name }}</h3>
                 <p class="page-sub">1 个主体 + {{ selected.items.length }} 个配件共同构成这套成品；主体和配件都可按类别替换，主体数量固定为 1。</p>
              </div>
            </div>

            <div class="bom">
              <div class="bom-head"><span>物料明细</span><span>数量</span><span>操作</span></div>

              <div class="bom-row is-body">
                <button
                  type="button"
                  class="thumb thumb-button"
                  :disabled="!bodyAccessory?.image_url"
                  :title="bodyAccessory?.image_url ? '点击查看大图' : '暂无图片'"
                  @click="openImage(bodyAccessory?.image_url, bodyAccessory?.name || '主体', bodyAccessory?.model)"
                >
                  <img v-if="bodyAccessory?.image_url" :src="imageSrc(bodyAccessory.image_url)" :alt="bodyAccessory?.name" />
                  <span v-else>◈</span>
                </button>
                <div class="item-info">
                  <b>{{ bodyAccessory?.name }} <span class="badge">主体</span><span v-if="bodyChanged" class="badge">已替换</span></b>
                  <small>{{ bodyAccessory?.model }}</small>
                </div>
                <span class="num bom-qty">1</span>
                <div class="row bom-actions">
                  <button class="btn btn-sm" @click="replacingBody = true">替换</button>
                  <button v-if="bodyChanged" class="btn btn-sm btn-ghost" @click="restoreBody">恢复</button>
                </div>
              </div>

              <div v-for="line in lines" :key="line.item.id" class="bom-row">
                <button
                  type="button"
                  class="thumb thumb-button"
                  :disabled="!line.accessory.image_url"
                  :title="line.accessory.image_url ? '点击查看大图' : '暂无图片'"
                  @click="openImage(line.accessory.image_url, line.accessory.name, `${line.accessory.category} · ${line.accessory.model}`)"
                >
                  <img v-if="line.accessory.image_url" :src="imageSrc(line.accessory.image_url)" :alt="line.accessory.name" />
                  <span v-else>✧</span>
                </button>
                <div class="item-info">
                  <b>{{ line.accessory.name }} <span v-if="line.changed" class="badge">已替换</span></b>
                  <small>
                    <span class="chip">{{ line.accessory.category }}</span>
                    {{ line.accessory.model }}
                  </small>
                  <div v-if="Object.keys(line.accessory.attributes || {}).length" class="attrs">
                    <span v-for="(value, key) in line.accessory.attributes" :key="key" class="chip">{{ key }}：{{ value }}</span>
                  </div>
                </div>
                <input
                  class="input qty-input bom-qty"
                  type="number"
                  :min="line.accessory.min_qty"
                  :max="line.accessory.max_qty"
                  :value="line.quantity"
                  aria-label="数量"
                  @change="setQuantity(line.item.id, Number(($event.target as HTMLInputElement).value), line.accessory)"
                />
                <div class="row bom-actions">
                  <button class="btn btn-sm" @click="replacingItem = line.item">替换</button>
                  <button v-if="line.changed" class="btn btn-sm btn-ghost" @click="restoreOriginal(line.item)">恢复</button>
                </div>
              </div>
            </div>
          </template>

          <!-- 步骤三：确认 -->
          <template v-else-if="step === 3 && selected">
            <div class="bundle-header">
              <div>
                <p class="eyebrow">STEP 03 · 确认报价</p>
                <h2>{{ selected.name }}</h2>
                <p class="page-sub">确认套装明细后保存报价单。保存后原套装保持不变。</p>
              </div>
              <button class="btn btn-sm" @click="goStep(2)">← 返回替换</button>
            </div>

            <div class="bom">
              <div class="bom-head"><span>物料明细</span><span>数量</span><span>状态</span></div>

              <div class="bom-row is-body">
                <button
                  type="button"
                  class="thumb thumb-button"
                  :disabled="!bodyAccessory?.image_url"
                  :title="bodyAccessory?.image_url ? '点击查看大图' : '暂无图片'"
                  @click="openImage(bodyAccessory?.image_url, bodyAccessory?.name || '主体', bodyAccessory?.model)"
                >
                  <img v-if="bodyAccessory?.image_url" :src="imageSrc(bodyAccessory.image_url)" :alt="bodyAccessory?.name" />
                  <span v-else>◈</span>
                </button>
                <div class="item-info">
                  <b>{{ bodyAccessory?.name }} <span class="badge">主体</span></b>
                  <small>{{ bodyAccessory?.model }}</small>
                </div>
                <span class="num bom-qty">1</span>
                <span v-if="bodyChanged" class="badge">已替换</span>
                <span v-else class="muted bom-fixed">原配</span>
              </div>

              <div v-for="line in lines" :key="line.item.id" class="bom-row">
                <button
                  type="button"
                  class="thumb thumb-button"
                  :disabled="!line.accessory.image_url"
                  :title="line.accessory.image_url ? '点击查看大图' : '暂无图片'"
                  @click="openImage(line.accessory.image_url, line.accessory.name, `${line.accessory.category} · ${line.accessory.model}`)"
                >
                  <img v-if="line.accessory.image_url" :src="imageSrc(line.accessory.image_url)" :alt="line.accessory.name" />
                  <span v-else>✧</span>
                </button>
                <div class="item-info">
                  <b>{{ line.accessory.name }}</b>
                  <small>{{ line.accessory.category }} · {{ line.accessory.model }}</small>
                </div>
                <span class="num bom-qty">× {{ line.quantity }}</span>
                <span v-if="line.changed" class="badge">已替换</span>
                <span v-else class="muted bom-fixed">原配</span>
              </div>
            </div>

            <div v-if="savedQuote" class="quick-item" style="margin-top: 20px">
              <div>
                <b>报价单 {{ savedQuote.quote_no }} 已保存</b>
                <small>有效期至 {{ formatDate(savedQuote.valid_until) }} · 原套装未被修改</small>
              </div>
              <div class="row">
                <button class="btn btn-sm" @click="openQuote(savedQuote.quote_no)">查看报价单</button>
                <button class="btn btn-sm" @click="restart">再开一单</button>
              </div>
            </div>
          </template>
        </div>
      </section>

      <aside class="rail">
        <div v-if="selected" class="card">
          <div class="card-head" style="padding: 14px 20px">
            <h3 class="card-title">{{ step === 3 ? '报价汇总' : '确认报价' }}</h3>
            <span v-if="step === 3 && previewing" class="badge">计算中…</span>
          </div>
          <div class="card-body">
            <div v-if="step === 3" class="quote-params">
              <div class="quote-params-head">
                <div>
                  <b>本套计价参数</b>
                  <small>根据当前套装和配件实际情况调整，只作用于本次报价</small>
                </div>
                <span class="badge">可调整</span>
              </div>
              <div class="form-grid">
                <label class="field">
                  <span>倍率</span>
                  <input v-model.number="quoteMultiplier" class="input" type="number" min="1" step="0.01" @change="pricingChanged" />
                </label>
                <label class="field">
                  <span>人工费（元）</span>
                  <input v-model.number="quoteLaborFee" class="input" type="number" min="0" step="1" @change="pricingChanged" />
                </label>
              </div>
              <p class="form-hint">单套售价 =（主体成本 + 配件成本 + 人工费）× 倍率</p>
            </div>

            <div v-if="step === 3" class="price-box">
              <span>最终总价</span>
              <strong>{{ totalPriceText }}</strong>
              <small>单套 {{ unitPriceText }} × {{ setCount }} 套</small>
            </div>
            <div v-else class="price-locked">
              <b>确认报价后显示售价</b>
              <small>请核对配件和数量，确认无误后点击「<span class="nowrap">确认报价</span>」查看最终售价。</small>
            </div>

            <p v-if="step === 3 && previewError" class="form-error">{{ previewError }}</p>

            <div v-if="step === 3" class="summary-line set-qty-line">
              <span>套装套数</span>
              <div class="set-qty">
                <button type="button" class="qty-btn" :disabled="setCount <= 1" aria-label="减少一套" @click="stepSetCount(-1)">−</button>
                <input
                  v-model.number="setCount"
                  class="input qty-input"
                  type="number"
                  min="1"
                  :max="MAX_SET_COUNT"
                  step="1"
                  aria-label="套装套数"
                  @change="normalizeSetCount"
                />
                <button type="button" class="qty-btn" :disabled="setCount >= MAX_SET_COUNT" aria-label="增加一套" @click="stepSetCount(1)">＋</button>
              </div>
            </div>

              <div class="summary-line">
                <span>物料数量</span>
                <b>{{ lines.length + 1 }} 项</b>
            </div>
            <div class="summary-line">
              <span>已替换</span>
              <b>{{ replacedCount }} 项</b>
            </div>
            <div v-if="step === 3 && preview" class="summary-line">
              <span>报价有效期</span>
              <b>{{ preview.quote_valid_days }} 天</b>
            </div>

            <button v-if="step === 2" class="btn btn-primary btn-block" style="margin-top: 16px" @click="confirmQuote">
              确认报价 →
            </button>
            <button
              v-if="step === 3 && !savedQuote"
              class="btn btn-primary btn-block"
              style="margin-top: 16px"
              :disabled="saving || previewing || !preview || !!previewError"
              @click="saveQuote"
            >
              <span v-if="saving" class="spinner"></span>{{ saving ? '保存中…' : '保存报价单' }}
            </button>
            <button v-if="savedQuote" class="btn btn-block" style="margin-top: 16px" @click="openQuote(savedQuote.quote_no)">
              查看已保存的报价单
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-head" style="padding: 14px 20px">
            <h3 class="card-title">最近报价</h3>
            <span class="badge">{{ quotes.length }}</span>
          </div>
          <div class="card-body tight">
            <div v-if="quotes.length" class="history">
              <button v-for="quote in quotes.slice(0, 6)" :key="quote.quote_no" class="history-item" @click="openQuote(quote.quote_no)">
                <span>
                  <b>{{ quote.bundle_name || '自定义组合' }}</b>
                  <small>{{ quote.quote_no }} · {{ quote.set_quantity || 1 }} 套 · {{ formatDate(quote.created_at) }}</small>
                </span>
                <b>¥ {{ money(quote.final_price) }}</b>
              </button>
            </div>
            <div v-else class="empty" style="padding: 24px 8px">
              <strong>还没有报价记录</strong>
              <p>保存第一张报价单后会显示在这里。</p>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- 替换主体或配件 -->
    <AppModal v-if="replacementTarget" medium :title="`替换「${replacementTarget.name}」`" :subtitle="`只能从同类别（${replacementTarget.category}）的配件中选择`" @close="closeReplacement">
      <div v-if="candidateList.length" class="stack">
        <button
          v-for="option in candidateList"
          :key="option.id"
          class="quick-item replacement-option"
          style="cursor: pointer; text-align: left"
          :disabled="option.id === replacementTarget.currentId"
          @click="applyReplacement(option)"
        >
          <span class="product">
            <span class="thumb">
              <img v-if="option.image_url" :src="imageSrc(option.image_url)" :alt="option.name" />
              <span v-else>✧</span>
            </span>
            <span class="product-main">
              <strong>{{ option.name }}</strong>
              <small>
                <span class="chip">{{ option.category }}</span>
                {{ option.model }} · 可调数量 {{ qty(option.min_qty) }}–{{ qty(option.max_qty) }}
              </small>
              <span v-if="Object.keys(option.attributes || {}).length" class="attrs">
                <span v-for="(value, key) in option.attributes" :key="key" class="chip">{{ key }}：{{ value }}</span>
              </span>
            </span>
          </span>
           <span v-if="option.id === replacementTarget.currentId" class="badge">当前选择</span>
          <span v-else class="btn btn-sm">选择</span>
        </button>
      </div>
      <div v-else class="empty">
        <strong>该类别下没有其它启用配件</strong>
        <p>请管理员在后台「配件」中添加同类别配件后再来替换。</p>
      </div>
    </AppModal>

    <!-- 报价单详情 -->
    <AppModal v-if="quoteDetailOpen && quoteDetail" :title="`报价单 ${quoteDetail.quote_no}`" :subtitle="`${statusLabel(quoteDetail.status)} · 有效期至 ${formatDate(quoteDetail.valid_until)}`" wide @close="quoteDetailOpen = false">
      <div class="stack">
        <div class="row wrap">
          <span class="badge">{{ quoteDetail.bundle?.name || '自定义组合' }}</span>
          <span v-if="quoteDetail.bundle?.code" class="badge mono">{{ quoteDetail.bundle.code }}</span>
          <span class="badge">主体：{{ quoteDetail.body?.name }}</span>
          <span class="badge">{{ quoteDetail.set_quantity || 1 }} 套</span>
        </div>

        <div class="item-list">
          <div class="item-row is-body" style="grid-template-columns: minmax(0, 1fr) auto">
            <div class="item-info">
              <b>{{ quoteDetail.body?.name }} <span class="badge">主体</span><span v-if="lineReplaced(quoteDetail.body?.name || '')" class="badge">已替换</span></b>
              <small>{{ quoteDetail.body?.model }}</small>
            </div>
            <span class="num bom-qty">1</span>
          </div>
          <div v-for="line in quoteDetail.lines" :key="`${line.bundle_item_id}-${line.accessory_id}`" class="item-row" style="grid-template-columns: minmax(0, 1fr) auto">
            <div class="item-info">
              <b>{{ line.name }} <span v-if="lineReplaced(line.name)" class="badge">已替换</span></b>
              <small>{{ line.model }}</small>
            </div>
            <span class="num bom-qty">× {{ line.quantity }}</span>
          </div>
        </div>

        <div v-if="quoteReplacementNames().length" class="formula">
          <span>替换记录</span>
          <span>{{ quoteReplacementNames().join('，') }}</span>
        </div>

        <div class="summary-line">
          <span>本次倍率</span>
          <b>{{ quoteDetail.pricing?.multiplier || '—' }}</b>
        </div>
        <div class="summary-line">
          <span>本次人工费</span>
          <b>¥ {{ money(quoteDetail.pricing?.labor_fee) }}</b>
        </div>
        <div class="summary-line">
          <span>单套售价</span>
          <b>¥ {{ money(quoteDetail.unit_price || quoteDetail.final_price) }}</b>
        </div>
        <div class="summary-line">
          <span>套数</span>
          <b>{{ quoteDetail.set_quantity || 1 }} 套</b>
        </div>
        <div class="summary-line">
          <span>最终总价</span>
          <b style="font-size: 20px; color: var(--brand-ink)">¥ {{ money(quoteDetail.final_price) }}</b>
        </div>
      </div>
    </AppModal>

    <ImageViewer
      v-if="viewer"
      :src="viewer.src"
      :title="viewer.title"
      :subtitle="viewer.subtitle"
      @close="viewer = null"
    />
  </div>
</template>
