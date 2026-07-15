# -*- coding: utf-8 -*-
"""结算：按商品归属人分账。

选定日期范围内，按「商品归属人」（inventory.owner_user_id → users）汇总订单净收益，
金额口径与订单管理一致（复用 OrderModel.aggregate_sums 的归属拆分）。
耗材由前端页面手动录入总额，再按各归属人净收益占比分摊，故本接口只负责给出
各归属人的净收益等基础数据，分摊与最终应结金额在前端实时计算。
"""

from typing import Any, Dict, List, Optional

from fastapi import Query

from .....db_manage.database import DatabaseManager
from .....db_manage.models.orders.order import OrderModel

_db = DatabaseManager()


def _time_col(by_purchase_time: bool) -> str:
    """与 OrderModel._build_list_filter 一致的时间列口径。"""
    return (
        "o.purchase_time"
        if by_purchase_time
        else "COALESCE(o.order_updated_at, o.purchase_time, o.order_date)"
    )


def _list_owners_in_range(
    start_ts: Optional[int],
    end_ts: Optional[int],
    by_purchase_time: bool,
) -> List[Dict[str, Any]]:
    """列出该时间段内、有非取消订单商品的归属人（去重）。"""
    tcol = _time_col(by_purchase_time)
    sql = f"""
        SELECT DISTINCT p.[owner_user_id],
               COALESCE(u.[display_name], u.[username]) AS owner_name
        FROM [orders] o
        JOIN [order_outbound_lines] l ON l.[order_no] = o.[order_no]
        JOIN [inventory] p ON p.[id] = l.[inventory_id]
        LEFT JOIN [users] u ON u.[id] = p.[owner_user_id]
        WHERE o.[status] != 'cancelled'
          AND p.[owner_user_id] IS NOT NULL
    """
    params: List[Any] = []
    if start_ts is not None:
        sql += f" AND {tcol} >= ?"
        params.append(int(start_ts))
    if end_ts is not None:
        sql += f" AND {tcol} <= ?"
        params.append(int(end_ts))
    rows = _db.execute_query(sql, tuple(params))

    out: List[Dict[str, Any]] = []
    for oid_raw, name_raw in rows:
        try:
            oid = int(oid_raw)
        except (TypeError, ValueError):
            continue
        if oid <= 0:
            continue
        out.append(
            {
                "owner_user_id": oid,
                "owner_name": str(name_raw or "").strip() or f"用户{oid}",
            }
        )
    return out


def settlement_summary(
    start: Optional[int] = Query(None, description="起始时间（unix 秒，含）"),
    end: Optional[int] = Query(None, description="结束时间（unix 秒，含）"),
    by_purchase_time: bool = Query(False, description="是否仅按购入时间筛选"),
) -> Dict[str, Any]:
    """按商品归属人给出该时段各人的订单净收益等汇总。

    - rows: 每个归属人的 order_count / sum_amount / sum_service_fee /
      sum_shipping_fee / net_income（净收益，口径与订单管理一致）。
    - overall: 该时段全部非取消订单的真实合计（含无归属部分，用于对账）。
    - assigned_net_income: 各归属人净收益之和。
    - unassigned_net_income: overall 净收益 - 已归属净收益（无归属商品部分）。
    """
    owners = _list_owners_in_range(start, end, by_purchase_time)

    rows: List[Dict[str, Any]] = []
    assigned_net = 0
    for ow in owners:
        oid = int(ow["owner_user_id"])
        agg = OrderModel.aggregate_sums(
            start_ts=start,
            end_ts=end,
            owner_user_id=oid,
            by_purchase_time=by_purchase_time,
        )
        net = int(agg.get("sum_net_income") or 0)
        assigned_net += net
        # 该归属人的包材合计（来自「包材使用记录」cost_expenses，口径与订单管理一致）。
        # net_income 已扣除包材，此处仅单独返回用于展示，不再二次扣减。
        packaging = int(
            OrderModel.aggregate_packaging_expense_yen(
                start_ts=start,
                end_ts=end,
                owner_user_id=oid,
                by_purchase_time=by_purchase_time,
            )
            or 0
        )
        rows.append(
            {
                "owner_user_id": oid,
                "owner_name": ow["owner_name"],
                "order_count": int(agg.get("total_count") or 0),
                "sum_amount": int(agg.get("sum_amount") or 0),
                "sum_service_fee": int(agg.get("sum_service_fee") or 0),
                "sum_shipping_fee": int(agg.get("sum_shipping_fee") or 0),
                "packaging": packaging,
                "net_income": net,
            }
        )

    # 净收益从高到低，方便查看
    rows.sort(key=lambda r: r["net_income"], reverse=True)

    overall = OrderModel.aggregate_sums(
        start_ts=start,
        end_ts=end,
        by_purchase_time=by_purchase_time,
    )
    overall_net = int(overall.get("sum_net_income") or 0)
    overall_packaging = int(
        OrderModel.aggregate_packaging_expense_yen(
            start_ts=start,
            end_ts=end,
            by_purchase_time=by_purchase_time,
        )
        or 0
    )

    return {
        "rows": rows,
        "overall": {
            "order_count": int(overall.get("total_count") or 0),
            "sum_amount": int(overall.get("sum_amount") or 0),
            "sum_service_fee": int(overall.get("sum_service_fee") or 0),
            "sum_shipping_fee": int(overall.get("sum_shipping_fee") or 0),
            "packaging": overall_packaging,
            "net_income": overall_net,
        },
        "assigned_net_income": assigned_net,
        "unassigned_net_income": overall_net - assigned_net,
    }
