# -*- coding: utf-8 -*-
"""
成本支出表模型
"""

from typing import Dict, Any, List
from ..base_model import BaseModel


class CostExpenseModel(BaseModel):
    """成本支出表"""

    @classmethod
    def get_table_name(cls) -> str:
        return "cost_expenses"

    @classmethod
    def get_fields(cls) -> Dict[str, Dict[str, Any]]:
        return {
            'id': {
                'type': 'INTEGER',
                'primary_key': True,
                'autoincrement': True,
                'not_null': True,
            },
            'type': {
                'type': 'TEXT',
                'not_null': True,
                'default': None,
            },
            'item_name': {
                'type': 'TEXT',
                'not_null': True,
                'default': None,
            },
            'entry': {
                'type': 'TEXT',
                'not_null': True,
                'default': '进入',
            },
            'quantity': {
                'type': 'INTEGER',
                'not_null': True,
                'default': 1,
            },
            'unit_price': {
                'type': 'INTEGER',
                'not_null': True,
                'default': 0,
            },
            'owner': {
                'type': 'TEXT',
                'not_null': False,
                'default': None,
            },
            'order_no': {
                'type': 'TEXT',
                'not_null': False,
                'default': None,
            },
            'record_time': {
                'type': 'INTEGER',
                'not_null': True,
                'default': None,
            },
            'created_at': {
                'type': 'DATETIME',
                'not_null': False,
                'default': 'CURRENT_TIMESTAMP',
            },
        }

    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {'name': 'idx_cost_expenses_record_time', 'columns': ['record_time']},
            {'name': 'idx_cost_expenses_type', 'columns': ['type']},
            {'name': 'idx_cost_expenses_owner', 'columns': ['owner']},
            {'name': 'idx_cost_expenses_order_no', 'columns': ['order_no']},
        ]
