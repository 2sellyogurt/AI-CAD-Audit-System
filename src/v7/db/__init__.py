# -*- coding: utf-8 -*-
"""v7.0 数据库层 — SQLite 持久化

管理所有配置、审查结果、版本历史的持久化存储。
"""

from .schema import get_db, init_db, SCHEMA_VERSION
from .migrate import auto_migrate

__all__ = ["get_db", "init_db", "auto_migrate", "SCHEMA_VERSION"]
