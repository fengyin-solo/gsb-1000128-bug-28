/**
 * 样品留存处理的唯一口径（列表页 / 详情页 / 处理入口弹窗共用）。
 *
 * 页面只负责收集选择和展示，空选、去重、重复触发锁定、结果明细汇总
 * 全部走这里，避免三个入口各写一遍判断而让同一条记录得出两种结果。
 * 最终是否生效以服务端同一份规则为准，本模块只做提交前的一致化与防重。
 */
import { ref } from 'vue'

import { request } from '@/api/client'

export const ENDPOINT = '/api/sample_storage'

export const ACTIONS = ['确认处置', '申请延期', '登记处置'] as const
export type StorageAction = (typeof ACTIONS)[number]

/** 终态：已处置的留存样品不能再被任何动作改写。 */
export const TERMINAL_STATUS = '已处置'

/** 与后端 services/sample_storage.py 的分项状态保持同名同义。 */
export type ItemStatus = 'applied' | 'skipped' | 'blocked' | 'missing' | 'pending'

export interface BatchItem {
  id: number
  status: ItemStatus
  message: string
}

export interface BatchResult {
  ok: boolean
  message: string
  action: string
  applied: number
  skipped: number
  blocked: number
  missing: number
  items: BatchItem[]
}

export type StorageRow = Record<string, string | number | boolean | null | undefined>

export interface ProcessingLog {
  action: string
  from_status: string
  to_status: string
}

export interface StorageEntry {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  processing_log?: ProcessingLog[]
  [key: string]: string | number | boolean | null | undefined | ProcessingLog[]
}

export const ITEM_STATUS_LABEL: Record<ItemStatus, string> = {
  applied: '已处理',
  skipped: '重复跳过',
  blocked: '异常中断',
  missing: '记录不存在',
  pending: '未执行',
}

/** 把各入口的选择归一化为去重后的数字 id，保持选择顺序。 */
export function normalizeIds(ids: Array<string | number | null | undefined>): number[] {
  const result: number[] = []
  const seen = new Set<number>()
  for (const raw of ids) {
    const id = Number(raw)
    if (!Number.isInteger(id) || seen.has(id)) {
      continue
    }
    seen.add(id)
    result.push(id)
  }
  return result
}

/** 空选口径：任何入口都不允许空选提交。 */
export function describeSelection(ids: number[], action: string): string | null {
  if (!ids.length) {
    return '未选择任何留存样品，请先勾选或打开一条留存记录后再处理'
  }
  if (!(ACTIONS as readonly string[]).includes(action)) {
    return `动作「${action}」不属于样品留存可执行范围`
  }
  return null
}

/**
 * 模块级提交锁：列表页、详情页、处理入口弹窗共享同一把锁，
 * 处理未返回前任何入口都不能再次触发，避免重复提交。
 */
const submitting = ref(false)

export function isSubmitting() {
  return submitting
}

/** 统一提交：所有入口只调这一个函数，明细与汇总来自同一份响应，天然不矛盾。 */
export async function submitBatch(rawIds: Array<string | number | null | undefined>, action: string): Promise<BatchResult> {
  const entryIds = normalizeIds(rawIds)
  const invalid = describeSelection(entryIds, action)
  if (invalid) {
    // 空选/非法动作直接在本地拦下，不发请求，与后端提示文案保持一致。
    return {
      ok: false,
      message: invalid,
      action,
      applied: 0,
      skipped: 0,
      blocked: 0,
      missing: 0,
      items: [],
    }
  }
  if (submitting.value) {
    return {
      ok: false,
      message: '上一次处理尚未结束，请稍候再操作，勿重复触发',
      action,
      applied: 0,
      skipped: 0,
      blocked: 0,
      missing: 0,
      items: [],
    }
  }

  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/batch`, {
      method: 'POST',
      body: JSON.stringify({ action, entry_ids: entryIds }),
    })
    if (!response.ok) {
      return {
        ok: false,
        message: '样品留存动作未生效，请稍后重试',
        action,
        applied: 0,
        skipped: 0,
        blocked: 0,
        missing: 0,
        items: [],
      }
    }
    return (await response.json()) as BatchResult
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : '样品留存操作失败',
      action,
      applied: 0,
      skipped: 0,
      blocked: 0,
      missing: 0,
      items: [],
    }
  } finally {
    submitting.value = false
  }
}

/** 终态判定：列表和详情据此决定动作按钮是否还可点。 */
export function isTerminal(row: StorageRow | StorageEntry): boolean {
  return row.status === TERMINAL_STATUS
}
