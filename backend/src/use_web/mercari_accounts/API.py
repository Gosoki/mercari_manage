# -*- coding: utf-8 -*-
"""煤炉账号管理 API 模块。

层级蓝图注册：
- 从 use_web/API.py 接收前缀 /mercariV2/src/use_web/mercari_accounts
- 完整 URL 示例: GET /mercariV2/src/use_web/mercari_accounts/
"""
from fastapi import APIRouter

from .units.mercari_accounts_crud import (
    create_mercari_account,
    delete_mercari_account,
    list_mercari_accounts,
    update_mercari_account,
)
from .units.mercari_accounts_mitm import (
    fetch_auth_via_mitm,
    fetch_seller_id_via_mitm,
)
from .units.mercari_accounts_sync import sync_account_all_data

router = APIRouter()

router.add_api_route("", list_mercari_accounts, methods=["GET"])
router.add_api_route("", create_mercari_account, methods=["POST"])
router.add_api_route("/{aid}", update_mercari_account, methods=["PUT"])
router.add_api_route("/fetch-seller-id-via-mitm", fetch_seller_id_via_mitm, methods=["POST"])
router.add_api_route("/{aid}/fetch-auth-via-mitm", fetch_auth_via_mitm, methods=["POST"])
router.add_api_route("/{aid}/sync-data", sync_account_all_data, methods=["POST"])
router.add_api_route("/{aid}", delete_mercari_account, methods=["DELETE"])
