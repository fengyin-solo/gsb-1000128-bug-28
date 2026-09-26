<template>
  <section class="page" data-module="sample_storage-detail">
    <header class="page-head">
      <div>
        <h2>留存样品明细 #{{ entryId }}</h2>
        <p class="page-desc">
          <RouterLink class="link" to="/sample_storage">← 返回样品留存列表</RouterLink>
          详情页的处理动作与列表批量处理共用同一判断口径。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="terminal || busy" @click="openProcess">
          {{ terminal ? '已处置（终态）' : '处理此留存样品' }}
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="result-panel is-warn">
      <span class="error-text">{{ errorMessage }}</span>
    </div>

    <template v-else-if="entry">
      <div class="detail-grid">
        <article v-for="column in columns" :key="column" class="detail-item">
          <span class="detail-label">{{ column }}</span>
          <strong class="detail-value">{{ entry[column] || '—' }}</strong>
        </article>
        <article class="detail-item">
          <span class="detail-label">异常标记</span>
          <strong class="detail-value" :class="entry.abnormal ? 'error-text' : 'success-text'">
            {{ entry.abnormal ? '异常（处理将被拦截）' : '正常' }}
          </strong>
        </article>
        <article class="detail-item">
          <span class="detail-label">待处理</span>
          <strong class="detail-value">{{ entry.pending ? '是' : '否' }}</strong>
        </article>
      </div>

      <section class="log-panel">
        <h3>处理记录</h3>
        <p v-if="!entry.processing_log?.length" class="hint-text">暂无处理记录，处置后可在此追溯每一次状态变更。</p>
        <ul v-else class="log-list">
          <li v-for="(log, index) in entry.processing_log" :key="index" class="log-line">
            <span class="result-tag">{{ log.action }}</span>
            <span>{{ log.from_status }} → {{ log.to_status }}</span>
          </li>
        </ul>
      </section>

      <p v-if="hint" class="hint-text">{{ hint }}</p>
    </template>

    <div v-else-if="loading" class="empty-state">明细加载中…</div>

    <ProcessDialog
      :open="dialogOpen"
      :ids="[entryId]"
      :single="true"
      @close="dialogOpen = false"
      @done="onDone"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import ProcessDialog from './ProcessDialog.vue'
import { ENDPOINT, isSubmitting, isTerminal, type BatchResult, type StorageEntry } from './rules'

const route = useRoute()
const entryId = Number(route.params.id)

const columns = ["留存编号", "样品编号", "留存位置", "留存期限", "到期日期", "保管人员", "处理方式", "留存状态"]

const entry = ref<StorageEntry | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const hint = ref('')
const dialogOpen = ref(false)
const busy = isSubmitting()

const terminal = computed(() => (entry.value ? isTerminal(entry.value) : false))

function openProcess() {
  hint.value = ''
  dialogOpen.value = true
}

async function onDone(result: BatchResult) {
  hint.value = result.message
  // 无论 applied 还是 blocked，明细都要回读服务端，保证页面状态与处理结果不矛盾；
  // 空选等前置失败（无明细）时无需请求。
  if (result.items.length > 0) {
    await loadEntry()
  }
}

async function loadEntry() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error(`留存样品 ${entryId} 不存在或已归档`)
      }
      throw new Error('留存样品明细读取失败')
    }
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '留存样品明细读取失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadEntry)
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.detail-item {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail-label {
  color: var(--muted);
  font-size: 12px;
}
.detail-value {
  font-size: 14px;
}
.log-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}
.log-panel h3 {
  margin: 0 0 8px;
  font-size: 14px;
}
.log-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.log-line {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 13px;
}
.result-tag {
  border-radius: 4px;
  padding: 1px 8px;
  background: #abefc6;
}
.hint-text {
  font-size: 12px;
  color: var(--muted);
}
.result-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.result-panel.is-warn {
  background: #fef3f2;
  border-color: #fda29b;
}
.success-text {
  color: #067647;
}
</style>
