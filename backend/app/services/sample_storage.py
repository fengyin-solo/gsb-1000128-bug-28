"""样品留存业务规则：状态流转、字段校验、批量处理口径全部收在这里。

列表页（批量处置）、详情页（单条处置）、处理入口（确认处置/申请延期/登记处置）
三个入口只负责收集选择与展示结果，真正的判断统一走 ``build_action_plan``，
保证同一条记录在任何入口得到的结论一致。

统一口径：
- 空选：不允许提交，任何记录都不动，直接给出可读提示；
- 异常中断：留存记录带异常标记（abnormal）时不允许处置，批量执行到该条即中断，
  它之前的记录照常生效，之后的记录保持原样；
- 重复触发：已经处于目标状态（含已处置终态）的记录按幂等处理，跳过且不再覆写，
  重复操作不会把明细改成另一种结果；
- 可追溯：每次生效的处置都会追加到记录的 processing_log，已有记录始终可查。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "sample_storage"
REQUIRED_FIELDS = ["留存编号", "样品编号", "留存位置"]

# 状态序列只用于展示顺序；是否终态由 TERMINAL_STATUSES 判定，
# 不再依赖序列最后一个元素，避免“已处置”被误判成待处理。
STATUS_ORDER = ["留存中", "即将到期", "已处置", "已延期"]
TERMINAL_STATUSES = ["已处置"]

# 三个处理入口共用的动作 -> 目标状态映射。
ACTION_RULES: dict[str, str] = {
    "确认处置": "已处置",
    "申请延期": "已延期",
    "登记处置": "已处置",
}

# 结果分项的统一状态：成功 / 幂等跳过 / 阻断中断 / 记录不存在
ITEM_APPLIED = "applied"
ITEM_SKIPPED = "skipped"
ITEM_BLOCKED = "blocked"
ITEM_MISSING = "missing"

MSG_EMPTY_SELECTION = "未选择任何留存样品，请先勾选或打开一条留存记录后再处理"
MSG_UNKNOWN_ACTION = "动作「{action}」不属于样品留存可执行范围"
MSG_TARGET_INVALID = "目标状态「{target}」不在允许的状态序列里"
MSG_MISSING_RECORD = "留存样品 {entry_id} 不存在或已归档"
MSG_BLOCKED = "留存样品 {entry_id} 状态异常，已中断本次批量处理；异常解除后可继续处理其余记录"
MSG_SKIPPED = "留存样品 {entry_id} 已是{target}状态，无需重复处理"
MSG_APPLIED = "留存样品 {entry_id} 已{action}"


class BatchRuleError(ValueError):
    """规则前置校验失败（空选、非法动作）：此时一条记录都不应被改动。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _is_terminal(entry: dict[str, Any]) -> bool:
    return entry.get("status") in TERMINAL_STATUSES


def _normalize_ids(raw_ids: Any) -> list[int]:
    """把各入口传来的选择归一化成去重后的 int 列表，保持用户选择顺序。"""
    if not isinstance(raw_ids, (list, tuple, set)):
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for raw in raw_ids:
        try:
            entry_id = int(raw)
        except (TypeError, ValueError):
            continue
        if entry_id in seen:
            continue
        seen.add(entry_id)
        ids.append(entry_id)
    return ids


