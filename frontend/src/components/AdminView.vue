<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type Accessory,
  type AdminBundle,
  type AdminUser,
  type AuditLog,
  type Body,
  type CategorySchema,
  type QuoteSettings,
  type QuoteSummary,
} from '../api'
import { toast } from '../ui/toast'
import AccessoriesPanel from './admin/AccessoriesPanel.vue'
import BundlesPanel from './admin/BundlesPanel.vue'
import LogsPanel from './admin/LogsPanel.vue'
import OverviewPanel from './admin/OverviewPanel.vue'
import QuotesPanel from './admin/QuotesPanel.vue'
import UsersPanel from './admin/UsersPanel.vue'

defineProps<{ username: string }>()

const tabs = ['概览', '配件', '套装', '账号', '报价', '日志']

const tab = ref('概览')
const loading = ref(true)
const refreshing = ref(false)

const accessories = ref<Accessory[]>([])
/** 主体已并入配件表，套装编辑器仍然只需要主体列表。 */
const bodies = computed<Body[]>(() => accessories.value.filter((item) => item.category === '主体'))
const bundles = ref<AdminBundle[]>([])
const quoteRows = ref<QuoteSummary[]>([])
const users = ref<AdminUser[]>([])
const logs = ref<AuditLog[]>([])
const schema = ref<CategorySchema[]>([])
const quoteSettings = ref<QuoteSettings>({ quote_valid_days: 15 })

async function load() {
  try {
    const [quoteSettingsRow, accessoryRows, bundleRows, quoteList, userRows, logRows, schemaRows] = await Promise.all([
      api<QuoteSettings>('/api/admin/quote-settings'),
      api<Accessory[]>('/api/admin/accessories'),
      api<AdminBundle[]>('/api/admin/bundles'),
      api<QuoteSummary[]>('/api/admin/quotes'),
      api<AdminUser[]>('/api/admin/users'),
      api<AuditLog[]>('/api/admin/audit-logs'),
      api<CategorySchema[]>('/api/catalog/accessory-schema'),
    ])
    quoteSettings.value = quoteSettingsRow
    accessories.value = accessoryRows
    bundles.value = bundleRows
    quoteRows.value = quoteList
    users.value = userRows
    logs.value = logRows
    schema.value = schemaRows
  } catch (exception) {
    toast((exception as Error).message, 'err')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function refresh() {
  refreshing.value = true
  await load()
}

onMounted(load)
</script>

<template>
  <div class="admin">
    <aside class="sidebar">
      <div class="sidebar-head">
        <b>控制室</b>
        <small>ADMIN CONTROL ROOM</small>
      </div>
      <nav class="nav">
        <button v-for="item in tabs" :key="item" class="nav-item" :class="{ active: tab === item }" @click="tab = item">
          {{ item }}
        </button>
      </nav>
    </aside>

    <main class="admin-main">
      <div v-if="loading" class="stack">
        <div class="skeleton" style="height: 40px; width: 40%"></div>
        <div class="skeleton" style="height: 120px"></div>
        <div class="skeleton" style="height: 260px"></div>
      </div>

      <template v-else>
        <OverviewPanel
          v-if="tab === '概览'"
          :body-count="bodies.length"
          :accessory-count="accessories.length"
          :bundles="bundles"
          :quotes="quoteRows"
          :user-count="users.length"
          @navigate="tab = $event"
        />
        <AccessoriesPanel v-else-if="tab === '配件'" :accessories="accessories" :schema="schema" @changed="refresh" />
        <BundlesPanel v-else-if="tab === '套装'" :bundles="bundles" :bodies="bodies" :accessories="accessories" :schema="schema" @changed="refresh" />
        <UsersPanel v-else-if="tab === '账号'" :users="users" :current-user="username" @changed="refresh" />
        <QuotesPanel v-else-if="tab === '报价'" :quotes="quoteRows" :quote-valid-days="quoteSettings.quote_valid_days" @changed="refresh" />
        <LogsPanel v-else :logs="logs" />
      </template>
    </main>
  </div>
</template>
