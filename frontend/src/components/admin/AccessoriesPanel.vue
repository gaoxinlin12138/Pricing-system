<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, imageSrc, money, type Accessory, type CategorySchema } from '../../api'
import { toast } from '../../ui/toast'
import AppModal from '../AppModal.vue'
import ImageField from './ImageField.vue'

const props = defineProps<{ accessories: Accessory[]; schema: CategorySchema[] }>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const query = ref('')
const categoryFilter = ref('')
const editing = ref(false)
const busy = ref(false)
const customCategory = ref('')

const form = reactive({
  id: 0,
  name: '',
  model: '',
  category: '',
  cost: 0,
  default_qty: 1,
  min_qty: 0,
  max_qty: 99,
  attributes: {} as Record<string, string>,
  image_url: '',
  active: true,
})

const categories = computed(() => {
  const fromSchema = props.schema.map((item) => item.category)
  const fromData = props.accessories.map((item) => item.category)
  return Array.from(new Set([...fromSchema, ...fromData])).sort((a, b) => a.localeCompare(b, 'zh-CN'))
})

const activeSchema = computed(() => props.schema.find((item) => item.category === form.category))

const finalCategory = computed(() => (form.category === '__custom' ? customCategory.value.trim() : form.category))

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return props.accessories.filter((item) => {
    if (categoryFilter.value && item.category !== categoryFilter.value) return false
    if (!needle) return true
    return `${item.name} ${item.model} ${item.category}`.toLowerCase().includes(needle)
  })
})

function syncAttributes() {
  const next: Record<string, string> = {}
  for (const field of activeSchema.value?.fields || []) next[field.key] = form.attributes[field.key] || ''
  form.attributes = next
}

function openCreate() {
  customCategory.value = ''
  Object.assign(form, {
    id: 0,
    name: '',
    model: '',
    category: categories.value[0] || '',
    cost: 0,
    default_qty: 1,
    min_qty: 0,
    max_qty: 99,
    attributes: {},
    image_url: '',
    active: true,
  })
  syncAttributes()
  editing.value = true
}

function openEdit(item: Accessory) {
  customCategory.value = ''
  Object.assign(form, {
    id: item.id,
    name: item.name,
    model: item.model,
    category: item.category,
    cost: Number(item.cost || 0),
    default_qty: Number(item.default_qty || 1),
    min_qty: Number(item.min_qty || 0),
    max_qty: Number(item.max_qty || 99),
    attributes: { ...(item.attributes || {}) },
    image_url: item.image_url || '',
    active: item.active !== false,
  })
  syncAttributes()
  editing.value = true
}

