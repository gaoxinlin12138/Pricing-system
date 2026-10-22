<script setup lang="ts">
import { reactive, ref } from 'vue'
import { api, type Session } from '../api'

const emit = defineEmits<{ (event: 'login', session: Session): void }>()

const form = reactive({ username: '', password: '' })
const error = ref('')
const busy = ref(false)

async function submit() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    const session = await api<Session>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: form.username.trim(), password: form.password }),
    })
    emit('login', session)
  } catch (exception) {
    error.value = (exception as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <section class="login-brand">
      <div>
        <p class="eyebrow">SHOWER / PRICING STUDIO</p>
        <div class="login-hero">
          <h1>让每一套<br />花洒组合<br />都有清晰答案。</h1>
          <p>内部报价工作台。管理员维护主体、配件与预设套装，员工按客户需求替换配件，系统统一核算对外售价。</p>
        </div>
      </div>
      <div class="login-foot">
        <div>
          <b>预设套装 · 报价快照</b>
          每次报价都会保存当时的配件组合，原套装保持不变。
        </div>
      </div>
    </section>

    <section class="login-panel">
      <form class="login-card" autocomplete="off" @submit.prevent="submit">
        <div class="brand">
          <span class="brand-mark">✦</span>
          <span>星瀑计价平台</span>
        </div>
        <h2>欢迎回来</h2>
        <p class="lead">登录你的工作台</p>

        <label class="field">
          <span>账号</span>
          <input v-model="form.username" class="input" name="username" autocomplete="username" required />
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="form.password" class="input" name="password" type="password" autocomplete="current-password" required />
        </label>

        <button class="btn btn-primary btn-lg btn-block" :disabled="busy">
          <span v-if="busy" class="spinner"></span>{{ busy ? '登录中…' : '进入工作台' }}
        </button>

        <p v-if="error" class="form-error">{{ error }}</p>
      </form>
    </section>
  </div>
</template>
