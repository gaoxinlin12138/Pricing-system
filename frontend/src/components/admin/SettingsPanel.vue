<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { api, type PricingSettings } from '../../api'
import { toast } from '../../ui/toast'

const props = defineProps<{ settings: PricingSettings }>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const form = reactive({ ...props.settings })
const busy = ref(false)

watch(
  () => props.settings,
  (value) => Object.assign(form, value),
)

async function save() {
  if (busy.value) return
  busy.value = true
  try {
    await api('/api/admin/pricing-settings', {
      method: 'PATCH',
      body: JSON.stringify({
        multiplier: Number(form.multiplier),
        labor_fee: Number(form.labor_fee),
        tax_rate_percent: Number(form.tax_rate_percent),
        freight: Number(form.freight),
        quote_valid_days: Number(form.quote_valid_days),
        max_discount_percent: Number(form.max_discount_percent),
        minimum_price: Number(form.minimum_price),
      }),
    })
    toast('计价参数已保存', 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">PRICING SETTINGS</p>
        <h1 class="page-title">统一计价参数</h1>
        <p class="page-sub">所有套装共用同一套参数，员工端只看到最终售价。</p>
      </div>
      <button class="btn btn-primary" :disabled="busy" @click="save">
        <span v-if="busy" class="spinner"></span>{{ busy ? '保存中…' : '保存变更' }}
      </button>
    </div>

    <div class="card">
      <div class="card-body">
        <div class="settings-grid">
          <label class="field"><span>统一倍率</span><input v-model="form.multiplier" class="input" type="number" min="1" step="0.01" /></label>
          <label class="field"><span>统一人工费（元）</span><input v-model="form.labor_fee" class="input" type="number" min="0" step="1" /></label>
          <label class="field"><span>税率（%）</span><input v-model="form.tax_rate_percent" class="input" type="number" min="0" step="0.1" /></label>
          <label class="field"><span>运费（元）</span><input v-model="form.freight" class="input" type="number" min="0" step="1" /></label>
          <label class="field"><span>报价有效期（天）</span><input v-model="form.quote_valid_days" class="input" type="number" min="1" step="1" /></label>
          <label class="field"><span>最大折扣（%）</span><input v-model="form.max_discount_percent" class="input" type="number" min="0" step="1" /></label>
          <label class="field"><span>最低售价（元）</span><input v-model="form.minimum_price" class="input" type="number" min="0" step="1" /></label>
        </div>

        <div class="formula" style="margin-top: 20px">
          <b>计价公式</b>
          <span>（主体成本 + 配件成本 × 数量 + 人工费）× 倍率 → 折扣 → 加税 → 加运费 = 最终对外售价</span>
        </div>
      </div>
    </div>
  </section>
</template>
