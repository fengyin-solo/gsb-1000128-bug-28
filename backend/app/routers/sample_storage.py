"""样品留存接口：维护留存样品，覆盖确认处置、申请延期、登记处置等动作。

列表页（批量）、详情页（单条）、处理入口弹窗提交到的都是同一套服务规则，
接口层不重复任何状态判断。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    BatchActionPayload,
    BatchActionResult,
    EntryPayload,
    PageResult,
)
from app.services.sample_storage import BatchRuleError, SampleStorageService

router = APIRouter(prefix="/api/sample_storage", tags=["样品留存"])

service = SampleStorageService()

LIST_FIELDS = ["留存编号", "样品编号", "留存位置", "留存期限", "到期日期", "保管人员", "处理方式", "留存状态"]
STATUSES = ["留存中", "即将到期", "已处置", "已延期"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按留存编号检索"),
    status: str | None = Query(default=None, description="留存中、即将到期、已处置、已延期"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按留存编号与状态过滤样品留存列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出样品留存清单：返回当前过滤条件下的全量数据。

    路由需声明在 /{entry_id} 之前，否则 export 会被当成记录 id。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "sample_storage", "total": total, "items": items}


@router.post("/batch", response_model=BatchActionResult)
def run_batch(payload: BatchActionPayload) -> BatchActionResult:
    """批量处理入口：空选拦截、异常中断、重复跳过的统一口径由服务层给出。"""
    try:
        result = service.run_batch(payload.entry_ids, payload.action.strip())
    except BatchRuleError as exc:
        # 空选 / 非法动作属于前置校验失败：一条记录都不会改动。
        return BatchActionResult(ok=False, message=exc.message, action=payload.action)
    return BatchActionResult(**result)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条留存样品，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="留存样品已登记", entry=entry)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条留存样品明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"留存样品 {entry_id} 不存在或已归档")
    return entry


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """详情页单条处置：与批量处理共用同一份判断，结论不会和列表页矛盾。"""
    action = str(payload.values.get("action") or "").strip()
    try:
        result = service.run_batch([entry_id], action)
    except BatchRuleError as exc:
        return ActionResult(ok=False, message=exc.message)
    item = result["items"][0]
    entry = service.get_entry(entry_id)
    return ActionResult(ok=result["ok"] and item["status"] != "blocked", message=item["message"], entry=entry)
