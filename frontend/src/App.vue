<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type Session } from './api'
import AdminView from './components/AdminView.vue'
import EmployeeView from './components/EmployeeView.vue'
import LoginView from './components/LoginView.vue'
import ToastStack from './components/ToastStack.vue'
import { toast } from './ui/toast'

const session = ref<Session | null>(null)
const booting = ref(true)

function onSessionExpired() {
  if (!session.value) return
  session.value = null
  toast('登录已过期，请重新登录', 'err')
}

onMounted(async () => {
  window.addEventListener('pricing:session-expired', onSessionExpired)
  try {
    session.value = await api<Session>('/api/auth/me')
  } catch {
    session.value = null
  } finally {
    booting.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('pricing:session-expired', onSessionExpired)
})

function onLogin(value: Session) {
  session.value = value
}

async function logout() {
  try {
    await api('/api/auth/logout', { method: 'POST' })
  } catch {
    /* 退出失败也让界面回到登录页 */
  }
  session.value = null
}
</script>

<template>
  <div v-if="booting" class="boot">正在进入工作台…</div>

  <LoginView v-else-if="!session" @login="onLogin" />

  <div v-else>
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span class="brand-mark">✦</span>
          <span>星瀑计价平台</span>
        </div>
        <div class="topbar-right">
          <span class="role-chip">{{ session.role === 'admin' ? '管理员' : '员工' }}</span>
          <b>{{ session.username }}</b>
          <button class="btn btn-sm btn-ghost" @click="logout">退出登录</button>
        </div>
      </div>
    </header>

    <AdminView v-if="session.role === 'admin'" :username="session.username" />
    <EmployeeView v-else />
  </div>

  <ToastStack />
</template>
