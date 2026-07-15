# -*- coding: utf-8 -*-
"""结算（按商品归属人分账）API。

层级蓝图注册：
- 从 use_web/system/API.py 接收前缀 /mercariV2/src/use_web/system/settlement
- 完整 URL 示例: GET /mercariV2/src/use_web/system/settlement/summary
"""

from fastapi import APIRouter

from .units.settlement_handler import settlement_summary

router = APIRouter()

router.add_api_route("/summary", settlement_summary, methods=["GET"])
