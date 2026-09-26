<template>
  <div v-if="open" class="modal-mask" @click.self="cancel">
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="样品留存处理入口">
      <header class="modal-head">
        <h3>样品留存处理</h3>
        <button class="link" type="button" :disabled="busy" @click="cancel">关闭</button>
      </header>

      <div class="modal-body">
        <p class="modal-tip">
          {{ single ? '详情页单条处理' : `列表批量处理：已选择 ${ids.length} 条留存样品` }}
          ；异常记录将中断本次处理，已处理结果可在留存明细中追溯。
        </p>

        <label class="filter-item">
          <span>处理动作</span>
          <select v-model="action" :disabled="busy || Boolean(result)">
            <option v-for="item in ACTIONS" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>

        <div v-if="result" class="result-panel" :class="result.ok ? 'is-ok' : 'is-warn'">
          <p class="result-summary">
            <strong :class="result.ok ? 'success-text' : 'error-text'">{{ result.ok ? '处理完成' : '处理存在拦截' }}</strong>
            <span>{{ result.message }}</span>
          </p>
          <ul v-if="result.items.length" class="result-items">
            <li v-for="item in result.items" :key="item.id" class="result-line">
              <span class="result-id">#{{ item.id }}</span>
              <span class="result-tag" :data-status="item.status">{{ statusLabel(item.status) }}</span>
              <span class="result-msg">{{ item.message }}</span>
            </li>
          </ul>
        </div>
      </div>

      <footer class="modal-foot">
        <button class="btn" type="button" :disabled="busy" @click="cancel">
          {{ result ? '完成' : '取消' }}
        </button>
        <button v-if="!result" class="btn primary" type="button" :disabled="busy" @click="confirm">
          {{ busy ? '处理中…' : `确认${action}` }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import {
  ACTIONS,
  isSubmitting,
  submitBatch,
  type BatchResult,
  type ItemStatus,
  ITEM_STATUS_LABEL,
} from './rules'

const props = defineProps<{
  open: boolean
  ids: number[]
  single?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'done', result: BatchResult): void
}>()

const action = ref<string>('确认处置')
const result = ref<BatchResult | null>(null)
const busy = isSubmitting()

watch(
  () => props.open,
  (open) => {
    if (open) {
      action.value = '确认处置'
      result.value = null
    }
  },
)

function statusLabel(status: ItemStatus): string {
  return ITEM_STATUS_LABEL[status] ?? status
}

async function confirm() {
  const outcome = await submitBatch(props.ids, action.value)
  result.value = outcome
  emit('done', outcome)
}

function cancel() {
  if (busy.value) {
    return
  }
  emit('close')
}
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 560px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.2);
  overflow: hidden;
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.modal-body {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.modal-tip {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}
.result-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.result-panel.is-ok {
  background: #f0fdf4;
  border-color: #abefc6;
}
.result-panel.is-warn {
  background: #fef3f2;
  border-color: #fda29b;
}
.result-summary {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 0 0 8px;
  font-size: 13px;
}
.result-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.result-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
}
.result-id {
  color: var(--muted);
  min-width: 36px;
}
.result-tag {
  border-radius: 4px;
  padding: 1px 6px;
  background: #e2e8f0;
  white-space: nowrap;
}
.result-tag[data-status='applied'] {
  background: #abefc6;
}
.result-tag[data-status='skipped'] {
  background: #e2e8f0;
}
.result-tag[data-status='blocked'],
.result-tag[data-status='missing'] {
  background: #fda29b;
}
.result-tag[data-status='pending'] {
  background: #fde68a;
}
.result-msg {
  color: #334155;
}
.success-text {
  color: #067647;
}
</style>
