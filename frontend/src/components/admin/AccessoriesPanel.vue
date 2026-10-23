<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, imageSrc, money, type Accessory, type CategorySchema } from '../../api'
import { confirmDialog } from '../../ui/confirm'
import { toast } from '../../ui/toast'
import AppModal from '../AppModal.vue'
import AppSelect from '../AppSelect.vue'
import ImageField from './ImageField.vue'

const props = defineProps<{ accessories: Accessory[]; schema: CategorySchema[] }>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const BODY_CATEGORY = '主体'

const query = ref('')
const searchEl = ref<HTMLInputElement | null>(null)
const selectedType = ref<string | null>(null)
const editing = ref(false)
const busy = ref(false)
const pendingId = ref<number | null>(null)

const form = reactive({
  id: 0,
  name: '',
  model: '',
  category: '',
  cost: 0,
  default_qty: 1,
  min_qty: 0,
  max_qty: 99,
  description: '',
  attributes: {} as Record<string, string>,
  image_url: '',
  active: true,
})

const isBodyForm = computed(() => form.category === BODY_CATEGORY)
const selectedIsBody = computed(() => selectedType.value === BODY_CATEGORY)

/** 类型顺序以产品资料表为准；数据里已存在的其它类别排在后面，避免历史记录丢失。 */
const categories = computed(() => {
  const fromSchema = props.schema.map((item) => item.category)
  const extras = Array.from(new Set(props.accessories.map((item) => item.category)))
    .filter((name) => !fromSchema.includes(name))
    .sort((a, b) => a.localeCompare(b, 'zh-CN'))
  return Array.from(new Set([...fromSchema, ...extras]))
})

interface AccessoryType {
  name: string
  note: string
  items: Accessory[]
  count: number
  activeCount: number
}

const types = computed<AccessoryType[]>(() => {
  const noteOf = new Map(props.schema.map((item) => [item.category, item.note || '']))
  return categories.value.map((name) => {
    const items = props.accessories.filter((item) => item.category === name)
    return {
      name,
      note: noteOf.get(name) || '',
      items,
      count: items.length,
      activeCount: items.filter((item) => item.active !== false).length,
    }
  })
})

const currentType = computed(() => types.value.find((item) => item.name === selectedType.value) || null)

const needle = computed(() => query.value.trim().toLowerCase())

function matches(item: Accessory): boolean {
  if (!needle.value) return true
  return `${item.name} ${item.model} ${item.category}`.toLowerCase().includes(needle.value)
}

const shownTypes = computed(() => {
  const base = selectedType.value === null ? types.value : types.value.filter((item) => item.name === selectedType.value)
  return base
    .map((type) => ({ ...type, visibleItems: type.items.filter(matches) }))
    .filter((type) => type.visibleItems.length > 0)
})

const visibleCount = computed(() => shownTypes.value.reduce((total, type) => total + type.visibleItems.length, 0))

const panelTitle = computed(() => selectedType.value ?? '全部主体与配件')

const unitOf = (name: string | null) => (name === BODY_CATEGORY ? '个主体' : '个配件')

const panelSub = computed(() => {
  if (needle.value) return `搜索「${query.value.trim()}」 · 找到 ${visibleCount.value} 个结果`
  if (selectedType.value === null) return `按类型分组展示，共 ${props.accessories.length} 个条目`
  const type = currentType.value
  if (!type || type.count === 0) return selectedIsBody.value ? '该类型下还没有主体' : '该类型下还没有配件'
  return `${type.count} ${unitOf(type.name)} · ${type.activeCount} 个启用`
})

const searchPlaceholder = computed(() => {
  if (selectedType.value === BODY_CATEGORY) return '搜索主体名称或型号'
  return selectedType.value ? `搜索${selectedType.value}配件` : '搜索全部主体与配件'
})

const activeSchema = computed(() => props.schema.find((item) => item.category === form.category))

const categoryOptions = computed(() => categories.value.map((name) => ({ value: name, label: name })))

function attributeOptions(field: CategorySchema['fields'][number]) {
  return (field.options || []).map((option) => ({ value: option, label: option }))
}

function appendUnit(value: string, unit?: string): string {
  const text = String(value ?? '').trim()
  if (!unit || !/^\d+(?:\.\d+)?$/.test(text)) return text
  return `${text}${unit}`
}

function fieldUnit(category: string, key: string): string | undefined {
  return props.schema.find((item) => item.category === category)?.fields.find((field) => field.key === key)?.unit
}

function attributesOf(item: Accessory): Array<[string, string]> {
  return Object.entries(item.attributes || {})
    .filter(([, value]) => String(value ?? '').trim() !== '')
    .map(([key, value]) => [key, appendUnit(String(value), fieldUnit(item.category, key))])
}

