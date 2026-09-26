"""样品留存业务规则：状态流转、字段校验与筛选口径都收在这里。

列表、详情、单条处理与批量处理入口都必须走同一套判断：
- 空选：动作与记录都缺失时直接拒绝，不写任何记录；
- 异常中断：批量处理先整体校验再落库，校验不过或写入异常都不留下半截结果；
- 重复触发：处理中的请求、已完成的同动作重试、不同动作的冲突都在这里收口。
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.store import store

MODULE = "sample_storage"
REQUIRED_FIELDS = ["留存编号", "样品编号", "留存位置"]
FILTER_FIELDS = ["留存编号", "样品编号", "留存位置"]
STATUS_ORDER = ["留存中", "即将到期", "已处置", "已延期"]
ACTIVE_STATUSES = {"留存中", "即将到期"}
ACTION_RULES = {"确认处置": "已处置", "申请延期": "已延期", "登记处置": "已处置"}
NEGATIVE_ACTIONS: list[str] = []
UNKNOWN_STATUS_MESSAGE = "状态不在样品留存允许的状态序列里"


class SampleStorageService:
    def __init__(self) -> None:
        self._action_lock = Lock()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if any(keyword in str(row.get(field, "")) for field in FILTER_FIELDS)
            ]
        for field, value in (filters or {}).items():
            if value:
                rows = [row for row in rows if value in str(row.get(field, ""))]
        if status:
            rows = [row for row in rows if self.canonical_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self.present(entry)

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
        entry["last_action"] = None
        entry["action_history"] = []
        rows.append(entry)
        return self.present(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """单条处理入口：与批量入口共用同一套动作判断，保证结果不打架。"""
        with self._action_lock:
            result = self._run_actions_locked([entry_id], action)
        entry = result["entries"][0] if result["entries"] else None
        return entry, result["message"]

    def run_actions(self, entry_ids: list[int], action: str) -> dict[str, Any]:
        """批量处理入口：整体校验、原子落库、重复触发按同一口径判定。"""
        with self._action_lock:
            return self._run_actions_locked(entry_ids, action)

    def canonical_status(self, entry: dict[str, Any]) -> str:
        """归一化留存状态：兼容旧数据里 status 与「留存状态」并存的两份写法。"""
        status = str(entry.get("status") or "").strip()
        if status in STATUS_ORDER:
            return status
        display_status = str(entry.get("留存状态") or "").strip()
        if display_status in STATUS_ORDER:
            return display_status
        return status or STATUS_ORDER[0]

    def present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表与详情共用的展示口径：不改原始记录，只把状态字段对齐后返回。"""
        snapshot = dict(entry)
        status = self.canonical_status(snapshot)
        snapshot["status"] = status
        snapshot["留存状态"] = status
        snapshot["pending"] = status in ACTIVE_STATUSES
        snapshot["处理方式"] = snapshot.get("处理方式") or snapshot.get("last_action") or "—"
        return snapshot

    def _run_actions_locked(self, entry_ids: list[int], action: str) -> dict[str, Any]:
        action = str(action or "").strip()
        unique_ids = list(dict.fromkeys(entry_ids))
        if not action:
            return self._result(False, "请选择要执行的留存处理动作", [], processed=0, skipped=0)
        if action not in ACTION_RULES:
            return self._result(False, f"动作「{action}」不属于样品留存可执行范围", [], processed=0, skipped=0)
        if not unique_ids:
            return self._result(False, "请先勾选需要处理的留存样品", [], processed=0, skipped=0)

        entries: list[dict[str, Any]] = []
        missing_ids: list[int] = []
        for entry_id in unique_ids:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                missing_ids.append(entry_id)
            else:
                entries.append(entry)
        if missing_ids:
            missing = "、".join(str(entry_id) for entry_id in missing_ids)
            return self._result(False, f"留存样品 {missing} 不存在或已归档", [], processed=0, skipped=0)

        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return self._result(False, f"目标状态「{target}」不在允许的状态序列里", [], processed=0, skipped=0)

        evaluations = [self._evaluate(entry, action, target) for entry in entries]
        conflicts = [message for kind, message in evaluations if kind == "conflict"]
        if conflicts:
            return self._result(False, "；".join(conflicts), [], processed=0, skipped=0)

        ready_entries = [entry for entry, (kind, _message) in zip(entries, evaluations) if kind == "ready"]
        skipped = len(entries) - len(ready_entries)
        if not ready_entries:
            if len(entries) == 1:
                message = evaluations[0][1]
            else:
                message = f"{len(entries)} 条留存样品均已{action}，本次为重复提交，未产生新的处理记录"
            return self._result(True, message, entries, processed=0, skipped=skipped)

        changed: list[tuple[dict[str, Any], dict[str, Any]]] = []
        try:
            for entry in ready_entries:
                before = dict(entry)
                self._apply(entry, action, target)
                changed.append((entry, before))
        except Exception:
            for entry, before in changed:
                entry.clear()
                entry.update(before)
            return self._result(False, "样品留存处理异常中断，已恢复原状态，请重新操作", [], processed=0, skipped=0)

        processed = len(ready_entries)
        if skipped:
            message = f"已处理 {processed} 条留存样品，{skipped} 条此前已完成相同动作，本次未重复登记"
        elif processed == 1:
            message = f"留存样品已{action}"
        else:
            message = f"已批量{action} {processed} 条留存样品"
        return self._result(True, message, entries, processed=processed, skipped=skipped)

    def _evaluate(self, entry: dict[str, Any], action: str, target: str) -> tuple[str, str]:
        """判断一条记录能否执行动作：ready 可处理、idempotent 重复提交、conflict 冲突。"""
        status = self.canonical_status(entry)
        label = self._entry_label(entry)
        if status not in STATUS_ORDER:
            return "conflict", f"{label}的{UNKNOWN_STATUS_MESSAGE}"
        if status in ACTIVE_STATUSES:
            if not str(entry.get("留存位置") or "").strip():
                return "conflict", f"{label}缺少留存位置，请先补录后再{action}"
            return "ready", ""
        last_action = str(entry.get("last_action") or "").strip()
        if last_action == action or (not last_action and status == target):
            return "idempotent", f"{label}已{action}，本次为重复提交，未产生新的处理记录"
        return "conflict", f"{label}当前状态为「{status}」，不能再次执行「{action}」"

    def _apply(self, entry: dict[str, Any], action: str, target: str) -> None:
        entry["status"] = target
        entry["留存状态"] = target
        entry["处理方式"] = action
        entry["last_action"] = action
        entry["pending"] = False
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        history = entry.setdefault("action_history", [])
        history.append({
            "action": action,
            "status": target,
            "at": datetime.now(timezone.utc).isoformat(),
        })

    def _entry_label(self, entry: dict[str, Any]) -> str:
        number = str(entry.get("留存编号") or "").strip()
        if number:
            return f"留存样品「{number}」"
        return f"留存样品 {entry.get('id', '未知')}"

    def _result(
        self,
        ok: bool,
        message: str,
        entries: list[dict[str, Any]],
        *,
        processed: int,
        skipped: int,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "message": message,
            "entries": [self.present(entry) for entry in entries],
            "processed": processed,
            "skipped": skipped,
        }
