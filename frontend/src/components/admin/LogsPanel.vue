<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatDate, type AuditLog } from '../../api'
import AppModal from '../AppModal.vue'

const props = defineProps<{ logs: AuditLog[] }>()

const query = ref('')
const selected = ref<AuditLog | null>(null)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.logs
  return props.logs.filter((log) => `${log.username} ${log.action_label} ${log.target_type_label} ${log.target_label || ''}`.toLowerCase().includes(needle))
})
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <p class="eyebrow">AUDIT LOG</p>
        <h1 class="page-title">操作日志</h1>
        <p class="page-sub">最近 200 条操作记录，包含创建、修改、删除和报价替换。</p>
      </div>
      <span class="badge">{{ props.logs.length }} 条</span>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="search" style="max-width: 320px">
          <span class="search-icon">⌕</span>
          <input v-model="query" class="input" placeholder="搜索操作人、动作或对象" />
        </div>
      </div>
      <div class="card-body tight">
        <div v-if="filtered.length" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th class="actions">详情</th></tr>
            </thead>
            <tbody>
              <tr v-for="log in filtered" :key="log.id">
                <td class="muted nowrap">{{ formatDate(log.created_at) }}</td>
                <td>{{ log.username }}</td>
                <td><span class="badge">{{ log.action_label }}</span></td>
                <td>
                  {{ log.target_type_label }}
                  <span class="muted">· {{ log.target_label || log.target_id }}</span>
                  <span v-if="log.target_deleted" class="badge off" style="margin-left: 6px">已删除</span>
                </td>
                <td class="actions"><button class="btn btn-sm" @click="selected = log">查看</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">
          <span class="empty-icon">≡</span>
          <strong>没有匹配的日志</strong>
          <p>换个关键词试试，或清空搜索条件。</p>
        </div>
      </div>
    </div>

    <AppModal v-if="selected" :title="`${selected.action_label} · ${selected.target_type_label}`" :subtitle="`${selected.username} · ${formatDate(selected.created_at)}`" @close="selected = null">
      <pre class="mono" style="margin: 0; white-space: pre-wrap; word-break: break-all; background: #f6f9f9; border: 1px solid var(--line); border-radius: 8px; padding: 12px">{{ JSON.stringify(selected.detail, null, 2) }}</pre>
    </AppModal>
  </section>
</template>
