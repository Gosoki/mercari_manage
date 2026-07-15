# -*- coding: utf-8 -*-
"""结算（按商品归属人分账）API。

层级蓝图注册：
- 从 use_web/system/API.py 接收前缀 /mercariV2/src/use_web/system/settlement
- 完整 URL 示例: GET /mercariV2/src/use_web/system/settlement/summary
"""

from fastapi import APIRouter

from .units.settlement_handler import settlement_summary
from .units.settlement_records import (
    delete_settlement,
    list_settled_ranges,
    list_settlements,
    save_settlement,
)

router = APIRouter()

router.add_api_route("/summary", settlement_summary, methods=["GET"])
# 结算记录：保存快照 / 已结区间（禁选） / 列表 / 删除
router.add_api_route("/records", save_settlement, methods=["POST"])
router.add_api_route("/records", list_settlements, methods=["GET"])
router.add_api_route("/settled-ranges", list_settled_ranges, methods=["GET"])
router.add_api_route("/records/{rid}", delete_settlement, methods=["DELETE"])
