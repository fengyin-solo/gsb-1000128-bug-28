/** 样品留存处理规则：列表、详情与处理入口共用这一份判断。 */

export type StorageCell = string | number | boolean | null | undefined
export type StorageRow = Record<string, StorageCell>

export type ActionKind = 'ready' | 'idempotent' | 'conflict'
export type StorageAction = '确认处置' | '申请延期' | '登记处置'
export type StorageStatus = '留存中' | '即将到期' | '已处置' | '已延期'

export const STORAGE_ENDPOINT = '/api/sample_storage'
export const ACTIONS: StorageAction[] = ['确认处置', '申请延期', '登记处置']
export const STATUSES: StorageStatus[] = ['留存中', '即将到期', '已处置', '已延期']
export const TARGET_STATUS: Record<StorageAction, StorageStatus> = {
  确认处置: '已处置',
  申请延期: '已延期',
  登记处置: '已处置',
}
export const ACTIVE_STATUSES: ReadonlySet<StorageStatus> = new Set<StorageStatus>(['留存中', '即将到期'])
export const STATUS_FIELD = '留存状态'
export const ACTION_FIELD = '处理方式'
export const LOCATION_FIELD = '留存位置'

export interface ActionDecision {
  kind: ActionKind
  available: boolean
  reason: string
}

export interface ActionRequestCheck {
  ok: boolean
  message: string
  action: StorageAction | null
  entryIds: number[]
}

export function asStorageAction(action: string | null | undefined): StorageAction | null {
  return ACTIONS.includes(action as StorageAction) ? (action as StorageAction) : null
}

export function getStatus(row: StorageRow): StorageStatus | string {
  const status = String(row.status ?? row[STATUS_FIELD] ?? '').trim()
  return STATUSES.includes(status as StorageStatus) ? (status as StorageStatus) : (status || '留存中')
}

export function getEntryId(row: StorageRow): number | null {
  const id = Number(row.id)
  return Number.isInteger(id) ? id : null
}

export function getLocation(row: StorageRow): string {
  return String(row[LOCATION_FIELD] ?? '').trim()
}

export function getLastAction(row: StorageRow): string {
  return String(row.last_action ?? '').trim()
}

export function entryLabel(row: StorageRow): string {
  const number = String(row['留存编号'] ?? '').trim()
  return number ? `留存样品「${number}」` : `留存样品 ${getEntryId(row) ?? '未知'}`
}

/** 同一条记录在三个入口的动作可执行性都从这里得出，避免重复写出不同结论。 */
export function getActionDecision(row: StorageRow, rawAction: string | null | undefined): ActionDecision {
  const action = asStorageAction(rawAction)
  if (!action) {
    return { kind: 'conflict', available: false, reason: `动作「${rawAction ?? ''}」不属于样品留存可执行范围` }
  }

  const status = getStatus(row) as StorageStatus
  if (!STATUSES.includes(status)) {
    return { kind: 'conflict', available: false, reason: `${entryLabel(row)}的状态不在样品留存允许的状态序列里` }
  }

  if (ACTIVE_STATUSES.has(status)) {
    if (!getLocation(row)) {
      return { kind: 'conflict', available: false, reason: `${entryLabel(row)}缺少留存位置，请先补录后再${action}` }
    }
    return { kind: 'ready', available: true, reason: '' }
  }

  const target = TARGET_STATUS[action]
  const lastAction = getLastAction(row)
  if (lastAction === action || (!lastAction && status === target)) {
    return { kind: 'idempotent', available: true, reason: `${entryLabel(row)}已${action}，再次提交不会产生新的处理记录` }
  }
  return { kind: 'conflict', available: false, reason: `${entryLabel(row)}当前状态为「${status}」，不能再次执行「${action}」` }
}

function normalizeEntries(entries: StorageRow[] | null | undefined): StorageRow[] {
  return Array.isArray(entries) ? entries : []
}

/** 处理前的空选、非法动作、冲突校验：单条和批量使用同一口径。 */
export function validateActionRequest(
  rawAction: string | null | undefined,
  rawEntries: StorageRow[] | null | undefined,
): ActionRequestCheck {
  const action = asStorageAction(rawAction)
  const entries = normalizeEntries(rawEntries)
  const entryIds = Array.from(
    entries.reduce((map: Map<number, number>, row) => {
      const id = getEntryId(row)
      if (id !== null && !map.has(id)) {
        map.set(id, id)
      }
      return map
    }, new Map<number, number>()).values(),
  )

  if (!rawAction || !String(rawAction).trim()) {
    return { ok: false, message: '请选择要执行的留存处理动作', action: null, entryIds }
  }
  if (!action) {
    return { ok: false, message: `动作「${rawAction}」不属于样品留存可执行范围`, action: null, entryIds }
  }
  if (entries.length === 0 || entryIds.length === 0) {
    return { ok: false, message: '请先勾选需要处理的留存样品', action, entryIds: [] }
  }

  const conflicts = entries
    .map((row) => getActionDecision(row, action))
    .filter((decision) => decision.kind === 'conflict')
  if (conflicts.length > 0) {
    return { ok: false, message: conflicts[0].reason, action, entryIds }
  }
  return { ok: true, message: '', action, entryIds }
}

export function actionSummary(entries: StorageRow[], action: StorageAction) {
  const decisions = entries.map((row) => getActionDecision(row, action))
  return {
    ready: decisions.filter((decision) => decision.kind === 'ready').length,
    idempotent: decisions.filter((decision) => decision.kind === 'idempotent').length,
    conflict: decisions.filter((decision) => decision.kind === 'conflict').length,
  }
}
