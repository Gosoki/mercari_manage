# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as PydanticModel

from ..db_manage.models.cost_expense import CostExpenseModel

router = APIRouter(prefix="/api/cost-expenses", tags=["cost-expenses"])


class CostExpenseCreate(PydanticModel):
    type: str
    item_name: str
    entry: str
    quantity: int
    unit_price: int
    owner: Optional[str] = None
    record_time: Optional[int] = None


class CostExpenseUpdate(PydanticModel):
    type: Optional[str] = None
    item_name: Optional[str] = None
    entry: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[int] = None
    owner: Optional[str] = None
    record_time: Optional[int] = None


def _validate_required_text(value: Optional[str], field_name: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field_name}不能为空")
    return cleaned


def _validate_positive_int(value: Optional[int], field_name: str) -> int:
    if value is None or int(value) <= 0:
        raise HTTPException(status_code=400, detail=f"{field_name}必须大于0")
    return int(value)


def _default_london_ts() -> int:
    return int(datetime.now(ZoneInfo("Europe/London")).timestamp())


@router.get("")
def list_cost_expenses(
    type: Optional[str] = None,
    owner: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
):
    where_parts = ["1=1"]
    params = []
    if type:
        where_parts.append("[type] = ?")
        params.append(type.strip())
    if owner:
        where_parts.append("[owner] = ?")
        params.append(owner.strip())
    if start_time is not None:
        where_parts.append("[record_time] >= ?")
        params.append(int(start_time))
    if end_time is not None:
        where_parts.append("[record_time] <= ?")
        params.append(int(end_time))

    where_clause = " AND ".join(where_parts)
    total = CostExpenseModel.count(where=where_clause, params=tuple(params))
    rows = CostExpenseModel.find_all(
        where=where_clause,
        params=tuple(params),
        order_by="record_time DESC, id DESC",
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [row.to_dict() for row in rows],
    }


@router.post("")
def create_cost_expense(data: CostExpenseCreate):
    row = CostExpenseModel(
        type=_validate_required_text(data.type, "类型"),
        item_name=_validate_required_text(data.item_name, "物品名称"),
        entry=_validate_required_text(data.entry, "进入"),
        quantity=_validate_positive_int(data.quantity, "数量"),
        unit_price=_validate_positive_int(data.unit_price, "单价"),
        owner=(data.owner or "").strip() or None,
        record_time=int(data.record_time) if data.record_time is not None else _default_london_ts(),
    )
    if not row.save():
        raise HTTPException(status_code=500, detail="保存失败")
    return row.to_dict()


@router.put("/{cid}")
def update_cost_expense(cid: int, data: CostExpenseUpdate):
    row = CostExpenseModel.find_by_id(id=cid)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")

    if data.type is not None:
        row.type = _validate_required_text(data.type, "类型")
    if data.item_name is not None:
        row.item_name = _validate_required_text(data.item_name, "物品名称")
    if data.entry is not None:
        row.entry = _validate_required_text(data.entry, "进入")
    if data.quantity is not None:
        row.quantity = _validate_positive_int(data.quantity, "数量")
    if data.unit_price is not None:
        row.unit_price = _validate_positive_int(data.unit_price, "单价")
    if data.owner is not None:
        row.owner = data.owner.strip() or None
    if data.record_time is not None:
        row.record_time = int(data.record_time)

    if not row.save():
        raise HTTPException(status_code=500, detail="更新失败")
    return row.to_dict()


@router.delete("/{cid}")
def delete_cost_expense(cid: int):
    row = CostExpenseModel.find_by_id(id=cid)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not row.delete():
        raise HTTPException(status_code=500, detail="删除失败")
    return {"message": "删除成功"}
