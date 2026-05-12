# -*- coding: utf-8 -*-
"""
在售商品详情：经网页 ``jp.mercari.com/item/m…`` + MITM 截获 items/get 响应，
解析说明中的管理番号 / バーコード → 回写 inventory.mercari_item_id、on_sale_quantity。

标题含「まとめ商品」且说明含「■ 商品内容」与 ``・`` 行时，按订单页同款规则用标题
匹配 on_sale_items → inventory（_resolve_inventory_id_by_bundle_title）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..db_manage.database import DatabaseManager
from ..db_manage.models.on_sale_item import OnSaleItemModel
from .get_order.description_mgmt_ids import (
    _extract_bundle_product_titles,
    _inventory_id_by_barcode,
    _inventory_id_exists,
    _resolve_inventory_id_by_bundle_title,
    parse_order_description_outbound_tokens,
)
from .get_order.mercari_item_get import fetch_mercari_item_get

_FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_MGMT_ID_PATTERN = re.compile(r"管理\s*ID\s*[:：]\s*([0-9０-９\s,，、*xX×]+)", re.IGNORECASE | re.MULTILINE)
_MGMT_BANGO_PATTERN = re.compile(r"管理\s*番号\s*[:：]\s*([0-9０-９\s,，、*xX×]+)", re.MULTILINE)
_BARCODE_PATTERN = re.compile(
    r"バーコード\s*[:：]\s*([0-9A-Za-z０-９\s,，、\-_*xX×]+)",
    re.MULTILINE,
)

_MERCARI_ID_SEP_RE = re.compile(r"[\n,，、\s]+")


def _mercari_response_ok(resp: Any) -> bool:
    if not isinstance(resp, dict):
        return False
    rc = resp.get("result")
    if rc is None:
        return isinstance(resp.get("data"), dict)
    return str(rc).strip().upper() == "OK"


def _on_sale_quantity_from_status(status: Optional[str]) -> int:
    """煤炉 status=on_sale（出售中）计 1 件在售；暂停/交易中/已售等均为 0。"""
    s = (status or "").strip()
    return 1 if s == "on_sale" else 0


def _normalize_mercari_item_id(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    t = str(raw).strip()
    return t or None


def _split_mercari_item_ids(raw: Any) -> List[str]:
    s = str(raw or "").strip()
    if not s:
        return []
    out: List[str] = []
    seen = set()
    for part in _MERCARI_ID_SEP_RE.split(s):
        t = str(part or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _join_mercari_item_ids(ids: List[str]) -> Optional[str]:
    arr = []
    seen = set()
    for v in ids:
        t = str(v or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        arr.append(t)
    return "、".join(arr) if arr else None


def _split_chunks(segment: str) -> List[str]:
    parts: List[str] = []
    for part in re.split(r"[,，、\s]+", segment or ""):
        p = (part or "").strip()
        if p:
            parts.append(p)
    return parts


def _value_and_quantity(token: str) -> Tuple[str, int]:
    """
    支持 token 尾部数量语法：6977850080862*10 / 6977850080862×10 / 6977850080862x10。
    未携带数量时默认 1。
    """
    t = (token or "").translate(_FW_DIGITS).strip()
    if not t:
        return "", 1
    m = re.match(r"^(.*?)(?:\s*[*xX×]\s*(\d+))?$", t)
    if not m:
        return t, 1
    base = (m.group(1) or "").strip()
    qraw = (m.group(2) or "").strip()
    if not qraw:
        return base, 1
    try:
        q = int(qraw)
    except (TypeError, ValueError):
        q = 1
    return base, max(1, q)


def parse_listing_description_tokens_with_quantity(text: Optional[str]) -> List[Dict[str, Any]]:
    """
    解析说明中的管理番号/条码，并保留每个识别值对应数量。
    返回项：{kind: mgmt_id|barcode, value: int|str, quantity: int, raw: str}
    """
    if text is None:
        return []
    s = str(text).strip()
    if not s:
        return []
    spans: List[Tuple[int, str, str]] = []
    for m in _MGMT_ID_PATTERN.finditer(s):
        spans.append((m.start(), "mgmt", m.group(1) or ""))
    for m in _MGMT_BANGO_PATTERN.finditer(s):
        spans.append((m.start(), "mgmt", m.group(1) or ""))
    for m in _BARCODE_PATTERN.finditer(s):
        spans.append((m.start(), "barcode", m.group(1) or ""))
    spans.sort(key=lambda x: x[0])

    out: List[Dict[str, Any]] = []
    for _, kind, chunk in spans:
        for part in _split_chunks(chunk):
            base, qty = _value_and_quantity(part)
            if not base:
                continue
            if kind == "mgmt":
                try:
                    mid = int(base)
                except (TypeError, ValueError):
                    continue
                out.append({"kind": "mgmt_id", "value": mid, "quantity": qty, "raw": part})
            else:
                out.append({"kind": "barcode", "value": str(base).strip(), "quantity": qty, "raw": part})
    return out


def resolve_inventory_id_from_listing_description(text: Optional[str]) -> Optional[int]:
    """
    按说明文中出现顺序，找第一个可映射到本地库存的标识：
    管理 ID / 管理番号 → inventory.id；バーコード → inventory.barcode。
    """
    tokens: List[Tuple[str, Any]] = parse_order_description_outbound_tokens(text)
    for kind, val in tokens:
        if kind == "mgmt_id":
            mid = int(val)
            if _inventory_id_exists(mid):
                return mid
        else:
            bc = str(val).strip()
            inv_id = _inventory_id_by_barcode(bc)
            if inv_id is not None:
                return inv_id
    return None


_MATOME_LISTING_TITLE_MARK = "まとめ商品"


def _is_matome_listing_bundle_by_title_and_description(
    listing_name: Optional[str],
    description: Optional[str],
) -> bool:
    """
    标题含「まとめ商品」且说明中存在「■ 商品内容」小节及至少一条「・」行时，
    按订单页同款逻辑用商品内容标题匹配库存（见 _extract_bundle_product_titles）。
    """
    name = str(listing_name or "").strip()
    if _MATOME_LISTING_TITLE_MARK not in name:
        return False
    desc = str(description or "").strip()
    if not desc:
        return False
    titles = _extract_bundle_product_titles(desc)
    return len(titles) > 0


def extract_mgmt_barcode_hints(text: Optional[str]) -> Dict[str, Any]:
    """便于前端展示：从说明中抽取的管理番号（数字串）与条码串列表（不要求已存在于库）。"""
    tokens = parse_order_description_outbound_tokens(text)
    mgmt: List[int] = []
    barcodes: List[str] = []
    for kind, val in tokens:
        if kind == "mgmt_id":
            mgmt.append(int(val))
        else:
            barcodes.append(str(val).strip())
    return {"management_numbers": mgmt, "barcodes": barcodes}


def _persist_listing_description_for_item(
    request_item_id: str,
    api_item_id: Optional[str],
    description: Optional[str],
) -> None:
    """
    将 items/get 返回的 data.description 写入 on_sale_items.listing_description，
    供在售列表与「查看详情」展示。按多种 item_id 写法匹配本地一行。
    """
    text = description if isinstance(description, str) else None

    keys: List[str] = []
    for x in (api_item_id, request_item_id):
        s = str(x or "").strip()
        if s and s not in keys:
            keys.append(s)
    for s in list(keys):
        if s.startswith("m") and len(s) > 1:
            t2 = s[1:].strip()
            if t2 and t2 not in keys:
                keys.append(t2)
        elif s.isdigit():
            ms = f"m{s}"
            if ms not in keys:
                keys.append(ms)

    for k in keys:
        rows = OnSaleItemModel.find_all(where="TRIM([item_id]) = TRIM(?)", params=(k,), limit=1)
        if not rows:
            continue
        ob = rows[0]
        ob.listing_description = text
        ob.save()
        return


def fetch_detail_and_sync_inventory(
    item_id: str,
    account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    通过浏览器打开商品页并由 MITM 截获 items/get，将 data.id 与在售数量写入匹配到的库存行。

    :return: { api: 原始响应, sync: { updated, inventory_id, mercari_item_id, on_sale_quantity, message } }
    """
    resp = fetch_mercari_item_get(item_id, account_id=account_id)
    sync: Dict[str, Any] = {
        "updated": False,
        "inventory_id": None,
        "mercari_item_id": None,
        "on_sale_quantity": None,
        "message": None,
    }

    if not _mercari_response_ok(resp):
        sync["message"] = "煤炉接口返回非 OK"
        return {"api": resp, "sync": sync}

    data = resp.get("data")
    if not isinstance(data, dict):
        sync["message"] = "响应缺少 data"
        return {"api": resp, "sync": sync}

    desc = data.get("description")
    desc_text = desc if isinstance(desc, str) else None
    listing_name = data.get("name")
    listing_name_str = listing_name if isinstance(listing_name, str) else None

    mid_api = _normalize_mercari_item_id(data.get("id"))
    status = data.get("status")
    on_sale_qty = _on_sale_quantity_from_status(status if isinstance(status, str) else None)

    _persist_listing_description_for_item(str(item_id or "").strip(), mid_api, desc_text)

    hints = extract_mgmt_barcode_hints(desc_text)
    sync["parsed_hints"] = hints
    parsed_tokens = parse_listing_description_tokens_with_quantity(desc_text)
    sync["parsed_tokens"] = parsed_tokens

    matome_bundle = _is_matome_listing_bundle_by_title_and_description(listing_name_str, desc_text)
    sync["matome_bundle"] = matome_bundle

    resolved_lines: List[Dict[str, Any]] = []
    qty_by_inventory: Dict[int, int] = {}
    inv_id: Optional[int] = None

    if matome_bundle:
        bundle_titles = _extract_bundle_product_titles(desc_text)
        sync["bundle_titles"] = bundle_titles
        for title in bundle_titles:
            riv = _resolve_inventory_id_by_bundle_title(title)
            resolved_lines.append(
                {
                    "kind": "bundle_title",
                    "value": title,
                    "quantity": 1,
                    "inventory_id": riv,
                }
            )
            if riv is not None:
                i = int(riv)
                qty_by_inventory[i] = max(qty_by_inventory.get(i, 0), int(on_sale_qty))
        if qty_by_inventory:
            inv_id = sorted(qty_by_inventory.keys())[0]
        sync["resolved_lines"] = resolved_lines
        if not qty_by_inventory:
            sync["message"] = (
                "まとめ商品：说明「■ 商品内容」中的标题未匹配到库存"
                "（与订单页一致：需在售列表存在同标题商品且对应库存已绑定煤炉商品 ID）"
            )
            return {"api": resp, "sync": sync}
    else:
        inv_id = resolve_inventory_id_from_listing_description(desc_text)
        if inv_id is None:
            sync["message"] = (
                "说明中未找到可关联的库存（需「管理ID」「管理番号」对应已存在的库存 id，"
                "或「バーコード」对应已存在的库存条码）"
            )
            return {"api": resp, "sync": sync}

        for token in parsed_tokens:
            kind = str(token.get("kind") or "")
            value = token.get("value")
            qty = int(token.get("quantity") or 1)
            resolved_inv_id: Optional[int] = None
            if kind == "mgmt_id":
                mid = int(value)
                if _inventory_id_exists(mid):
                    resolved_inv_id = mid
            elif kind == "barcode":
                resolved_inv_id = _inventory_id_by_barcode(str(value or "").strip())
            resolved_lines.append(
                {
                    "kind": kind,
                    "value": value,
                    "quantity": qty,
                    "inventory_id": resolved_inv_id,
                }
            )
            if resolved_inv_id is not None:
                qty_by_inventory[resolved_inv_id] = qty_by_inventory.get(resolved_inv_id, 0) + qty

        if not qty_by_inventory and inv_id is not None:
            # 回退兼容：若解析列表为空但旧逻辑能识别到单个库存，按 status 推导 0/1。
            qty_by_inventory[int(inv_id)] = max(0, int(on_sale_qty))
        sync["resolved_lines"] = resolved_lines

    if not mid_api:
        sync["message"] = "响应中缺少商品 id"
        return {"api": resp, "sync": sync}

    db = DatabaseManager()
    try:
        current_rows = db.execute_query(
            """
            SELECT [id], [mercari_item_id], [on_sale_quantity]
            FROM [inventory]
            WHERE TRIM(IFNULL([mercari_item_id], '')) != ''
            """
        )
        matched_ids = set(int(i) for i in qty_by_inventory.keys())
        for iid_raw, mids_raw, osq_raw in current_rows:
            iid = int(iid_raw)
            mids = _split_mercari_item_ids(mids_raw)
            if not mids:
                continue
            if mid_api in mids and iid not in matched_ids:
                # 同一煤炉商品上次关联但本次未命中的库存：仅移除该 mid，不破坏该库存绑定的其他 mid。
                next_mids = [x for x in mids if x != mid_api]
                next_mid_text = _join_mercari_item_ids(next_mids)
                next_osq = 0 if not next_mids else int(osq_raw or 0)
                db.execute_update(
                    """
                    UPDATE [inventory]
                    SET [mercari_item_id] = ?, [on_sale_quantity] = ?
                    WHERE [id] = ?
                    """,
                    (next_mid_text, next_osq, iid),
                )
        for iid, qty in qty_by_inventory.items():
            row = db.execute_query(
                "SELECT [mercari_item_id] FROM [inventory] WHERE [id] = ? LIMIT 1",
                (int(iid),),
            )
            old_mids = _split_mercari_item_ids(row[0][0] if row else None)
            if mid_api not in old_mids:
                old_mids.append(mid_api)
            merged_mid_text = _join_mercari_item_ids(old_mids)
            db.execute_update(
                """
                UPDATE [inventory]
                SET [mercari_item_id] = ?, [on_sale_quantity] = ?
                WHERE [id] = ?
                """,
                (merged_mid_text, int(qty), int(iid)),
            )
    except Exception as exc:
        sync["message"] = f"写入库存失败: {exc}"
        return {"api": resp, "sync": sync}

    sync["updated"] = bool(qty_by_inventory)
    sync["inventory_id"] = int(inv_id) if inv_id is not None else None
    sync["mercari_item_id"] = mid_api
    sync["on_sale_quantity"] = sum(qty_by_inventory.values()) if qty_by_inventory else 0
    sync["inventory_ids"] = sorted(qty_by_inventory.keys())
    sync["inventory_quantity_map"] = {str(k): int(v) for k, v in qty_by_inventory.items()}
    if qty_by_inventory:
        if matome_bundle:
            n = len(qty_by_inventory)
            sync["message"] = (
                f"まとめ商品：已按「■ 商品内容」匹配 {n} 条库存并同步煤炉商品 ID（与订单页 bundle_title 规则一致）"
            )
        else:
            sync["message"] = "已同步煤炉商品 ID 与在售数量"
    else:
        sync["message"] = "未匹配到可写入库存"
    return {"api": resp, "sync": sync}