function applyUnit(field: CategorySchema['fields'][number]) {
  form.attributes[field.key] = appendUnit(form.attributes[field.key] || '', field.unit)
}

function normalizedAttributes(): Record<string, string> {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries(form.attributes)) next[key] = String(value ?? '').trim()
  for (const field of activeSchema.value?.fields || []) {
    if (field.unit) next[field.key] = appendUnit(next[field.key] || '', field.unit)
  }
  return next
}

function selectType(name: string | null) {
  selectedType.value = name
}

function syncAttributes() {
  const next: Record<string, string> = {}
  for (const field of activeSchema.value?.fields || []) next[field.key] = form.attributes[field.key] || ''
  form.attributes = next
}

function openCreate(category?: string) {
  Object.assign(form, {
    id: 0,
    name: '',
    model: '',
    category: category || selectedType.value || '',
    cost: 0,
    default_qty: 1,
    min_qty: 0,
    max_qty: 99,
    description: '',
    attributes: {},
    image_url: '',
    active: true,
  })
  syncAttributes()
  editing.value = true
}

function openEdit(item: Accessory) {
  Object.assign(form, {
    id: item.id,
    name: item.name,
    model: item.model,
    category: item.category,
    cost: Number(item.cost || 0),
    default_qty: Number(item.default_qty || 1),
    min_qty: Number(item.min_qty || 0),
    max_qty: Number(item.max_qty || 99),
    description: item.description || '',
    attributes: { ...(item.attributes || {}) },
    image_url: item.image_url || '',
    active: item.active !== false,
  })
  syncAttributes()
  editing.value = true
}

