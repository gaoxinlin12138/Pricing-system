<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, imageSrc, money, roundMoney, type Accessory, type AdminBundle, type Body, type CategorySchema, type PricingSettings } from '../../api'
import { confirmDialog } from '../../ui/confirm'
import { toast } from '../../ui/toast'
import AppModal from '../AppModal.vue'
import AppSelect from '../AppSelect.vue'
import ImageField from './ImageField.vue'

const props = defineProps<{
  bundles: AdminBundle[]
  bodies: Body[]
  accessories: Accessory[]
  settings: PricingSettings
  schema: CategorySchema[]
}>()
const emit = defineEmits<{ (event: 'changed'): void }>()

interface DraftItem {
  accessory_id: number
  quantity: number
  /** 该行预置的配件类型（含“主体”） */
  category: string
}

const query = ref('')
const editing = ref(false)
const busy = ref(false)
const form = reactive<{ id: number; name: string; code: string; description: string; image_url: string; active: boolean; items: DraftItem[] }>({
  id: 0,
  name: '',
  code: '',
  description: '',
  image_url: '',
  active: true,
  items: [],
})

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.bundles
  return props.bundles.filter((bundle) => `${bundle.name} ${bundle.description} ${bundle.body?.name || ''}`.toLowerCase().includes(needle))
})

const activeBodies = computed(() => props.bodies.filter((body) => body.active !== false))

const bodyRow = computed(() => form.items.find((item) => item.category === '主体') || null)

const accessoryById = computed(() => new Map(props.accessories.map((item) => [item.id, item])))

const allCategories = computed(() => {
  const fromSchema = props.schema.map((item) => item.category)
  const fromAccessories = props.accessories.map((item) => item.category)
  // 类型顺序以产品资料表为准；“主体”也是其中一行，且排在最前。
  return Array.from(new Set([...fromSchema, ...fromAccessories])).filter(Boolean) as string[]
})

function categoryOf(accessoryId: number): string {
  return accessoryById.value.get(accessoryId)?.category || ''
}

function buildRows(selected: Array<{ accessory_id: number; quantity: number }>, bodyId = 0): DraftItem[] {
  const pool = selected.filter((item) => item.accessory_id)
  const rows: DraftItem[] = []
  for (const category of allCategories.value) {
    if (category === '主体') {
      rows.push({ accessory_id: bodyId, quantity: 1, category })
      continue
    }
    const index = pool.findIndex((item) => categoryOf(item.accessory_id) === category)
    if (index >= 0) {
      const [match] = pool.splice(index, 1)
      rows.push({ accessory_id: match.accessory_id, quantity: match.quantity, category })
    } else {
      rows.push({ accessory_id: 0, quantity: 1, category })
    }
  }
  for (const leftover of pool) {
    rows.push({ accessory_id: leftover.accessory_id, quantity: leftover.quantity, category: categoryOf(leftover.accessory_id) })
  }
  return rows
}

function optionsFor(index: number) {
  const row = form.items[index]
  const isBodyRow = row?.category === '主体'
  const chosenElsewhere = new Set(
    form.items
      .filter((item, itemIndex) => itemIndex !== index && item.accessory_id)
      .map((item) => item.accessory_id),
  )
  return props.accessories.filter((item) => {
    if (isBodyRow ? item.category !== '主体' : item.category === '主体') return false
    if (chosenElsewhere.has(item.id)) return false
    if (item.id === row?.accessory_id) return true
    if (item.active === false) return false
    if (row?.category) return item.category === row.category
    return true
  })
}

function accessoryOptions(index: number) {
  const row = form.items[index]
  const isBodyRow = row?.category === '主体'
  return optionsFor(index).map((accessory) => ({
    value: accessory.id,
    label: isBodyRow
      ? `${accessory.name} · ${accessory.model}`
      : row?.category
        ? `${accessory.name}（${accessory.model}）`
        : `${accessory.category} · ${accessory.name}（${accessory.model}）`,
    image: imageSrc(accessory.image_url),
  }))
}

const estimate = computed(() => {
  const body = props.bodies.find((item) => item.id === bodyRow.value?.accessory_id)
  const accessoryTotal = form.items.reduce((total, item) => {
    if (item.category === '主体') return total
    const accessory = accessoryById.value.get(item.accessory_id)
    return total + Number(accessory?.cost || 0) * Number(item.quantity || 0)
  }, 0)
  const subtotal = Number(body?.cost || 0) + accessoryTotal + Number(props.settings.labor_fee || 0)
  const final = subtotal * Number(props.settings.multiplier || 1)
  return { body: Number(body?.cost || 0), accessoryTotal, subtotal, final }
})

