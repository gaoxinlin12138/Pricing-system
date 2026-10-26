<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type Session } from './api'
import AdminView from './components/AdminView.vue'
import EmployeeView from './components/EmployeeView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
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
  <div class="app-scenery app-scenery-top" aria-hidden="true">
    <svg viewBox="0 0 1600 360" preserveAspectRatio="xMidYMin slice" role="presentation">
      <defs>
        <radialGradient id="scenery-top-glow" cx="78%" cy="0%" r="70%">
          <stop offset="0" stop-color="#41bbc8" stop-opacity=".15" />
          <stop offset=".5" stop-color="#8fdde3" stop-opacity=".06" />
          <stop offset="1" stop-color="#fcf9e8" stop-opacity="0" />
        </radialGradient>
        <linearGradient id="scenery-top-plate" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#ffffff" stop-opacity=".72" />
          <stop offset=".6" stop-color="#d5eff2" stop-opacity=".32" />
          <stop offset="1" stop-color="#8fdde3" stop-opacity=".10" />
        </linearGradient>
      </defs>

      <rect width="1600" height="360" fill="url(#scenery-top-glow)" />

      <g fill="none" stroke="#41bbc8" stroke-opacity=".12">
        <ellipse cx="1270" cy="-60" rx="430" ry="300" />
        <ellipse cx="1270" cy="-60" rx="350" ry="245" />
        <ellipse cx="1270" cy="-60" rx="270" ry="190" />
      </g>

      <g fill="none" stroke="#0b5e67" stroke-opacity=".07" stroke-width="1.2">
        <path d="M-40 230 C 240 160 460 245 720 200 C 980 155 1200 215 1640 175" />
        <path d="M-40 258 C 220 190 450 275 730 228 C 990 184 1220 242 1640 205" />
        <path d="M-40 286 C 260 220 480 305 760 260 C 1020 218 1260 272 1640 236" />
      </g>

      <g transform="translate(1160 55)">
        <path d="M0 100 L190 5 L365 70 L175 170 Z" fill="url(#scenery-top-plate)" opacity=".5" />
        <path d="M0 100 L175 170 L175 190 L0 120 Z" fill="#0b5e67" opacity=".055" />
        <path d="M175 170 L365 70 L365 90 L175 190 Z" fill="#0b5e67" opacity=".04" />
        <g fill="none" stroke="#0b5e67" stroke-opacity=".08">
          <path d="M0 100 L190 5 L365 70 L175 170 Z" />
          <path d="M45 78 L235 148 M90 56 L280 126 M135 34 L325 104" />
        </g>
      </g>

      <g transform="translate(1325 40)">
        <path d="M0 58 L112 4 L218 40 L106 96 Z" fill="url(#scenery-top-plate)" opacity=".34" />
        <path d="M0 58 L106 96 L106 110 L0 72 Z" fill="#0b5e67" opacity=".04" />
        <path d="M106 96 L218 40 L218 54 L106 110 Z" fill="#0b5e67" opacity=".03" />
        <path d="M0 58 L112 4 L218 40 L106 96 Z" fill="none" stroke="#0b5e67" stroke-opacity=".08" />
      </g>

      <g fill="none" stroke="#0b5e67" stroke-opacity=".16" stroke-width="1.2">
        <path d="M300 128 v12 M294 134 h12" />
        <path d="M586 84 v8 M582 88 h8" />
        <path d="M1500 174 v9 M1495.5 178.5 h9" />
      </g>
      <circle cx="338" cy="206" r="2.2" fill="#41bbc8" opacity=".3" />
      <circle cx="1042" cy="80" r="1.8" fill="#0b5e67" opacity=".16" />
    </svg>
  </div>

  <div class="app-scenery" aria-hidden="true">
    <svg viewBox="0 0 1600 560" preserveAspectRatio="xMidYMax slice" role="presentation">
      <defs>
        <radialGradient id="scenery-glow" cx="67%" cy="84%" r="62%">
          <stop offset="0" stop-color="#41bbc8" stop-opacity=".20" />
          <stop offset=".55" stop-color="#8fdde3" stop-opacity=".09" />
          <stop offset="1" stop-color="#fcf9e8" stop-opacity="0" />
        </radialGradient>
        <linearGradient id="scenery-teal" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#41bbc8" stop-opacity=".28" />
          <stop offset="1" stop-color="#bfe3e8" stop-opacity=".03" />
        </linearGradient>
        <linearGradient id="scenery-sand" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#d8c48a" stop-opacity=".30" />
          <stop offset="1" stop-color="#fcf9e8" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="scenery-plate" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#f7fdfd" stop-opacity=".78" />
          <stop offset=".55" stop-color="#d5eff2" stop-opacity=".42" />
          <stop offset="1" stop-color="#8fdde3" stop-opacity=".18" />
        </linearGradient>
        <linearGradient id="scenery-side" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0b5e67" stop-opacity=".15" />
          <stop offset="1" stop-color="#0b5e67" stop-opacity=".02" />
        </linearGradient>
        <filter id="scenery-soft" x="-30%" y="-80%" width="160%" height="260%">
          <feGaussianBlur stdDeviation="16" />
        </filter>
      </defs>

      <rect width="1600" height="560" fill="url(#scenery-glow)" />

      <g fill="none" stroke="#41bbc8" stroke-opacity=".15" stroke-width="1.1">
        <path d="M-40 382 C 230 318 430 402 690 362 C 950 322 1120 372 1340 346 C 1460 332 1550 350 1640 335" />
        <path d="M-40 407 C 240 344 452 426 720 386 C 980 347 1150 397 1370 371 C 1480 358 1570 375 1640 361" />
        <path d="M-40 432 C 260 374 470 450 750 414 C 1010 380 1190 427 1410 402 C 1510 390 1580 406 1640 393" />
      </g>

      <path d="M-40 425 C 230 360 410 455 680 405 C 940 357 1110 415 1330 388 C 1460 373 1560 395 1640 380 L1640 600 L-40 600 Z" fill="url(#scenery-teal)" />
      <path d="M-40 470 C 230 415 430 500 710 455 C 980 412 1190 462 1640 425 L1640 600 L-40 600 Z" fill="url(#scenery-sand)" opacity=".72" />
      <path d="M-40 515 C 260 465 480 535 790 500 C 1090 466 1340 515 1640 490 L1640 600 L-40 600 Z" fill="#0b5e67" opacity=".065" />

      <g fill="none" stroke="#41bbc8">
        <ellipse cx="320" cy="430" rx="310" ry="78" stroke-opacity=".14" />
        <ellipse cx="320" cy="430" rx="250" ry="60" stroke-opacity=".11" />
        <ellipse cx="320" cy="430" rx="190" ry="43" stroke-opacity=".08" />
      </g>
      <circle cx="320" cy="430" r="3" fill="#0b5e67" opacity=".22" />
      <circle cx="86" cy="428" r="2.2" fill="#41bbc8" opacity=".34" />
      <circle cx="558" cy="456" r="2" fill="#0b5e67" opacity=".18" />

      <path d="M520 466 C 740 390 960 390 1180 466" fill="none" stroke="#0b5e67" stroke-opacity=".09" />

      <g transform="translate(1065 288)">
        <ellipse cx="215" cy="238" rx="250" ry="44" fill="#0b5e67" opacity=".07" filter="url(#scenery-soft)" />

        <path d="M0 145 L215 40 L420 112 L205 218 Z" fill="url(#scenery-plate)" opacity=".62" />
        <path d="M0 145 L205 218 L205 246 L0 173 Z" fill="url(#scenery-side)" />
        <path d="M205 218 L420 112 L420 140 L205 246 Z" fill="url(#scenery-side)" />
        <g fill="none" stroke="#0b5e67" stroke-opacity=".12">
          <path d="M43 120 L248 193 M86 99 L291 172 M129 78 L334 151 M172 57 L377 130" />
          <path d="M43 120 L86 99 M129 78 L172 57 M215 40 L258 61 M301 82 L344 103" />
        </g>

        <path d="M62 55 L277 -50 L482 22 L267 128 Z" fill="url(#scenery-plate)" opacity=".44" />
        <path d="M62 55 L267 128 L267 151 L62 78 Z" fill="url(#scenery-side)" />
        <path d="M267 128 L482 22 L482 45 L267 151 Z" fill="url(#scenery-side)" />
        <g fill="none" stroke="#0b5e67" stroke-opacity=".10">
          <path d="M105 33 L310 106 M148 11 L353 84 M191 -11 L396 62" />
          <path d="M105 33 L148 11 M191 -11 L234 -33 M277 -50 L320 -28 M363 -6 L406 16" />
        </g>

        <path d="M138 -8 L320 -100 L505 -35 L323 57 Z" fill="url(#scenery-plate)" opacity=".30" />
        <path d="M138 -8 L323 57 L323 74 L138 9 Z" fill="url(#scenery-side)" />
        <path d="M323 57 L505 -35 L505 -18 L323 74 Z" fill="url(#scenery-side)" />
        <g fill="none" stroke="#0b5e67" stroke-opacity=".10">
          <path d="M138 -8 L320 -100 L505 -35 L323 57 Z" />
          <path d="M181 -30 L363 -122 M224 -52 L406 -144 M267 -74 L449 -166" />
        </g>
      </g>

      <g fill="none" stroke="#0b5e67" stroke-opacity=".18" stroke-width="1.2">
        <path d="M176 328 v12 M170 334 h12" />
        <path d="M575 370 v8 M571 374 h8" />
        <path d="M1444 342 v10 M1439 347 h10" />
      </g>
      <circle cx="1514" cy="315" r="2.2" fill="#41bbc8" opacity=".3" />
      <circle cx="1322" cy="300" r="1.8" fill="#0b5e67" opacity=".18" />
    </svg>
  </div>

  <div class="app-layer">
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
  </div>

  <ConfirmDialog />
  <ToastStack />
</template>
