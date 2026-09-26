<template>
  <section class="page" data-module="sample_storage">
    <header class="page-head">
      <div>
        <h2>样品留存管理</h2>
        <p class="page-desc">维护留存样品，围绕留存编号、样品编号、留存位置、留存期限做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
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

    <form class="filter-bar" @submit.prevent="() => reload()">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <label class="select-all">
        <input type="checkbox" :checked="allChecked" :indeterminate.prop="someChecked" @change="toggleAll" />
        全选本页
      </label>
      <span class="selection-count">已选 {{ selectedIds.length }} 条</span>
      <button class="btn primary" type="button" :disabled="!selectedIds.length || busy" @click="openBatch">
        批量处理
      </button>
      <span v-if="batchHint" class="hint-text">{{ batchHint }}</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">选择</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input type="checkbox" :checked="isSelected(row)" :disabled="isTerminal(row)" @change="toggleRow(row)" />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <RouterLink class="link" :to="`/sample_storage/${row.id}`">明细</RouterLink>
            <button class="link" type="button" :disabled="isTerminal(row)" @click="openSingle(row)">
              {{ isTerminal(row) ? '已处置' : '处理' }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无样品留存数据，可先登记留存样品</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条样品留存记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <ProcessDialog
      :open="dialogOpen"
      :ids="dialogIds"
      :single="dialogSingle"
      @close="dialogOpen = false"
      @done="onDone"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import ProcessDialog from './ProcessDialog.vue'
import {
  ENDPOINT,
  isSubmitting,
  isTerminal,
  normalizeIds,
  type BatchResult,
  type StorageRow,
} from './rules'

type Row = StorageRow

const columns = ["留存编号", "样品编号", "留存位置", "留存期限", "到期日期", "保管人员", "处理方式", "留存状态"]
const filterFields = columns.slice(0, 3)

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const batchHint = ref('')
const filters = ref<Record<string, string>>({})

const selected = ref<Set<number>>(new Set())
const dialogOpen = ref(false)
const dialogIds = ref<number[]>([])
const dialogSingle = ref(false)
const busy = isSubmitting()

const selectedIds = computed(() => [...selected.value])
const selectableRows = computed(() => rows.value.filter((row) => !isTerminal(row)))
const allChecked = computed(
  () => selectableRows.value.length > 0 && selectableRows.value.every((row) => selected.value.has(Number(row.id))),
)
const someChecked = computed(() => selected.value.size > 0 && !allChecked.value)

const stats = computed(() => {
  const count = (status: string) => rows.value.filter((row) => row.status === status).length
  return [
    { label: '留存中样品', value: count('留存中') + count('已延期') },
    { label: '即将到期', value: count('即将到期') },
    { label: '已处置样品', value: count('已处置') },
  ]
})

function isSelected(row: Row): boolean {
  return selected.value.has(Number(row.id))
}

function toggleRow(row: Row) {
  const id = Number(row.id)
  const next = new Set(selected.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  selected.value = next
}

function toggleAll() {
  if (allChecked.value) {
    const next = new Set(selected.value)
    for (const row of selectableRows.value) {
      next.delete(Number(row.id))
    }
    selected.value = next
  } else {
    selected.value = new Set(selectableRows.value.map((row) => Number(row.id)))
  }
}

function openBatch() {
  dialogIds.value = normalizeIds(selectedIds.value)
  dialogSingle.value = false
  dialogOpen.value = true
}

function openSingle(row: Row) {
  dialogIds.value = normalizeIds([Number(row.id)])
  dialogSingle.value = true
  dialogOpen.value = true
}

async function onDone(result: BatchResult) {
  batchHint.value = result.message
  // 明细与结果来自同一份响应：以服务端最新数据刷新，页面不会与处理结果矛盾。
  await reload(result.applied > 0)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '留存样品登记入口尚未接入审批流'
}

async function reload(preserveError = false) {
  if (!preserveError) {
    errorMessage.value = ''
  }
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('留存样品列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 清理已不在当前页（或已被处置）的勾选项，避免把旧选择带进下一次批量。
    const visibleIds = new Set(rows.value.filter((row) => !isTerminal(row)).map((row) => Number(row.id)))
    selected.value = new Set([...selected.value].filter((id) => visibleIds.has(id)))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样品留存列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.check-col {
  width: 48px;
  text-align: center;
}
.selection-count {
  font-size: 12px;
  color: var(--muted);
}
.hint-text {
  font-size: 12px;
  color: var(--muted);
}
</style>
