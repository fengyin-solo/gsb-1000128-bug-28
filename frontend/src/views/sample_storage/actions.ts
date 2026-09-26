/** 样品留存动作提交：所有入口共用同一路由、锁和结果解析。 */
import { request } from '@/api/client'

import {
  ACTIONS,
  STORAGE_ENDPOINT,
  type StorageAction,
  type StorageRow,
  validateActionRequest,
} from './rules'

export interface ActionSubmitResult {
  ok: boolean
  message: string
  entry?: StorageRow
  entries: StorageRow[]
  processed: number
  skipped: number
}

interface ActionResponse {
  ok?: boolean
  message?: string
  entry?: StorageRow
  entries?: StorageRow[]
  processed?: number
  skipped?: number
}

const inflightKeys = new Set<string>()

export function actionKey(action: string, entryIds: number[]): string {
  return `${action}:${[...entryIds].sort((a, b) => a - b).join(',')}`
}

export function isActionInflight(action: string, entryIds: number[]): boolean {
  return inflightKeys.has(actionKey(action, entryIds))
}

export interface SubmitOptions {
  force?: boolean
}

/**
 * 先执行共用规则，再发起请求；同一动作和同一批记录处理中会被拦下，
 * 防止重复点击制造两次流转。
 */
export async function submitStorageAction(
  action: StorageAction | string | null | undefined,
  entries: StorageRow[] | null | undefined,
  options: SubmitOptions = {},
): Promise<ActionSubmitResult> {
  const check = validateActionRequest(action, entries)
  if (!check.ok || !check.action) {
    return { ok: false, message: check.message, entries: [], processed: 0, skipped: 0 }
  }

  const key = actionKey(check.action, check.entryIds)
  if (!options.force && inflightKeys.has(key)) {
    return {
      ok: false,
      message: '该留存处理正在执行，请勿重复触发',
      entries: [],
      processed: 0,
      skipped: 0,
    }
  }

  inflightKeys.add(key)
  try {
    const isSingle = check.entryIds.length === 1
    const path = isSingle
      ? `${STORAGE_ENDPOINT}/${check.entryIds[0]}/actions`
      : `${STORAGE_ENDPOINT}/actions`
    const response = await request(path, {
      method: 'POST',
      body: JSON.stringify({ action: check.action, entryIds: check.entryIds }),
    })
    const payload = (await response.json().catch(() => ({}))) as ActionResponse
    const message = payload.message || (response.ok ? '样品留存动作已生效' : '样品留存动作未生效，请稍后重试')
    if (!response.ok || payload.ok === false) {
      return { ok: false, message, entries: payload.entries ?? [], processed: 0, skipped: 0 }
    }

    const resultEntries = payload.entries ?? (payload.entry ? [payload.entry] : [])
    return {
      ok: true,
      message,
      entry: payload.entry ?? resultEntries[0],
      entries: resultEntries,
      processed: payload.processed ?? (isSingle ? 1 : resultEntries.length),
      skipped: payload.skipped ?? 0,
    }
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : '样品留存操作失败',
      entries: [],
      processed: 0,
      skipped: 0,
    }
  } finally {
    inflightKeys.delete(key)
  }
}

export function getInflightEntries(entryIds: number[]): StorageAction[] {
  return ACTIONS.filter((action) => isActionInflight(action, entryIds))
}
