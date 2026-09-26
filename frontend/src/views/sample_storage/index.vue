<template>
  <section class="page" data-module="sample_storage">
    <header class="page-head">
      <div>
        <h2>样品留存管理</h2>
        <p class="page-desc">维护留存样品，围绕留存编号、样品编号、留存位置、留存期限做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" :to="processPath">进入批量处理</RouterLink>
        <button class="btn primary" type="button" @click="openCreate">登记留存样品</button>
        <button class="btn" type="button" @click="exportRows">导出样品留存清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <span>已选 {{ selectedIds.size }} 条</span>
      <button
        v-for="action in actions"
        :key="action"
        class="btn"
        type="button"
        :disabled="selectedRows.length === 0 || isActionInflight(action, [...selectedIds])"
        @click="runBatchAction(action)"
      >
        批量{{ action }}
      </button>
      <RouterLink v-if="selectedRows.length" class="btn ghost" :to="selectedProcessPath">到处理入口确认</RouterLink>
      <span v-if="statusMessage" :class="messageClass">{{ statusMessage }}</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="select-cell"><input type="checkbox" :checked="allSelected" :disabled="!rows.length" @change="toggleAll" /></th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="select-cell">
            <input
              type="checkbox"
              :checked="selectedIds.has(Number(row.id))"
              @change="toggleRow(Number(row.id))"
            />
          </td>
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '留存编号'" :to="detailPath(row)">{{ row[column] ?? '—' }}</RouterLink>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!getDecision(row, action).available || isActionInflight(action, [Number(row.id)])"
              :title="getDecision(row, action).reason"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <RouterLink class="link" :to="processPathFor(row)">处理</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无样品留存数据，可先登记留存样品</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条样品留存记录</span>
      <span v-if="statusMessage" :class="messageClass">{{ statusMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { request } from '@/api/client'
import { isActionInflight, submitStorageAction } from './actions'
import {
  ACTIONS,
  getActionDecision,
  getEntryId,
  type StorageAction,
  type StorageRow,
} from './rules'

const ENDPOINT = '/api/sample_storage'
const columns = ['留存编号', '样品编号', '留存位置', '留存期限', '到期日期', '保管人员', '处理方式', '留存状态']
const actions = ACTIONS
const filterFields = columns.slice(0, 3)

const rows = ref<StorageRow[]>([])
const total = ref(0)
const statusMessage = ref('')
const messageKind = ref<'error' | 'success'>('error')
const filters = ref<Record<string, string>>({})
const selectedIds = ref<Set<number>>(new Set())

const stats = computed(() => [
  { label: '留存中样品', value: rows.value.filter((row) => row.status === '留存中').length },
  { label: '即将到期', value: rows.value.filter((row) => row.status === '即将到期').length },
  { label: '已处置样品', value: rows.value.filter((row) => row.status === '已处置').length },
])
const selectedRows = computed(() => rows.value.filter((row) => {
  const id = getEntryId(row)
  return id !== null && selectedIds.value.has(id)
}))
const allSelected = computed(() => rows.value.length > 0 && selectedRows.value.length === rows.value.length)
const messageClass = computed(() => (messageKind.value === 'error' ? 'error-text' : 'success-text'))
const processPath = '/sample_storage/process'
const selectedProcessPath = computed(() => ({
  path: processPath,
  query: { ids: [...selectedIds.value].sort((a, b) => a - b).join(',') },
}))

function detailPath(row: StorageRow) {
  return `/sample_storage/${String(row.id)}`
}

function processPathFor(row: StorageRow) {
  return { path: `${processPath}`, query: { id: String(row.id) } }
}

function getDecision(row: StorageRow, action: StorageAction) {
  return getActionDecision(row, action)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  messageKind.value = 'error'
  statusMessage.value = '留存样品登记入口尚未接入审批流'
}

function toggleRow(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  selectedIds.value = next
}

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selectedIds.value = new Set(checked ? rows.value.map(getEntryId).filter((id): id is number => id !== null) : [])
}

async function runAction(action: StorageAction, row: StorageRow) {
  const result = await submitStorageAction(action, [row])
  await reload()
  messageKind.value = result.ok ? 'success' : 'error'
  statusMessage.value = result.message
}

async function runBatchAction(action: StorageAction) {
  const result = await submitStorageAction(action, selectedRows.value)
  if (result.ok) {
    selectedIds.value = new Set()
  }
  await reload()
  messageKind.value = result.ok ? 'success' : 'error'
  statusMessage.value = result.message
}

async function reload() {
  statusMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('留存样品列表读取失败')
    }
    const payload = (await response.json()) as { items?: StorageRow[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    const visibleIds = new Set(rows.value.map(getEntryId).filter((id): id is number => id !== null))
    selectedIds.value = new Set([...selectedIds.value].filter((id) => visibleIds.has(id)))
  } catch (error) {
    messageKind.value = 'error'
    statusMessage.value = error instanceof Error ? error.message : '样品留存列表读取失败'
  }
}

onMounted(reload)
</script>