async function save() {
  if (busy.value) return
  if (!form.name.trim() || !form.model.trim() || !form.category) {
    toast('请填写名称、型号和类型', 'err')
    return
  }
  const body = form.category === BODY_CATEGORY
  busy.value = true
  try {
    const payload = {
      name: form.name.trim(),
      model: form.model.trim(),
      category: form.category,
      description: form.description.trim(),
      attributes: body ? {} : normalizedAttributes(),
      image_url: form.image_url,
      cost: Number(form.cost),
      default_qty: body ? 1 : Number(form.default_qty),
      min_qty: body ? 1 : Number(form.min_qty),
      max_qty: body ? 1 : Number(form.max_qty),
      active: form.active,
    }
    await api(form.id ? `/api/admin/accessories/${form.id}` : '/api/admin/accessories', {
      method: form.id ? 'PATCH' : 'POST',
      body: JSON.stringify(payload),
    })
    toast(form.id ? (body ? '主体已更新' : '配件已更新') : body ? '主体已创建' : '配件已创建', 'ok')
    editing.value = false
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}

const pendingActive = ref<boolean | null>(null)

async function setActive(item: Accessory, active: boolean) {
  if (pendingId.value !== null || (item.active !== false) === active) return
  const noun = item.category === BODY_CATEGORY ? '主体' : '配件'
  pendingId.value = item.id
  pendingActive.value = active
  try {
    await api(`/api/admin/accessories/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: item.name,
        model: item.model,
        category: item.category,
        description: item.description || '',
        attributes: item.attributes || {},
        image_url: item.image_url || '',
        cost: Number(item.cost || 0),
        default_qty: Number(item.default_qty || 0),
        min_qty: Number(item.min_qty || 0),
        max_qty: Number(item.max_qty || 0),
        active,
      }),
    })
    toast(`${noun}已${active ? '启用' : '停用'}`, 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    pendingId.value = null
    pendingActive.value = null
  }
}

async function remove(item: Accessory) {
  if (pendingId.value !== null) return
  const noun = item.category === BODY_CATEGORY ? '主体' : '配件'
  const confirmed = await confirmDialog({
    title: `删除${noun}`,
    message: `确定删除${noun}「${item.name}」吗？仍被套装引用时无法删除。`,
    confirmText: '删除',
    danger: true,
  })
  if (!confirmed) return
  pendingId.value = item.id
  try {
    await api(`/api/admin/accessories/${item.id}`, { method: 'DELETE' })
    toast(`${noun}已删除`, 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    pendingId.value = null
  }
}

function focusSearch(event: KeyboardEvent) {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return
  const target = event.target as HTMLElement | null
  if (target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) return
  if (document.querySelector('.modal-mask')) return
  event.preventDefault()
  searchEl.value?.focus()
}

onMounted(() => window.addEventListener('keydown', focusSearch))
onBeforeUnmount(() => window.removeEventListener('keydown', focusSearch))
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">CATALOG</p>
        <h1 class="page-title">配件目录</h1>
        <p class="page-sub">按类型浏览主体与配件，属性只用于展示，不参与成本计算与组合限制。</p>
      </div>
      <button class="btn btn-primary" @click="openCreate()">{{ selectedIsBody ? '＋ 新增主体' : '＋ 新增配件' }}</button>
    </div>

    <div class="catalog">
      <aside class="card catalog-types" aria-label="类型导航">
        <div class="catalog-types-head">
          <span>类型</span>
          <small>{{ categories.length }} 类</small>
        </div>
        <nav class="type-list">
          <button
            class="type-item"
            :class="{ active: selectedType === null }"
            :aria-current="selectedType === null ? 'true' : undefined"
            @click="selectType(null)"
          >
            <span class="type-glyph" aria-hidden="true">全</span>
            <span class="type-name">全部</span>
            <span class="type-count num">{{ accessories.length }}</span>
          </button>
          <span class="type-divider" aria-hidden="true"></span>
          <button
            v-for="type in types"
            :key="type.name"
            class="type-item"
            :class="{ active: selectedType === type.name }"
            :aria-current="selectedType === type.name ? 'true' : undefined"
            :title="type.note || type.name"
            @click="selectType(type.name)"
          >
            <span class="type-glyph" aria-hidden="true">{{ type.name.slice(0, 1) }}</span>
            <span class="type-name">{{ type.name }}</span>
            <span class="type-count num">{{ type.count }}</span>
          </button>
        </nav>
      </aside>

      <section class="card catalog-detail">
        <header class="catalog-head">
          <div class="catalog-heading">
            <h2 class="catalog-title">{{ panelTitle }}</h2>
            <p v-if="selectedType && currentType?.note" class="catalog-note">{{ currentType.note }}</p>
            <p class="catalog-sub">{{ panelSub }}</p>
          </div>
          <div class="catalog-tools">
            <div class="search catalog-search">
              <span class="search-icon" aria-hidden="true">⌕</span>
              <input
                ref="searchEl"
                v-model="query"
                class="input"
                type="text"
                :placeholder="searchPlaceholder"
                aria-label="搜索主体或配件名称、型号"
                @keydown.esc="query = ''"
              />
            </div>
          </div>
        </header>

        <div v-if="visibleCount" class="acc-groups">
          <section v-for="group in shownTypes" :key="group.name" class="acc-group">
            <header v-if="selectedType === null" class="acc-group-head">
              <span class="acc-group-mark" aria-hidden="true"></span>
              <h3>{{ group.name }}</h3>
              <span class="acc-group-count num">{{ group.visibleItems.length }}</span>
            </header>
            <div class="acc-list">
              <article v-for="item in group.visibleItems" :key="item.id" class="acc-item">
                <span class="acc-thumb">
                  <img v-if="item.image_url" :src="imageSrc(item.image_url)" :alt="item.name" />
                  <span v-else aria-hidden="true">✧</span>
                </span>
                <div class="acc-main">
                  <div class="acc-title">
                    <strong>{{ item.name }}</strong>
                  </div>
                  <p class="acc-model mono">{{ item.model }}</p>
                  <p v-if="item.description" class="acc-desc">{{ item.description }}</p>
                  <div v-if="attributesOf(item).length" class="attrs">
                    <span v-for="[key, value] in attributesOf(item)" :key="key" class="attr">
                      <span class="attr-key">{{ key }}</span>
                      <span>{{ value }}</span>
                    </span>
                  </div>
                </div>
                <dl class="acc-meta">
                  <div>
                    <dt>成本</dt>
                    <dd class="num">¥ {{ money(item.cost) }}</dd>
                  </div>
                  <div v-if="item.category !== BODY_CATEGORY">
                    <dt>数量范围</dt>
                    <dd class="num">{{ Number(item.min_qty) }} – {{ Number(item.max_qty) }}</dd>
                  </div>
                </dl>
                <div class="acc-actions">
                  <button class="btn btn-sm" :disabled="pendingId === item.id" @click="openEdit(item)">编辑</button>
                  <button
                    class="btn btn-sm"
                    :disabled="pendingId === item.id || item.active !== false"
                    :title="item.active !== false ? '当前已启用' : '启用'"
                    @click="setActive(item, true)"
                  >
                    <span v-if="pendingId === item.id && pendingActive === true" class="spinner"></span>启用
                  </button>
                  <button
                    class="btn btn-sm"
                    :disabled="pendingId === item.id || item.active === false"
                    :title="item.active === false ? '当前已停用' : '停用'"
                    @click="setActive(item, false)"
                  >
                    <span v-if="pendingId === item.id && pendingActive === false" class="spinner"></span>停用
                  </button>
                  <button class="btn btn-sm btn-danger" :disabled="pendingId === item.id" @click="remove(item)">删除</button>
                </div>
              </article>
            </div>
          </section>
        </div>

        <div v-else class="empty">
          <span class="empty-icon" aria-hidden="true">✧</span>
          <template v-if="query">
            <strong>没有匹配的结果</strong>
            <p>没有找到包含「{{ query }}」的主体或配件，换个关键词再试。</p>
            <button class="btn" @click="query = ''">清空搜索</button>
          </template>
          <template v-else-if="selectedIsBody">
            <strong>还没有录入主体</strong>
            <p>主体是套装的基础，录入后就能在套装里选择。</p>
            <button class="btn btn-primary" @click="openCreate(BODY_CATEGORY)">＋ 新增主体</button>
          </template>
          <template v-else-if="selectedType">
            <strong>「{{ selectedType }}」还没有配件</strong>
            <p>添加后，员工端才能在套装里选用这一类型。</p>
            <button class="btn btn-primary" @click="openCreate(selectedType)">＋ 新增{{ selectedType }}配件</button>
          </template>
          <template v-else>
            <strong>还没有录入主体或配件</strong>
            <p>主体与配件都按类型录入，套装里再用它们组合。</p>
            <button class="btn btn-primary" @click="openCreate()">＋ 新增第一条记录</button>
          </template>
        </div>
      </section>
    </div>

    <AppModal
      v-if="editing"
      :title="form.id ? (isBodyForm ? '编辑主体' : '编辑配件') : isBodyForm ? '新增主体' : '新增配件'"
      :subtitle="isBodyForm ? '主体是套装的基础，每套固定选一个' : '类型决定属性字段；同一类型的配件才能在报价时互相替换'"
      wide
      @close="editing = false"
    >
      <div class="form-grid">
        <label class="field"><span>名称</span><input v-model="form.name" class="input" :placeholder="isBodyForm ? '例如：星瀑花洒主体' : '例如：方形不锈钢杆'" /></label>
        <label class="field"><span>型号</span><input v-model="form.model" class="input" :placeholder="isBodyForm ? '例如：SH-001' : '例如：GZ-220'" /></label>
        <label class="field">
          <span>类型</span>
          <AppSelect
            v-model="form.category"
            :options="categoryOptions"
            placeholder="请选择类型"
            aria-label="类型"
            @change="syncAttributes"
          />
        </label>
        <label class="field"><span>成本（元）</span><input v-model.number="form.cost" class="input" type="number" min="0" step="0.01" /></label>
        <label v-if="!isBodyForm" class="field"><span>默认数量</span><input v-model.number="form.default_qty" class="input" type="number" min="0" step="1" /></label>
        <label v-if="!isBodyForm" class="field">
          <span>数量范围 <small>员工端可调整</small></span>
          <div class="row">
            <input v-model.number="form.min_qty" class="input" type="number" min="0" step="1" aria-label="最小数量" />
            <span class="muted">–</span>
            <input v-model.number="form.max_qty" class="input" type="number" min="0" step="1" aria-label="最大数量" />
          </div>
        </label>
        <label v-if="isBodyForm" class="field full">
          <span>描述 <small>显示在套装与员工端</small></span>
          <textarea v-model="form.description" class="input" placeholder="材质、适配场景等"></textarea>
        </label>
        <div class="full"><ImageField v-model="form.image_url" /></div>

        <div v-if="activeSchema?.fields.length" class="full">
          <hr class="divider" />
          <p class="page-sub" style="margin-bottom: 12px">该类型的属性（只用于展示，不参与计价）</p>
          <div class="form-grid">
            <label v-for="field in activeSchema.fields" :key="field.key" class="field">
              <span>{{ field.label }} <small v-if="field.unit">{{ field.unit }}</small></span>
              <AppSelect
                v-if="field.type === 'select'"
                v-model="form.attributes[field.key]"
                :options="attributeOptions(field)"
                placeholder="请选择"
                :aria-label="field.label"
                clearable
              />
              <input v-else v-model="form.attributes[field.key]" class="input" placeholder="选填" @blur="applyUnit(field)" />
            </label>
          </div>
        </div>
      </div>

      <template #footer>
        <button class="btn" type="button" @click="editing = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="save">
          <span v-if="busy" class="spinner"></span>{{ busy ? '保存中…' : isBodyForm ? '保存主体' : '保存配件' }}
        </button>
      </template>
    </AppModal>
  </section>
</template>
