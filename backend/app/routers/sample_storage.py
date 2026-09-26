"""样品留存接口：维护留存样品，覆盖确认处置、申请延期、登记处置等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult, SampleStorageActionPayload
from app.services.sample_storage import SampleStorageService

router = APIRouter(prefix="/api/sample_storage", tags=["样品留存"])

service = SampleStorageService()

LIST_FIELDS = ["留存编号", "样品编号", "留存位置", "留存期限", "到期日期", "保管人员", "处理方式", "留存状态"]
STATUSES = ["留存中", "即将到期", "已处置", "已延期"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按留存编号、样品编号或留存位置检索"),
    status: str | None = Query(default=None, description="留存中、即将到期、已处置、已延期"),
    retention_no: str | None = Query(default=None, alias="留存编号"),
    sample_no: str | None = Query(default=None, alias="样品编号"),
    storage_location: str | None = Query(default=None, alias="留存位置"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按留存编号、样品编号、留存位置与状态过滤列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = {
        "留存编号": retention_no or "",
        "样品编号": sample_no or "",
        "留存位置": storage_location or "",
    }
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        filters=filters,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出样品留存清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "sample_storage", "total": total, "items": items}


@router.post("/actions", response_model=ActionResult)
def run_actions(payload: SampleStorageActionPayload) -> ActionResult:
    """批量处理入口：与列表、详情共用同一份动作判断，空选、中断、重复触发统一收口。"""
    result = service.run_actions(payload.normalized_entry_ids(), payload.normalized_action())
    return ActionResult(**result)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条留存样品明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"留存样品 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条留存样品，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="留存样品已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: SampleStorageActionPayload) -> ActionResult:
    """单条处理入口：复用批量处理规则，保证同一记录在任何入口得到同一结果。"""
    entry_ids = payload.normalized_entry_ids() or [entry_id]
    if entry_id not in entry_ids:
        entry_ids.append(entry_id)
    result = service.run_actions(entry_ids, payload.normalized_action())
    entry = result["entries"][0] if result["entries"] else None
    return ActionResult(
        ok=result["ok"],
        message=result["message"],
        entry=entry,
        entries=result["entries"],
        processed=result["processed"],
        skipped=result["skipped"],
    )