function openCreate() {
  Object.assign(form, {
    id: 0,
    name: '',
    code: '',
    description: '',
    image_url: '',
    active: true,
    items: buildRows([], activeBodies.value[0]?.id || 0),
  })
  editing.value = true
}

function openEdit(bundle: AdminBundle) {
  Object.assign(form, {
    id: bundle.id,
    name: bundle.name,
    code: bundle.code || '',
    description: bundle.description || '',
    image_url: bundle.image_url || '',
    active: bundle.active !== false,
    items: buildRows(
      (bundle.items || []).map((item) => ({ accessory_id: item.accessory.id, quantity: Number(item.quantity) })),
      bundle.body?.id || 0,
    ),
  })
  editing.value = true
}

function removeItem(index: number) {
  const row = form.items[index]
  if (row?.category === '主体') return
  if (row?.category) {
    row.accessory_id = 0
    row.quantity = 1
    return
  }
  form.items.splice(index, 1)
}

async function save() {
  if (busy.value) return
  if (!form.name.trim()) return toast('请填写套装名称', 'err')
  const bodyItem = form.items.find((item) => item.category === '主体')
  if (!bodyItem?.accessory_id) return toast('请选择主体', 'err')

  const chosen = form.items.filter((item) => item.accessory_id && item.category !== '主体')
  if (!chosen.length) return toast('至少选择一个配件，留空的行不会保存', 'err')
  if (chosen.some((item) => Number(item.quantity) < 1)) return toast('配件数量至少为 1', 'err')
  if (new Set(chosen.map((item) => item.accessory_id)).size !== chosen.length) return toast('同一个配件只能出现一次，请用数量表示用量', 'err')

  busy.value = true
  try {
    const payload = {
      name: form.name.trim(),
      code: form.code.trim(),
      description: form.description,
      image_url: form.image_url,
      body_id: bodyItem.accessory_id,
      active: form.active,
      items: chosen.map((item, index) => ({
        accessory_id: item.accessory_id,
        quantity: Number(item.quantity),
        position: index + 1,
      })),
    }
    await api(form.id ? `/api/admin/bundles/${form.id}` : '/api/admin/bundles', {
      method: form.id ? 'PATCH' : 'POST',
      body: JSON.stringify(payload),
    })
    toast(form.id ? '套装已更新' : '套装已创建', 'ok')
    editing.value = false
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}

const pendingBundleId = ref<number | null>(null)
const pendingBundleActive = ref<boolean | null>(null)

async function setActive(bundle: AdminBundle, active: boolean) {
  if (pendingBundleId.value !== null || bundle.active === active) return
  pendingBundleId.value = bundle.id
  pendingBundleActive.value = active
  try {
    await api(`/api/admin/bundles/${bundle.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: bundle.name,
        code: bundle.code || '',
        description: bundle.description || '',
        image_url: bundle.image_url || '',
        body_id: bundle.body?.id,
        active,
        items: (bundle.items || []).map((item, index) => ({
          accessory_id: item.accessory.id,
          quantity: Number(item.quantity),
          position: index + 1,
        })),
      }),
    })
    toast(`套装已${active ? '启用' : '停用'}`, 'ok')
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    pendingBundleId.value = null
    pendingBundleActive.value = null
  }
}

async function remove(bundle: AdminBundle) {
  const confirmed = await confirmDialog({
    title: '删除套装',
    message: `确定删除套装「${bundle.name}」吗？历史报价仍会保留当时的快照。`,
    confirmText: '删除',
    danger: true,
  })
  if (!confirmed) return
  try {
    await api(`/api/admin/bundles/${bundle.id}`, { method: 'DELETE' })
    toast('套装已删除', 'ok')
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
        <p class="eyebrow">PRESET BUNDLES</p>
        <h1 class="page-title">预设套装</h1>
        <p class="page-sub">自由组合「主体 + 配件」，员工端搜索到的就是这里启用的套装。</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">＋ 新增套装</button>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="search" style="max-width: 320px">
          <span class="search-icon">⌕</span>
          <input v-model="query" class="input" placeholder="搜索套装或主体" />
        </div>
        <span class="badge">{{ filtered.length }} 个套装</span>
      </div>
      <div class="card-body tight">
        <div v-if="filtered.length" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>套装</th><th>编号</th><th>主体</th><th class="num">物料</th><th class="actions">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="bundle in filtered" :key="bundle.id">
                <td>
                  <div class="product">
                    <span class="thumb">
                      <img v-if="bundle.image_url" :src="imageSrc(bundle.image_url)" :alt="bundle.name" />
                      <span v-else>✦</span>
                    </span>
                    <span class="product-main">
                      <strong>
                        {{ bundle.name }}
                        <span v-if="!bundle.image_url" class="badge warn">缺图</span>
                      </strong>
                      <small class="ellipsis">v{{ bundle.version }} · {{ bundle.description || '暂无说明' }}</small>
                    </span>
                  </div>
                </td>
                <td class="mono">{{ bundle.code || '—' }}</td>
                <td>{{ bundle.body?.name }} <span class="muted">· {{ bundle.body?.model }}</span></td>
                <td class="num">{{ (bundle.items?.length || 0) + 1 }} 件</td>
                <td class="actions">
                  <div class="row" style="justify-content: flex-end">
                    <button class="btn btn-sm" :disabled="pendingBundleId === bundle.id" @click="openEdit(bundle)">编辑</button>
                    <button
                      class="btn btn-sm"
                      :disabled="pendingBundleId === bundle.id || bundle.active"
                      :title="bundle.active ? '当前已启用' : '启用'"
                      @click="setActive(bundle, true)"
                    >
                      <span v-if="pendingBundleId === bundle.id && pendingBundleActive === true" class="spinner"></span>启用
                    </button>
                    <button
                      class="btn btn-sm"
                      :disabled="pendingBundleId === bundle.id || !bundle.active"
                      :title="!bundle.active ? '当前已停用' : '停用'"
                      @click="setActive(bundle, false)"
                    >
                      <span v-if="pendingBundleId === bundle.id && pendingBundleActive === false" class="spinner"></span>停用
                    </button>
                    <button class="btn btn-sm btn-danger" :disabled="pendingBundleId === bundle.id" @click="remove(bundle)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">
          <span class="empty-icon">✦</span>
          <strong>{{ query ? '没有匹配的套装' : '还没有预设套装' }}</strong>
          <p>{{ query ? '换个关键词试试。' : '选一个主体，再加上若干配件，就组成员工端可搜索的套装。' }}</p>
          <button v-if="!query" class="btn" @click="openCreate">＋ 创建第一个套装</button>
        </div>
      </div>
    </div>

    <AppModal v-if="editing" :title="form.id ? '编辑套装' : '新增套装'" subtitle="套装只保存组合关系；员工替换配件并保存报价时不会改动这里" wide @close="editing = false">
      <div class="bundle-editor">
        <div class="form-grid">
          <label class="field"><span>套装名称</span><input v-model="form.name" class="input" placeholder="例如：星瀑 · 恒温三件套" /></label>
          <label class="field"><span>套装编号 <small>可选</small></span><input v-model="form.code" class="input" placeholder="例如：86148T03WU2" /></label>
          <label class="field full"><span>说明 <small>可选</small></span><textarea v-model="form.description" class="input" placeholder="这套组合适合什么场景"></textarea></label>
          <div class="full"><ImageField v-model="form.image_url" label="套装成品图（用作员工端封面，一张）" /></div>
        </div>

        <div>
          <div class="row" style="justify-content: space-between; margin-bottom: 8px">
            <span class="field"><span>套装物料（BOM）</span></span>
          </div>
          <p class="page-sub" style="margin-bottom: 10px">
            已按配件类型各预置一行；主体为必选行，其它类型留空保存时会自动跳过。
          </p>

          <div class="editor-items">
            <div v-for="(item, index) in form.items" :key="index" class="editor-item">
              <span class="editor-cat" :title="item.category">{{ item.category }}</span>
              <AppSelect
                v-model="item.accessory_id"
                :options="accessoryOptions(index)"
                :menu-label="`选择${item.category}`"
                :placeholder="item.category ? `选择${item.category}` : '请选择配件'"
                :aria-label="item.category === '主体' ? '主体' : `第 ${index + 1} 行配件`"
              />
              <input
                v-model.number="item.quantity"
                class="input"
                type="number"
                min="1"
                step="1"
                aria-label="数量"
                :disabled="!item.accessory_id || item.category === '主体'"
              />
              <button
                v-if="item.category !== '主体'"
                type="button"
                class="btn btn-sm btn-ghost"
                :title="item.category ? '清空该类别' : '移除这一行'"
                :aria-label="item.category ? '清空该类别' : '移除这一行'"
                @click="removeItem(index)"
              >
                ✕
              </button>
            </div>
          </div>
        </div>

        <div class="editor-total">
          <span>
            主体 ¥{{ money(estimate.body) }} · 配件 ¥{{ money(estimate.accessoryTotal) }} · 人工 ¥{{ money(settings.labor_fee) }}
          </span>
          <span>单套预估售价 <b>¥ {{ roundMoney(estimate.final) }}</b></span>
        </div>
      </div>

      <template #footer>
        <button class="btn" type="button" @click="editing = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="save">
          <span v-if="busy" class="spinner"></span>{{ busy ? '保存中…' : '保存套装' }}
        </button>
      </template>
    </AppModal>
  </section>
</template>
