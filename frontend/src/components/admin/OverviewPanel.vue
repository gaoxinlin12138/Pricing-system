<script setup lang="ts">
import { formatDate, money, type BundleSummary, type QuoteSummary } from '../../api'
import QuoteTrendChart from './QuoteTrendChart.vue'

defineProps<{
  bodyCount: number
  accessoryCount: number
  bundles: BundleSummary[]
  quotes: QuoteSummary[]
  userCount: number
}>()

const emit = defineEmits<{ (event: 'navigate', tab: string): void }>()

const steps = [
  { tab: '配件', title: '维护主体与配件', hint: '按类型录入主体、配件、属性与成本' },
  { tab: '套装', title: '组合预设套装', hint: '自由选择主体 + 配件，员工端即可搜索' },
]
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">OVERVIEW</p>
        <h1 class="page-title">维护工作台</h1>
        <p class="page-sub">配件（含主体）、预设套装与计价参数在这里维护；报价趋势一眼掌握。</p>
      </div>
      <button class="btn" @click="emit('navigate', '套装')">去创建套装</button>
    </div>

    <div class="metrics">
      <div class="metric">
        <span>配件</span>
        <strong>{{ accessoryCount }}</strong>
        <small class="metric-note">{{ bodyCount ? `含 ${bodyCount} 个主体` : '按类型统一维护' }}</small>
        <a href="#" @click.prevent="emit('navigate', '配件')">管理配件 →</a>
      </div>
      <div class="metric">
        <span>预设套装</span>
        <strong>{{ bundles.length }}</strong>
        <small class="metric-note">主体 + 配件组合</small>
        <a href="#" @click.prevent="emit('navigate', '套装')">管理套装 →</a>
      </div>
      <div class="metric">
        <span>报价单</span>
        <strong>{{ quotes.length }}</strong>
        <small class="metric-note">全部历史报价</small>
        <a href="#" @click.prevent="emit('navigate', '报价')">查看报价 →</a>
      </div>
      <div class="metric">
        <span>账号管理</span>
        <strong>{{ userCount }}</strong>
        <small class="metric-note">管理员与员工账号</small>
        <a href="#" @click.prevent="emit('navigate', '账号')">管理账号 →</a>
      </div>
    </div>

    <QuoteTrendChart :quotes="quotes" />

    <div class="overview-grid">
      <div class="card">
        <div class="card-head">
          <h2 class="card-title">最近报价</h2>
          <span class="badge">{{ quotes.length }} 张</span>
        </div>
        <div class="card-body tight">
          <div v-if="quotes.length" class="table-wrap">
            <table class="table">
              <thead>
                <tr><th>报价单</th><th>套装</th><th>员工</th><th class="num">售价</th></tr>
              </thead>
              <tbody>
                <tr v-for="quote in quotes.slice(0, 6)" :key="quote.quote_no">
                  <td>
                    <div class="product-main">
                      <strong class="mono">{{ quote.quote_no }}</strong>
                      <small>{{ formatDate(quote.created_at) }}</small>
                    </div>
                  </td>
                  <td>{{ quote.bundle_name || '—' }}</td>
                  <td>{{ quote.username || '—' }}</td>
                  <td class="num">¥ {{ money(quote.final_price) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty">
            <span class="empty-icon">¥</span>
            <strong>还没有报价单</strong>
            <p>员工保存报价后会出现在这里。</p>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h2 class="card-title">录入顺序</h2></div>
        <div class="card-body">
          <div class="quick-list">
            <button v-for="(step, index) in steps" :key="step.tab" class="quick-item" style="cursor: pointer; text-align: left" @click="emit('navigate', step.tab)">
              <div class="row">
                <span class="thumb" style="width: 32px; height: 32px; font-size: 13px">{{ index + 1 }}</span>
                <div>
                  <b>{{ step.title }}</b>
                  <small>{{ step.hint }}</small>
                </div>
              </div>
              <span class="muted">→</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
