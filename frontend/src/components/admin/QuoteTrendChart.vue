<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { QuoteSummary } from '../../api'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ quotes: QuoteSummary[] }>()

type RangeKey = '14d' | '6m' | '12m'
type Bucket = { key: string; label: string; count: number; amount: number }

const rangeOptions: Array<{ value: RangeKey; label: string }> = [
  { value: '14d', label: '14 天' },
  { value: '6m', label: '6 个月' },
  { value: '12m', label: '12 个月' },
]
const range = ref<RangeKey>('14d')

const chartEl = ref<HTMLDivElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let observer: ResizeObserver | null = null

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function dateKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function monthKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`
}

function formatAmount(value: number): string {
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const rangeLabel = computed(() => {
  if (range.value === '14d') return '近 14 天'
  if (range.value === '6m') return '近 6 个月'
  return '近 12 个月'
})

const periodLabel = computed(() => (range.value === '14d' ? '当日' : '当月'))

const chartData = computed<Bucket[]>(() => {
  const now = new Date()
  let rows: Bucket[]
  if (range.value === '14d') {
    const today = new Date(now)
    today.setHours(0, 0, 0, 0)
    rows = Array.from({ length: 14 }, (_, index) => {
      const date = new Date(today)
      date.setDate(today.getDate() - (13 - index))
      return {
        key: dateKey(date),
        label: `${date.getMonth() + 1}-${pad(date.getDate())}`,
        count: 0,
        amount: 0,
      }
    })
  } else {
    const months = range.value === '6m' ? 6 : 12
    const start = new Date(now.getFullYear(), now.getMonth() - (months - 1), 1)
    rows = Array.from({ length: months }, (_, index) => {
      const date = new Date(start.getFullYear(), start.getMonth() + index, 1)
      return {
        key: monthKey(date),
        label: monthKey(date),
        count: 0,
        amount: 0,
      }
    })
  }

  const byKey = new Map(rows.map((row) => [row.key, row]))
  for (const quote of props.quotes) {
    if (quote.status === 'void') continue
    const created = new Date(quote.created_at)
    if (Number.isNaN(created.getTime())) continue
    const key = range.value === '14d' ? dateKey(created) : monthKey(created)
    const row = byKey.get(key)
    if (!row) continue
    row.count += 1
    row.amount += Number(quote.final_price) || 0
  }
  return rows
})

const totalCount = computed(() => chartData.value.reduce((total, row) => total + row.count, 0))
const totalAmount = computed(() => chartData.value.reduce((total, row) => total + row.amount, 0))
const hasData = computed(() => totalCount.value > 0)
const emptyTitle = computed(() => (props.quotes.length ? `${rangeLabel.value}暂无报价` : '暂无报价趋势'))
const emptyHint = computed(() =>
  props.quotes.length ? '更早的报价仍保留在报价记录里。' : '员工保存报价后，这里会显示累计金额趋势。',
)

function render() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const rows = chartData.value
  const showChart = hasData.value
  let running = 0
  const cumulative = rows.map((row) => {
    running += row.amount
    return Number(running.toFixed(2))
  })
  chart.setOption(
    {
      animationDuration: 600,
      grid: { left: 10, right: 18, top: 24, bottom: 10, containLabel: true },
      tooltip: {
        show: showChart,
        trigger: 'axis',
        backgroundColor: '#fffdf7',
        borderColor: '#e7e1cf',
        borderWidth: 1,
        padding: [10, 12],
        extraCssText: 'box-shadow: 0 8px 24px rgba(74,64,34,.12); border-radius: 10px;',
        textStyle: { color: '#17323a', fontSize: 12 },
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params]
          const point = list[0] as { dataIndex: number } | undefined
          if (!point) return ''
          const row = rows[point.dataIndex]
          return `<div style="min-width:146px">
            <div style="font-weight:600;margin-bottom:6px">${row.label}</div>
            <div style="display:flex;justify-content:space-between;gap:16px"><span style="color:#64756f">${periodLabel.value}报价</span><b>${row.count} 张</b></div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-top:2px"><span style="color:#64756f">${periodLabel.value}金额</span><b>¥ ${formatAmount(row.amount)}</b></div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-top:2px"><span style="color:#64756f">累计金额</span><b>¥ ${formatAmount(cumulative[point.dataIndex])}</b></div>
          </div>`
        },
      },
      xAxis: {
        show: showChart,
        type: 'category',
        boundaryGap: false,
        data: rows.map((row) => row.label),
        axisLine: { lineStyle: { color: '#e7e1cf' } },
        axisTick: { show: false },
        axisLabel: { color: '#8a8a7a', fontSize: 11, hideOverlap: true },
      },
      yAxis: {
        show: showChart,
        type: 'value',
        min: 0,
        splitNumber: 4,
        axisLabel: {
          color: '#8a8a7a',
          fontSize: 11,
          formatter: (value: number) => `¥${Number(value).toLocaleString('zh-CN')}`,
        },
        splitLine: { lineStyle: { color: '#efe9d8', type: 'dashed' } },
      },
      series: [
        {
          name: '累计报价金额',
          type: 'line',
          data: showChart ? cumulative : [],
          smooth: 0.38,
          showSymbol: false,
          symbol: 'circle',
          symbolSize: 7,
          lineStyle: {
            width: 2.6,
            color: '#2fa9b6',
            shadowColor: 'rgba(65,187,200,0.24)',
            shadowBlur: 12,
            shadowOffsetY: 6,
          },
          itemStyle: { color: '#2fa9b6', borderColor: '#fff', borderWidth: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(65,187,200,0.40)' },
                { offset: 1, color: 'rgba(65,187,200,0.02)' },
              ],
            },
          },
          emphasis: { focus: 'series' },
        },
      ],
    },
    true,
  )
}

watch([() => props.quotes, range], () => render(), { deep: true })

onMounted(() => {
  render()
  if (chartEl.value) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(chartEl.value)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="card overview-chart">
    <div class="card-head chart-head">
      <div>
        <h2 class="card-title">报价趋势</h2>
        <p class="chart-sub">{{ rangeLabel }} · 累计报价金额</p>
      </div>
      <div class="chart-tools">
        <div class="chart-range" role="group" aria-label="报价趋势时间范围">
          <button
            v-for="option in rangeOptions"
            :key="option.value"
            type="button"
            class="chart-range-btn"
            :class="{ active: range === option.value }"
            :aria-pressed="range === option.value"
            @click="range = option.value"
          >
            {{ option.label }}
          </button>
        </div>
        <span class="badge" title="已排除作废报价">{{ totalCount }} 张 · ¥ {{ formatAmount(totalAmount) }}</span>
      </div>
    </div>
    <div class="chart-wrap">
      <div
        ref="chartEl"
        class="quote-chart"
        role="img"
        :aria-label="`${rangeLabel}累计报价金额，共 ${totalCount} 张报价单，合计 ${formatAmount(totalAmount)} 元`"
      ></div>
      <div v-if="!hasData" class="chart-empty">
        <span class="chart-empty-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 18.5l5-5 3.2 3.2L20 8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M4 20.5h16" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity=".45" />
          </svg>
        </span>
        <strong>{{ emptyTitle }}</strong>
        <p>{{ emptyHint }}</p>
      </div>
    </div>
  </div>
</template>