def evaluate_action(entry_id: int, action: str, *, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """对单条记录做一次纯判断，不写数据。

    列表页、详情页、处理入口共用这一份判定；返回结构同时供批量汇总使用。
    """
    if action not in ACTION_RULES:
        raise BatchRuleError(MSG_UNKNOWN_ACTION.format(action=action))
    target = ACTION_RULES[action]
    if target not in STATUS_ORDER:
        raise BatchRuleError(MSG_TARGET_INVALID.format(target=target))

    rows = store.rows(MODULE) if rows is None else rows
    entry = next((row for row in rows if int(row.get("id", 0)) == entry_id), None)
    if entry is None:
        return {
            "id": entry_id,
            "status": ITEM_MISSING,
            "message": MSG_MISSING_RECORD.format(entry_id=entry_id),
            "entry": None,
        }

    # 已处置是终态；或记录已经处在本次动作的目标状态 -> 幂等跳过，绝不覆写。
    if _is_terminal(entry) or entry.get("status") == target:
        return {
            "id": entry_id,
            "status": ITEM_SKIPPED,
            "message": MSG_SKIPPED.format(entry_id=entry_id, target=entry.get("status") or target),
            "entry": entry,
        }

    # 异常留存记录不允许处置：批量在此中断，单条直接拦下。
    if entry.get("abnormal"):
        return {
            "id": entry_id,
            "status": ITEM_BLOCKED,
            "message": MSG_BLOCKED.format(entry_id=entry_id),
            "entry": entry,
        }

    return {
        "id": entry_id,
        "status": ITEM_APPLIED,
        "message": MSG_APPLIED.format(entry_id=entry_id, action=action),
        "entry": entry,
        "target": target,
        "action": action,
        "from_status": entry.get("status"),
    }


def build_action_plan(entry_ids: Any, action: str) -> list[dict[str, Any]]:
    """统一的批量处理口径：空选拦截、去重、逐项判断、遇异常中断。

    返回的每一项是 evaluate_action 的判定结果；遇到 blocked 时补齐后续未处理项，
    让调用方既能看到已生效明细，也能看到中断点之后尚未执行的记录。
    """
    ids = _normalize_ids(entry_ids)
    if not ids:
        raise BatchRuleError(MSG_EMPTY_SELECTION)
    if action not in ACTION_RULES:
        raise BatchRuleError(MSG_UNKNOWN_ACTION.format(action=action))

    rows = store.rows(MODULE)
    plan: list[dict[str, Any]] = []
    blocked = False
    for entry_id in ids:
        if blocked:
            plan.append({
                "id": entry_id,
                "status": "pending",
                "message": f"留存样品 {entry_id} 因前序异常未处理，本次未执行",
                "entry": store.find(MODULE, entry_id),
            })
            continue
        result = evaluate_action(entry_id, action, rows=rows)
        plan.append(result)
        if result["status"] == ITEM_BLOCKED:
            blocked = True
    return plan


class SampleStorageService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("留存编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None and "processing_log" not in entry:
            # 历史种子数据没有处置日志字段，补上空列表，保证详情页口径一致、可查。
            entry["processing_log"] = []
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["处理方式"] = ""
        entry["留存状态"] = STATUS_ORDER[0]
        entry["processing_log"] = []
        rows.append(entry)
        return entry, []

    def run_batch(self, entry_ids: Any, action: str) -> dict[str, Any]:
        """执行批量处理：先按统一口径出判定计划，再只对 applied 项落库。

        判定与写入分离，保证中断点之前生效、之后不动；重复执行本方法结果幂等。
        """
        plan = build_action_plan(entry_ids, action)
        items: list[dict[str, Any]] = []
        applied = skipped = blocked = missing = pending_count = 0
        for result in plan:
            status = result["status"]
            entry = result.get("entry")
            if status == ITEM_APPLIED and entry is not None:
                target = result["target"]
                entry["status"] = target
                # 只有“已处置”是终态；已延期仍需后续处置，仍属待处理。
                entry["pending"] = target not in TERMINAL_STATUSES
                entry["处理方式"] = result["action"]
                entry["留存状态"] = target
                entry.setdefault("processing_log", []).append({
                    "action": result["action"],
                    "from_status": result.get("from_status"),
                    "to_status": target,
                })
                applied += 1
            elif status == ITEM_SKIPPED:
                skipped += 1
            elif status == ITEM_BLOCKED:
                blocked += 1
            elif status == ITEM_MISSING:
                missing += 1
            else:
                pending_count += 1
            items.append({"id": result["id"], "status": status, "message": result["message"]})

        if blocked:
            message = (
                f"批量{action}因异常记录中断：已处理 {applied} 条，"
                f"重复跳过 {skipped} 条，{blocked} 条异常拦截，{pending_count} 条未执行"
            )
            ok = False
        elif applied == 0 and skipped:
            message = f"所选 {skipped} 条留存样品均已处于对应状态，未重复处理"
            ok = True
        else:
            tail = f"，重复跳过 {skipped} 条" if skipped else ""
            message = f"批量{action}完成：成功 {applied} 条{tail}"
            ok = True

        return {
            "ok": ok,
            "message": message,
            "action": action,
            "applied": applied,
            "skipped": skipped,
            "blocked": blocked,
            "missing": missing,
            "items": items,
        }