async function save() {
  if (busy.value) return
  if (!form.name.trim() || !form.model.trim() || !finalCategory.value) {
    toast('请填写配件名称、型号和类别', 'err')
    return
  }
  busy.value = true
  try {
    const payload = {
      name: form.name.trim(),
      model: form.model.trim(),
      category: finalCategory.value,
      attributes: form.attributes,
      image_url: form.image_url,
      cost: Number(form.cost),
      default_qty: Number(form.default_qty),
      min_qty: Number(form.min_qty),
      max_qty: Number(form.max_qty),
      active: form.active,
    }
    await api(form.id ? `/api/admin/accessories/${form.id}` : '/api/admin/accessories', {
      method: form.id ? 'PATCH' : 'POST',
      body: JSON.stringify(payload),
    })
    toast(form.id ? '配件已更新' : '配件已创建', 'ok')
    editing.value = false
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}

async function toggle(item: Accessory) {
  try {
    await api(`/api/admin/accessories/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: item.name,
        model: item.model,
        category: item.category,
        attributes: item.attributes || {},
        image_url: item.image_url || '',
        cost: Number(item.cost || 0),
        default_qty: Number(item.default_qty || 0),
        min_qty: Number(item.min_qty || 0),
        max_qty: Number(item.max_qty || 0),
        active: !item.active,
      }),
    })
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}

async function remove(item: Accessory) {
  if (!window.confirm(`确定删除配件「${item.name}」吗？仍被套装引用时无法删除。`)) return
  try {
    await api(`/api/admin/accessories/${item.id}`, { method: 'DELETE' })
    toast('配件已删除', 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">ACCESSORIES</p>
        <h1 class="page-title">配件目录</h1>
        <p class="page-sub">按类别维护配件，属性只用于展示，不参与成本计算与组合限制。</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">＋ 新增配件</button>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="row wrap grow">
          <div class="search" style="max-width: 280px">
            <span class="search-icon">⌕</span>
            <input v-model="query" class="input" placeholder="搜索配件名称或型号" />
          </div>
          <select v-model="categoryFilter" class="input" style="width: 168px">
            <option value="">全部类别</option>
            <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
          </select>
        </div>
        <span class="badge">{{ filtered.length }} 个配件</span>
      </div>
      <div class="card-body tight">
        <div v-if="filtered.length" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>配件</th><th>类别</th><th class="num">成本</th><th>数量范围</th><th>状态</th><th class="actions">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in filtered" :key="item.id">
                <td>
                  <div class="product">
                    <span class="thumb">
                      <img v-if="item.image_url" :src="imageSrc(item.image_url)" :alt="item.name" />
                      <span v-else>✧</span>
                    </span>
                    <span class="product-main">
                      <strong>{{ item.name }}</strong>
                      <small>{{ item.model }}</small>
                    </span>
                  </div>
                </td>
                <td><span class="chip">{{ item.category }}</span></td>
                <td class="num">¥ {{ money(item.cost) }}</td>
                <td class="num">{{ Number(item.min_qty) }} – {{ Number(item.max_qty) }}</td>
                <td><span class="badge" :class="item.active ? 'on' : 'off'">{{ item.active ? '启用' : '停用' }}</span></td>
                <td class="actions">
                  <div class="row" style="justify-content: flex-end">
                    <button class="btn btn-sm" @click="openEdit(item)">编辑</button>
                    <button class="btn btn-sm" @click="toggle(item)">{{ item.active ? '停用' : '启用' }}</button>
                    <button class="btn btn-sm btn-danger" @click="remove(item)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">
          <span class="empty-icon">✧</span>
          <strong>{{ query || categoryFilter ? '没有匹配的配件' : '还没有录入配件' }}</strong>
          <p>{{ query || categoryFilter ? '调整筛选条件再试。' : '配件按类别录入，套装里再用它们组合。' }}</p>
          <button v-if="!query && !categoryFilter" class="btn" @click="openCreate">＋ 新增第一个配件</button>
        </div>
      </div>
    </div>

    <AppModal v-if="editing" :title="form.id ? '编辑配件' : '新增配件'" subtitle="类别决定属性字段；同类别的配件才能在报价时互相替换" wide @close="editing = false">
      <div class="form-grid">
        <label class="field"><span>名称</span><input v-model="form.name" class="input" placeholder="例如：方形不锈钢杆" /></label>
        <label class="field"><span>型号</span><input v-model="form.model" class="input" placeholder="例如：GZ-220" /></label>
        <label class="field">
          <span>类别</span>
          <select v-model="form.category" class="input" @change="syncAttributes">
            <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
            <option value="__custom">＋ 自定义类别…</option>
          </select>
        </label>
        <label v-if="form.category === '__custom'" class="field">
          <span>新类别名称</span>
          <input v-model="customCategory" class="input" placeholder="例如：置物架" />
        </label>
        <label class="field"><span>成本（元）</span><input v-model.number="form.cost" class="input" type="number" min="0" step="0.01" /></label>
        <label class="field"><span>默认数量</span><input v-model.number="form.default_qty" class="input" type="number" min="0" step="1" /></label>
        <label class="field">
          <span>数量范围 <small>员工端可调整</small></span>
          <div class="row">
            <input v-model.number="form.min_qty" class="input" type="number" min="0" step="1" aria-label="最小数量" />
            <span class="muted">–</span>
            <input v-model.number="form.max_qty" class="input" type="number" min="0" step="1" aria-label="最大数量" />
          </div>
        </label>
        <label class="field full switch"><input v-model="form.active" type="checkbox" /> 启用（员工端可选用）</label>
        <div class="full"><ImageField v-model="form.image_url" /></div>

        <div v-if="activeSchema?.fields.length" class="full">
          <hr class="divider" />
          <p class="page-sub" style="margin-bottom: 12px">该类别的属性（只用于展示，不参与计价）</p>
          <div class="form-grid">
            <label v-for="field in activeSchema.fields" :key="field.key" class="field">
              <span>{{ field.label }} <small v-if="field.unit">{{ field.unit }}</small></span>
              <select v-if="field.type === 'select'" v-model="form.attributes[field.key]" class="input">
                <option value="">未填写</option>
                <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
              </select>
              <input v-else v-model="form.attributes[field.key]" class="input" placeholder="未填写" />
            </label>
          </div>
        </div>
      </div>

      <template #footer>
        <button class="btn" type="button" @click="editing = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="save">
          <span v-if="busy" class="spinner"></span>{{ busy ? '保存中…' : '保存配件' }}
        </button>
      </template>
    </AppModal>
  </section>
</template>
