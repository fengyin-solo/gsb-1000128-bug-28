<template>
  <section class="page detail-page" data-module="sample_storage-detail">
    <header class="page-head">
      <div>
        <h2>留存样品详情</h2>
        <p class="page-desc">详情页只展示服务端统一后的状态，可执行动作与列表页、处理入口共用同一判断。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/sample_storage">返回列表</RouterLink>
        <RouterLink class="btn primary" :to="processPath">进入处理入口</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-else-if="entry">
      <div class="detail-grid">
        <article v-for="field in detailFields" :key="field" class="detail-item">
          <span>{{ field }}</span>
          <strong>{{ entry[field] ?? '—' }}</strong>
        </article>
      </div>

      <section class="decision-panel">
        <h3>处理动作</h3>
        <div v-for="action in actions" :key="action" class="decision-row">
          <button
            class="btn"
            type="button"
            :disabled="!decisionOf(action).available || isActionInflight(action, [entryId])"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
          <span :class="decisionOf(action).kind === 'conflict' ? 'error-text' : 'hint-text'">
            {{ decisionOf(action).reason || '当前可执行；执行后状态将变为「' + targetStatus(action) + '」' }}
          </span>
        </div>
        <p v-if="statusMessage" :class="messageClass">{{ statusMessage }}</p>
      </section>

      <section v-if="history.length" class="history-panel">
        <h3>处理记录</h3>
        <ul>
          <li v-for="(item, index) in history" :key="`${item.at}-${index}`">
            {{ item.at }} · {{ item.action }} · {{ item.status }}
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { fetchJson } from '@/api/client'
import { isActionInflight, submitStorageAction } from './actions'
import {
  ACTIONS,
  TARGET_STATUS,
  getActionDecision,
  type StorageAction,
  type StorageRow,
} from './rules'

interface HistoryItem {
  action: string
  status: string
  at: string
}

const route = useRoute()
const actions = ACTIONS
const detailFields = ['留存编号', '样品编号', '留存位置', '留存期限', '到期日期', '保管人员', '处理方式', '留存状态']
const entry = ref<StorageRow | null>(null)
const errorMessage = ref('')
const statusMessage = ref('')
const messageKind = ref<'error' | 'success'>('error')

const entryId = computed(() => Number(route.params.id))
const processPath = computed(() => ({ path: '/sample_storage/process', query: { id: String(entryId.value) } }))
const messageClass = computed(() => (messageKind.value === 'error' ? 'error-text' : 'success-text'))
const history = computed<HistoryItem[]>(() => {
  const value = entry.value?.action_history
  return Array.isArray(value) ? (value as HistoryItem[]) : []
})

function decisionOf(action: StorageAction) {
  return entry.value ? getActionDecision(entry.value, action) : {
    kind: 'conflict' as const,
    available: false,
    reason: '留存样品尚未加载',
  }
}

function targetStatus(action: StorageAction) {
  return TARGET_STATUS[action]
}

async function runAction(action: StorageAction) {
  if (!entry.value) {
    return
  }
  const result = await submitStorageAction(action, [entry.value])
  if (result.entry) {
    entry.value = result.entry
  } else {
    await reload()
  }
  messageKind.value = result.ok ? 'success' : 'error'
  statusMessage.value = result.message
}

async function reload() {
  errorMessage.value = ''
  statusMessage.value = ''
  if (!Number.isInteger(entryId.value)) {
    errorMessage.value = '留存样品编号无效'
    return
  }
  try {
    entry.value = await fetchJson<StorageRow>(`/api/sample_storage/${entryId.value}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '留存样品详情读取失败'
  }
}

onMounted(reload)
</script>
