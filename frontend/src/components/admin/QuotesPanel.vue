<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, formatDate, money, statusLabel, type QuoteDetail, type QuoteSummary } from '../../api'
import { confirmDialog } from '../../ui/confirm'
import { toast } from '../../ui/toast'
import AppModal from '../AppModal.vue'

const props = defineProps<{ quotes: QuoteSummary[] }>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const query = ref('')
const detail = ref<QuoteDetail | null>(null)
const detailOpen = ref(false)
const loadingDetail = ref(false)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.quotes
  return props.quotes.filter((quote) => `${quote.quote_no} ${quote.bundle_name} ${quote.username || ''}`.toLowerCase().includes(needle))
})

async function open(quoteNo: string) {
  detailOpen.value = true
  loadingDetail.value = true
  detail.value = null
  try {
    detail.value = await api<QuoteDetail>(`/api/admin/quotes/${quoteNo}`)
  } catch (exception) {
    toast((exception as Error).message, 'err')
    detailOpen.value = false
  } finally {
    loadingDetail.value = false
  }
}

async function voidQuote(quoteNo: string) {
  const confirmed = await confirmDialog({
    title: '作废报价单',
    message: `确定作废报价单 ${quoteNo} 吗？作废后不能再作为有效报价使用。`,
    confirmText: '作废',
    danger: true,
  })
  if (!confirmed) return
  try {
    await api(`/api/admin/quotes/${quoteNo}/void`, { method: 'POST' })
    toast('报价单已作废', 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}

async function remove(quoteNo: string) {
  const confirmed = await confirmDialog({
    title: '删除报价单',
    message: `确定删除报价单 ${quoteNo} 吗？删除后无法恢复。`,
    confirmText: '删除',
    danger: true,
  })
  if (!confirmed) return
  try {
    await api(`/api/admin/quotes/${quoteNo}`, { method: 'DELETE' })
    toast('报价单已删除', 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}

function statusClass(status: string) {
  if (status === 'void') return 'off'
  if (status === 'expired') return 'warn'
  return 'on'
}
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">QUOTES</p>
        <h1 class="page-title">报价记录</h1>
        <p class="page-sub">每张报价单都是保存时的快照，之后的调价或改套装都不会影响它。</p>
      </div>
      <span class="badge">{{ props.quotes.length }} 张报价单</span>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="search" style="max-width: 320px">
          <span class="search-icon">⌕</span>
          <input v-model="query" class="input" placeholder="搜索报价单号、套装或员工" />
        </div>
      </div>
      <div class="card-body tight">
        <div v-if="filtered.length" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>报价单</th><th>套装</th><th>员工</th><th>状态</th><th class="num">套数</th><th class="num">总价</th><th>创建时间</th><th class="actions">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="quote in filtered" :key="quote.quote_no">
                <td class="mono">{{ quote.quote_no }}</td>
                <td>{{ quote.bundle_name || '—' }}</td>
                <td>{{ quote.username || '—' }}</td>
                <td><span class="badge" :class="statusClass(quote.status)">{{ statusLabel(quote.status) }}</span></td>
                <td class="num">{{ quote.set_quantity || 1 }}</td>
                <td class="num">¥ {{ money(quote.final_price) }}</td>
                <td class="muted">{{ formatDate(quote.created_at) }}</td>
                <td class="actions">
                  <div class="row" style="justify-content: flex-end">
                    <button class="btn btn-sm" @click="open(quote.quote_no)">查看</button>
                    <button class="btn btn-sm" :disabled="quote.status === 'void'" @click="voidQuote(quote.quote_no)">作废</button>
                    <button class="btn btn-sm btn-danger" @click="remove(quote.quote_no)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">
          <span class="empty-icon">¥</span>
          <strong>{{ query ? '没有匹配的报价单' : '还没有报价单' }}</strong>
          <p>{{ query ? '换个关键词试试。' : '员工保存报价后会出现在这里。' }}</p>
        </div>
      </div>
    </div>

    <AppModal v-if="detailOpen" :title="detail ? `报价单 ${detail.quote_no}` : '报价单详情'" :subtitle="detail ? `${statusLabel(detail.status)} · ${formatDate(detail.created_at)}` : '加载中…'" wide @close="detailOpen = false">
      <div v-if="loadingDetail" class="stack">
        <div class="skeleton skeleton-line" style="width: 40%"></div>
        <div class="skeleton skeleton-line" style="width: 80%"></div>
        <div class="skeleton skeleton-line" style="width: 65%"></div>
      </div>
      <div v-else-if="detail" class="stack">
        <div class="row wrap">
          <span class="badge">{{ detail.bundle?.name || '自定义组合' }}</span>
          <span v-if="detail.bundle?.code" class="badge mono">{{ detail.bundle.code }}</span>
          <span class="badge">主体：{{ detail.body?.name }}</span>
          <span class="badge">{{ detail.set_quantity || 1 }} 套</span>
          <span class="badge">有效期至 {{ formatDate(detail.valid_until) }}</span>
        </div>
        <div class="item-list">
          <div class="item-row is-body" style="grid-template-columns: minmax(0, 1fr) auto">
            <div class="item-info"><b>{{ detail.body?.name }} <span class="badge">主体</span></b><small>{{ detail.body?.model }}</small></div>
            <span class="num bom-qty">1</span>
          </div>
          <div v-for="line in detail.lines" :key="`${line.accessory_id}-${line.name}`" class="item-row" style="grid-template-columns: minmax(0, 1fr) auto">
            <div class="item-info"><b>{{ line.name }}</b><small>{{ line.model }}</small></div>
            <span class="num bom-qty">× {{ line.quantity }}</span>
          </div>
        </div>
        <div v-if="(detail.replacements || []).length" class="formula">
          <b>配件替换</b>
          <span>{{ (detail.replacements || []).map((item) => `${item.original_name} → ${item.replacement_name}`).join('，') }}</span>
        </div>
        <div class="summary-line">
          <span>单套售价</span>
          <b>¥ {{ money(detail.unit_price || detail.final_price) }}</b>
        </div>
        <div class="summary-line">
          <span>套数</span>
          <b>{{ detail.set_quantity || 1 }} 套</b>
        </div>
        <div class="summary-line">
          <span>最终总价</span>
          <b style="font-size: 20px; color: var(--brand-ink)">¥ {{ money(detail.final_price) }}</b>
        </div>
      </div>
    </AppModal>
  </section>
</template>
