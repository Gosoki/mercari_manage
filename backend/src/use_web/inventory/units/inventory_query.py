# -*- coding: utf-8 -*-
"""库存查询端点：列表、单条、按条形码、待出库明细。"""
from typing import Optional
from fastapi import HTTPException

from ....db_manage.models.order_outbound_line import OrderOutboundLineModel
from ....use_mercari.mgmt_id_cipher import decode_mgmt_id_cipher

from .inventory_helpers import (
    _query_inventory_with_joins,
    _inventory_exists,
    _sql_inventory_has_image_condition,
)


def list_inventory(
    keyword: Optional[str] = None,
    category_id: Optional[int] = None,
    product_type_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    in_stock_only: bool = False,
    warehouse_assigned_only: bool = False,
    no_image_only: bool = False,
    combined_only: bool = False,
):
    where_parts = []
    params = []
    kw = (keyword or "").strip()
    if kw:
        clauses = ["p.name LIKE ?"]
        kw_params = [f"%{kw}%"]
        # 纯数字 → 按管理番号（inventory.id）精确匹配
        mgmt_id_exact: Optional[int] = None
        if kw.isdigit():
            try:
                n = int(kw)
            except ValueError:
                n = 0
            if n > 0:
                mgmt_id_exact = n
        else:
            # 5 进制管理番号暗号（-=~<>）→ 解码为 inventory.id 精确匹配
            mgmt_id_exact = decode_mgmt_id_cipher(kw)
        if mgmt_id_exact is not None:
            clauses.append("p.id = ?")
            kw_params.append(mgmt_id_exact)
        where_parts.append("AND (" + " OR ".join(clauses) + ")")
        params.extend(kw_params)
    if category_id:
        where_parts.append("AND p.category_id = ?")
        params.append(category_id)
    if product_type_id:
        where_parts.append("AND p.product_type_id = ?")
        params.append(product_type_id)
    if owner_user_id:
        where_parts.append("AND p.owner_user_id = ?")
        params.append(owner_user_id)
    if warehouse_id:
        where_parts.append("AND p.warehouse_id = ?")
        params.append(warehouse_id)
    if in_stock_only:
        where_parts.append("AND COALESCE(p.quantity, 0) > 0")
    if warehouse_assigned_only:
        where_parts.append("AND p.warehouse_id IS NOT NULL")
    if no_image_only:
        where_parts.append(f"AND NOT {_sql_inventory_has_image_condition()}")
    if combined_only:
        where_parts.append("AND COALESCE(p.is_combined, 0) = 1")
    where_sql = " " + " ".join(where_parts) + " ORDER BY p.id DESC"
    return _query_inventory_with_joins(where_sql, tuple(params))


def find_by_barcode(barcode: str):
    """根据条形码精确查找商品（用于连续扫码流程）"""
    inventory_items = _query_inventory_with_joins(" AND p.barcode = ? LIMIT 1", (barcode.strip(),))
    if not inventory_items:
        return {"found": False, "inventory": None}
    return {"found": True, "inventory": inventory_items[0]}


def get_inventory(pid: int):
    inventory_items = _query_inventory_with_joins(" AND p.id = ? LIMIT 1", (pid,))
    if not inventory_items:
        raise HTTPException(status_code=404, detail="商品不存在")
    return inventory_items[0]


def list_inventory_pending_outbound_lines(pid: int):
    """库存展开：该商品在非终态订单中尚未出库的明细行。"""
    if not _inventory_exists(pid):
        raise HTTPException(status_code=404, detail="商品不存在")
    items = OrderOutboundLineModel.list_pending_for_inventory(pid)
    return {"inventory_id": pid, "items": items}
