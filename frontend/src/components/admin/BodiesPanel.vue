<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, imageSrc, money, type Body } from '../../api'
import { toast } from '../../ui/toast'
import AppModal from '../AppModal.vue'
import ImageField from './ImageField.vue'

const props = defineProps<{ bodies: Body[] }>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const query = ref('')
const editing = ref(false)
const busy = ref(false)
const form = reactive({ id: 0, name: '', model: '', cost: 0, description: '', image_url: '', active: true })

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.bodies
  return props.bodies.filter((body) => `${body.name} ${body.model} ${body.description}`.toLowerCase().includes(needle))
})

function openCreate() {
  Object.assign(form, { id: 0, name: '', model: '', cost: 0, description: '', image_url: '', active: true })
  editing.value = true
}

function openEdit(body: Body) {
  Object.assign(form, {
    id: body.id,
    name: body.name,
    model: body.model,
    cost: Number(body.cost || 0),
    description: body.description || '',
    image_url: body.image_url || '',
    active: body.active !== false,
  })
  editing.value = true
}

async function save() {
  if (busy.value) return
  if (!form.name.trim() || !form.model.trim()) {
    toast('请填写主体名称和型号', 'err')
    return
  }
  busy.value = true
  try {
    const payload = {
      name: form.name.trim(),
      model: form.model.trim(),
      description: form.description,
      image_url: form.image_url,
      cost: Number(form.cost),
      active: form.active,
    }
    await api(form.id ? `/api/admin/bodies/${form.id}` : '/api/admin/bodies', {
      method: form.id ? 'PATCH' : 'POST',
      body: JSON.stringify(payload),
    })
    toast(form.id ? '主体已更新' : '主体已创建', 'ok')
    editing.value = false
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}

async function toggle(body: Body) {
  try {
    await api(`/api/admin/bodies/${body.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: body.name,
        model: body.model,
        description: body.description || '',
        image_url: body.image_url || '',
        cost: Number(body.cost || 0),
        active: !body.active,
      }),
    })
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  }
}

async function remove(body: Body) {
  if (!window.confirm(`确定删除主体「${body.name}」吗？仍被套装引用时无法删除。`)) return
  try {
    await api(`/api/admin/bodies/${body.id}`, { method: 'DELETE' })
    toast('主体已删除', 'ok')
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
        <p class="eyebrow">BODIES</p>
        <h1 class="page-title">主体目录</h1>
        <p class="page-sub">主体是套装的基础，只有一个成本价，不参与配件间的限制。</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">＋ 新增主体</button>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="search" style="max-width: 320px">
          <span class="search-icon">⌕</span>
          <input v-model="query" class="input" placeholder="搜索主体名称或型号" />
        </div>
        <span class="badge">{{ filtered.length }} 个主体</span>
      </div>
      <div class="card-body tight">
        <div v-if="filtered.length" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>主体</th><th>型号</th><th class="num">成本</th><th>状态</th><th class="actions">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="body in filtered" :key="body.id">
                <td>
                  <div class="product">
                    <span class="thumb">
                      <img v-if="body.image_url" :src="imageSrc(body.image_url)" :alt="body.name" />
                      <span v-else>◈</span>
                    </span>
                    <span class="product-main">
                      <strong>{{ body.name }}</strong>
                      <small class="ellipsis">{{ body.description || '暂无描述' }}</small>
                    </span>
                  </div>
                </td>
                <td class="mono">{{ body.model }}</td>
                <td class="num">¥ {{ money(body.cost) }}</td>
                <td><span class="badge" :class="body.active ? 'on' : 'off'">{{ body.active ? '启用' : '停用' }}</span></td>
                <td class="actions">
                  <div class="row" style="justify-content: flex-end">
                    <button class="btn btn-sm" @click="openEdit(body)">编辑</button>
                    <button class="btn btn-sm" @click="toggle(body)">{{ body.active ? '停用' : '启用' }}</button>
                    <button class="btn btn-sm btn-danger" @click="remove(body)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">
          <span class="empty-icon">◈</span>
          <strong>{{ query ? '没有匹配的主体' : '还没有录入主体' }}</strong>
          <p>{{ query ? '换个关键词试试。' : '先录入花洒主体，之后才能在套装里组合。' }}</p>
          <button v-if="!query" class="btn" @click="openCreate">＋ 新增第一个主体</button>
        </div>
      </div>
    </div>

    <AppModal v-if="editing" :title="form.id ? '编辑主体' : '新增主体'" subtitle="主体只有成本价，不参与配件互斥或依赖判断" @close="editing = false">
      <div class="form-grid">
        <label class="field"><span>名称</span><input v-model="form.name" class="input" placeholder="例如：星瀑花洒主体" /></label>
        <label class="field"><span>型号</span><input v-model="form.model" class="input" placeholder="例如：SH-001" /></label>
        <label class="field"><span>成本（元）</span><input v-model.number="form.cost" class="input" type="number" min="0" step="0.01" /></label>
        <label class="field switch" style="align-self: end; padding-bottom: 8px">
          <input v-model="form.active" type="checkbox" /> 启用（员工端可见）
        </label>
        <label class="field full"><span>描述 <small>可选</small></span><textarea v-model="form.description" class="input" placeholder="材质、适配场景等"></textarea></label>
        <div class="full"><ImageField v-model="form.image_url" /></div>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="editing = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="save">
          <span v-if="busy" class="spinner"></span>{{ busy ? '保存中…' : '保存主体' }}
        </button>
      </template>
    </AppModal>
  </section>
</template>
