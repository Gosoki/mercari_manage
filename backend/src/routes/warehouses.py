# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as PydanticModel
from typing import Optional
from ..db_manage.database import DatabaseManager
from ..db_manage.models.warehouse import WarehouseModel

router = APIRouter(prefix="/api/warehouses", tags=["warehouses"])
db = DatabaseManager()


class WarehouseCreate(PydanticModel):
    name: str  # 货架号（同一仓库内唯一）
    warehouse: Optional[str] = "默认仓库"
    shelf_name: Optional[str] = None  # 货架名称（展示）
    location: Optional[str] = None
    description: Optional[str] = None


class WarehouseUpdate(PydanticModel):
    name: Optional[str] = None
    warehouse: Optional[str] = None
    shelf_name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class RenameWarehouseGroupBody(PydanticModel):
    """将同一展示仓库名下的所有货架位批量改到新仓库名（仅改 warehouse 字段）"""
    old_warehouse: str
    new_warehouse: str


class RenameShelfNameGroupBody(PydanticModel):
    """同一仓库下、同一货架名称（shelf_name）分组批量改为新名称"""
    warehouse: str
    old_shelf_name: Optional[str] = None  # 空串 / None 表示「未设置货架名称」分组
    new_shelf_name: Optional[str] = None  # 空串 / None 表示清空为未设置


def _norm_shelf_name_key(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    t = str(s).strip()
    return t if t else None


def _serialize(wh: WarehouseModel) -> dict:
    d = wh.to_dict()
    d.update(WarehouseModel.get_stats(wh.id))
    return d


@router.get("")
def list_warehouses():
    return [_serialize(w) for w in WarehouseModel.find_all(order_by="id ASC")]


def _safe_remove_default_template_shelf(name: str, exclude_id: int) -> None:
    """
    在非默认仓库新建同名货架后，若默认仓库仍有同名「模板」货架则删除之，
    避免列表里长期保留重复名称；有出入库或库存占用时不删。
    """
    default_key = WarehouseModel.normalize_warehouse_key(None)
    tmpl = WarehouseModel.find_by_warehouse_and_name(default_key, name)
    if not tmpl or tmpl.id == exclude_id:
        return
    wid = tmpl.id
    has_tx = db.execute_query(
        "SELECT 1 FROM [transactions] WHERE warehouse_id = ? OR target_warehouse_id = ? LIMIT 1",
        (wid, wid),
    )
    if has_tx:
        return
    has_inv = db.execute_query(
        "SELECT 1 FROM [inventory] WHERE warehouse_id = ? LIMIT 1",
        (wid,),
    )
    if has_inv:
        return
    has_cost = db.execute_query(
        "SELECT 1 FROM [cost_records] WHERE warehouse_id = ? LIMIT 1",
        (wid,),
    )
    if has_cost:
        return
    tmpl.delete()


@router.post("")
def create_warehouse(data: WarehouseCreate):
    wh_key = WarehouseModel.normalize_warehouse_key(data.warehouse)
    if WarehouseModel.find_by_warehouse_and_name(wh_key, data.name):
        raise HTTPException(status_code=400, detail="该仓库下货架号已存在")
    sn = (data.shelf_name or "").strip() or None
    wh = WarehouseModel(
        name=data.name,
        warehouse=wh_key,
        shelf_name=sn,
        location=data.location,
        description=data.description
    )
    if not wh.save():
        raise HTTPException(status_code=500, detail="保存失败")
    default_key = WarehouseModel.normalize_warehouse_key(None)
    if wh_key != default_key:
        _safe_remove_default_template_shelf(data.name, wh.id)
    return _serialize(wh)


@router.put("/rename-group")
def rename_warehouse_group(data: RenameWarehouseGroupBody):
    old_key = WarehouseModel.normalize_warehouse_key(data.old_warehouse)
    new_key = WarehouseModel.normalize_warehouse_key(data.new_warehouse)
    if old_key == new_key:
        raise HTTPException(status_code=400, detail="新仓库名称与当前相同")
    all_rows = WarehouseModel.find_all(order_by="id ASC")

    def row_wh_key(w: WarehouseModel) -> str:
        return WarehouseModel.normalize_warehouse_key(w.warehouse)

    targets = [w for w in all_rows if row_wh_key(w) == old_key]
    if not targets:
        raise HTTPException(status_code=404, detail="未找到该仓库")
    target_ids = {w.id for w in targets}
    for w in targets:
        other = WarehouseModel.find_by_warehouse_and_name(new_key, w.name)
        if other and other.id not in target_ids:
            raise HTTPException(
                status_code=400,
                detail=f"目标仓库「{new_key}」下已存在货架号「{w.name}」，请先处理冲突后再改名",
            )
    for w in targets:
        w.warehouse = new_key
        if not w.save():
            raise HTTPException(status_code=500, detail="保存失败")
    return {"message": "仓库名称已更新", "updated": len(targets)}


@router.put("/rename-shelf-name-group")
def rename_shelf_name_group(data: RenameShelfNameGroupBody):
    wh_key = WarehouseModel.normalize_warehouse_key(data.warehouse)
    old_key = _norm_shelf_name_key(data.old_shelf_name)
    new_key = _norm_shelf_name_key(data.new_shelf_name)
    if old_key == new_key:
        raise HTTPException(status_code=400, detail="新货架名称与当前相同")

    def row_wh_key(w: WarehouseModel) -> str:
        return WarehouseModel.normalize_warehouse_key(w.warehouse)

    def row_sn_key(w: WarehouseModel) -> Optional[str]:
        return _norm_shelf_name_key(w.shelf_name)

    all_rows = WarehouseModel.find_all(order_by="id ASC")
    targets = [w for w in all_rows if row_wh_key(w) == wh_key and row_sn_key(w) == old_key]
    if not targets:
        raise HTTPException(status_code=404, detail="未找到该货架名称分组")
    for w in targets:
        w.shelf_name = new_key
        if not w.save():
            raise HTTPException(status_code=500, detail="保存失败")
    return {"message": "货架名称已更新", "updated": len(targets)}


@router.put("/{wid}")
def update_warehouse(wid: int, data: WarehouseUpdate):
    wh = WarehouseModel.find_by_id(id=wid)
    if not wh:
        raise HTTPException(status_code=404, detail="仓库不存在")
    next_name = data.name if data.name is not None else wh.name
    next_wh = WarehouseModel.normalize_warehouse_key(
        data.warehouse if data.warehouse is not None else wh.warehouse
    )
    other = WarehouseModel.find_by_warehouse_and_name(next_wh, next_name)
    if other and other.id != wid:
        raise HTTPException(status_code=400, detail="该仓库下货架号已存在")
    if data.name is not None:
        wh.name = data.name
    if data.warehouse is not None:
        wh.warehouse = WarehouseModel.normalize_warehouse_key(data.warehouse)
    if data.shelf_name is not None:
        wh.shelf_name = (data.shelf_name or "").strip() or None
    if data.location is not None:
        wh.location = data.location
    if data.description is not None:
        wh.description = data.description
    wh.save()
    return _serialize(wh)


@router.delete("/{wid}")
def delete_warehouse(wid: int):
    wh = WarehouseModel.find_by_id(id=wid)
    if not wh:
        raise HTTPException(status_code=404, detail="仓库不存在")
    has_tx = db.execute_query(
        "SELECT 1 FROM [transactions] WHERE warehouse_id = ? OR target_warehouse_id = ? LIMIT 1",
        (wid, wid),
    )
    if has_tx:
        raise HTTPException(status_code=400, detail="仓库存在出入库记录，无法删除")
    wh.delete()
    return {"message": "删除成功"}
