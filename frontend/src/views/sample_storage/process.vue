<template>
  <section class="page process-page" data-module="sample_storage-process">
    <header class="page-head">
      <div>
        <h2>留存样品批量处理</h2>
        <p class="page-desc">处理入口只做选择与提交，空选、异常中断和重复触发全部复用统一处理规则。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/sample_storage">返回列表</RouterLink>
      </div>
    </header>

    <form class="process-panel" @submit.prevent="submit">
      <fieldset>
        <legend>处理动作</legend>
        <label v-for="action in actions" :key="action" class="action-option">
          <input v-model="selectedAction" type="radio" name="storage-action" :value="action" />
          {{ action }} → {{ TARGET_STATUS[action] }}
        </label>
      </fieldset>

      <div class="process-toolbar">
        <label>
          留存样品 / 留存位置检索
          <input v-model="keyword" type="search" placeholder="输入留存编号、样品编号或留存位置" />
        </label>
        <span>已选 {{ selectedIds.size }} 条；可处理 {{ summary.ready }} 条；重复提交 {{ summary.idempotent }} 条；冲突 {{ summary.conflict }} 条</span>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th class="select-cell"><input type="checkbox" :checked="allVisibleSelected" :disabled="!filteredRows.length" @change="toggleAllVisible" /></th>
            <th>留存编号</th>
            <th>样品编号</th>
            <th>留存位置</th>
            <th>当前状态</th>
            <th>上次处理</th>
            <th>规则判断</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="String(row.id)">
            <td><input type="checkbox" :checked="selectedIds.has(Number(row.id))" @change="toggleRow(Number(row.id))" /></td>
            <td><RouterLink :to="`/sample_storage/${String(row.id)}`">{{ row['留存编号'] ?? '—' }}</RouterLink></td>
            <td>{{ row['样品编号'] ?? '—' }}</td>
            <td>{{ row['留存位置'] ?? '—' }}</td>
            <td>{{ row['留存状态'] ?? row.status ?? '—' }}</td>
            <td>{{ row.last_action ?? row['处理方式'] ?? '—' }}</td>
            <td>
              <span v-if="selectedIds.has(Number(row.id))" :class="decision(row).kind === 'conflict' ? 'error-text' : 'hint-text'">
                {{ decision(row).reason || '本次将执行处理' }}
              </span>
              <span v-else class="hint-text">未选择</span>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="7" class="empty-state">未找到符合条件的留存样品</td>
          </tr>
        </tbody>
      </table>

      <footer class="process-footer">
        <button class="btn primary" type="submit" :disabled="submitting || !selectedRows.length || summary.conflict > 0">
          {{ submitting ? '处理中…' : `提交${selectedAction}` }}
        </button>
        <RouterLink class="btn ghost" :to="detailLink">查看首条明细</RouterLink>
        <span v-if="statusMessage" :class="messageClass">{{ statusMessage }}</span>
      </footer>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { request } from '@/api/client'
import { submitStorageAction } from './actions'
import {
  ACTIONS,
  TARGET_STATUS,
  actionSummary,
  getActionDecision,
  getEntryId,
  type StorageAction,
  type StorageRow,
} from './rules'

const route = useRoute()
const actions = ACTIONS

const rows = ref<StorageRow[]>([])
const selectedIds = ref<Set<number>>(new Set())
const selectedAction = ref<StorageAction>('确认处置')
const keyword = ref('')
const statusMessage = ref('')
const messageKind = ref<'error' | 'success'>('error')
const submitting = ref(false)

const selectedRows = computed(() => rows.value.filter((row) => {
  const id = getEntryId(row)
  return id !== null && selectedIds.value.has(id)
}))
const filteredRows = computed(() => {
  const text = keyword.value.trim()
  if (!text) {
    return rows.value
  }
  return rows.value.filter((row) => ['留存编号', '样品编号', '留存位置'].some((field) =>
    String(row[field] ?? '').includes(text),
  ))
})
const allVisibleSelected = computed(() =>
  filteredRows.value.length > 0
  && filteredRows.value.every((row) => {
    const id = getEntryId(row)
    return id !== null && selectedIds.value.has(id)
  }),
)
const summary = computed(() => actionSummary(selectedRows.value, selectedAction.value))
const messageClass = computed(() => (messageKind.value === 'error' ? 'error-text' : 'success-text'))
const detailLink = computed(() => {
  const firstId = selectedRows.value[0]?.id
  return firstId ? `/sample_storage/${String(firstId)}` : '/sample_storage'
})

function decision(row: StorageRow) {
  return getActionDecision(row, selectedAction.value)
}

function toggleRow(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  selectedIds.value = next
  statusMessage.value = ''
}

function toggleAllVisible(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const next = new Set(selectedIds.value)
  filteredRows.value.forEach((row) => {
    const id = getEntryId(row)
    if (id === null) {
      return
    }
    if (checked) {
      next.add(id)
    } else {
      next.delete(id)
    }
  })
  selectedIds.value = next
}

async function submit() {
  submitting.value = true
  statusMessage.value = ''
  const result = await submitStorageAction(selectedAction.value, selectedRows.value)
  submitting.value = false
  if (result.ok) {
    selectedIds.value = new Set()
  }
  await reload()
  messageKind.value = result.ok ? 'success' : 'error'
  statusMessage.value = result.message
}

async function reload() {
  try {
    const response = await request('/api/sample_storage?size=200')
    if (!response.ok) {
      throw new Error('留存样品列表读取失败')
    }
    const payload = (await response.json()) as { items?: StorageRow[] }
    rows.value = payload.items ?? []
  } catch (error) {
    messageKind.value = 'error'
    statusMessage.value = error instanceof Error ? error.message : '留存样品列表读取失败'
  }
}

function initialIds(): number[] {
  const raw = [route.query.id, route.query.ids]
    .flatMap((value) => (Array.isArray(value) ? value : value ? [value] : []))
    .join(',')
  return Array.from(new Set(raw
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value) && value > 0)))
}

onMounted(async () => {
  await reload()
  const ids = initialIds()
  const visibleIds = new Set(rows.value.map(getEntryId).filter((id): id is number => id !== null))
  selectedIds.value = new Set(ids.filter((id) => visibleIds.has(id)))
})
</script>
