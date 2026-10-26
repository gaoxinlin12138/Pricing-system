<script setup lang="ts">
import { reactive, ref } from 'vue'
import { api, formatDate, type AdminUser } from '../../api'
import { confirmDialog } from '../../ui/confirm'
import { toast } from '../../ui/toast'
import AppModal from '../AppModal.vue'
import AppSelect from '../AppSelect.vue'

const props = defineProps<{ users: AdminUser[]; currentUser: string }>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const roleOptions = [
  { value: 'employee', label: '员工' },
  { value: 'admin', label: '管理员' },
]

const editing = ref(false)
const busy = ref(false)
const editingCurrentUser = ref(false)
const form = reactive({ id: 0, username: '', password: '', role: 'employee' as 'admin' | 'employee', active: true })

function openCreate() {
  Object.assign(form, { id: 0, username: '', password: '', role: 'employee', active: true })
  editingCurrentUser.value = false
  editing.value = true
}

function openEdit(user: AdminUser) {
  Object.assign(form, { id: user.id, username: user.username, password: '', role: user.role, active: user.active })
  editingCurrentUser.value = user.username === props.currentUser
  editing.value = true
}

async function save() {
  if (busy.value) return
  if (form.username.trim().length < 3) return toast('账号至少 3 个字符', 'err')
  if (editingCurrentUser.value && (form.role !== 'admin' || !form.active)) return toast('当前登录账号必须保持管理员且启用', 'err')
  if (!form.id && form.password.length < 8) return toast('新账号密码至少 8 位', 'err')
  if (form.id && form.password && form.password.length < 8) return toast('密码至少 8 位', 'err')
  busy.value = true
  try {
    await api(form.id ? `/api/admin/users/${form.id}` : '/api/admin/users', {
      method: form.id ? 'PATCH' : 'POST',
      body: JSON.stringify({
        username: form.username.trim(),
        password: form.password || null,
        role: form.role,
        active: form.active,
      }),
    })
    toast(form.id ? '账号已更新' : '账号已创建', 'ok')
    editing.value = false
    emit('changed')
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    busy.value = false
  }
}

async function remove(user: AdminUser) {
  const confirmed = await confirmDialog({
    title: '删除账号',
    message: `确定删除账号「${user.username}」吗？该账号的报价记录会保留用户名快照。`,
    confirmText: '删除',
    danger: true,
  })
  if (!confirmed) return
  try {
    await api(`/api/admin/users/${user.id}`, { method: 'DELETE' })
    toast('账号已删除', 'ok')
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
        <p class="eyebrow">ACCOUNTS</p>
        <h1 class="page-title">账号管理</h1>
        <p class="page-sub">管理员维护目录和参数，员工只能搜索套装、替换主体或配件并保存报价。</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">＋ 新增账号</button>
    </div>

    <div class="card">
      <div class="card-body tight">
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>账号</th><th>角色</th><th>状态</th><th>最近登录</th><th class="actions">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="user in props.users" :key="user.id">
                <td>
                  <div class="product">
                    <span class="thumb" style="width: 32px; height: 32px; font-size: 12px">{{ user.username.slice(0, 1).toUpperCase() }}</span>
                    <span class="product-main">
                      <strong>{{ user.username }}</strong>
                      <small v-if="user.username === props.currentUser">当前登录</small>
                    </span>
                  </div>
                </td>
                <td><span class="badge" :class="user.role === 'admin' ? '' : 'off'">{{ user.role === 'admin' ? '管理员' : '员工' }}</span></td>
                <td><span class="badge" :class="user.active ? 'on' : 'off'">{{ user.active ? '启用' : '停用' }}</span></td>
                <td class="muted">{{ formatDate(user.last_login) }}</td>
                <td class="actions">
                  <div class="row" style="justify-content: flex-end">
                    <button class="btn btn-sm" @click="openEdit(user)">编辑</button>
                    <button class="btn btn-sm btn-danger" :disabled="user.username === props.currentUser" @click="remove(user)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <AppModal v-if="editing" :title="form.id ? '编辑账号' : '新增账号'" :subtitle="form.id ? '密码留空表示不修改' : '新账号必须设置不少于 8 位的密码'" @close="editing = false">
      <div class="form-grid">
        <label class="field"><span>账号</span><input v-model="form.username" class="input" autocomplete="off" /></label>
        <label class="field"><span>密码 <small v-if="form.id">留空不修改</small></span><input v-model="form.password" class="input" type="password" autocomplete="new-password" /></label>
        <label class="field">
          <span>角色 <small v-if="editingCurrentUser">当前登录账号不可降级</small></span>
          <AppSelect v-model="form.role" :options="roleOptions" :disabled="editingCurrentUser" placeholder="请选择角色" aria-label="角色" />
        </label>
        <label class="field switch" style="align-self: end; padding-bottom: 8px"><input v-model="form.active" type="checkbox" :disabled="editingCurrentUser" /> 启用</label>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="editing = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="save">
          <span v-if="busy" class="spinner"></span>{{ busy ? '保存中…' : '保存账号' }}
        </button>
      </template>
    </AppModal>
  </section>
</template>
