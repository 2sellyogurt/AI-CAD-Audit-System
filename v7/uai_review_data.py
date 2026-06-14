# -*- coding: utf-8 -*-
# UAI审查结果数据库 — 系统固化模块
# 145检查点 × 逐条实地发现文本证据 → 注入报告问题清单
# 更新方式: 修改 v7/data/uai_review_data.json → unified_pipeline.py 自动合并 → 报告刷新

import os
import json
import logging

logger = logging.getLogger(__name__)

# 数据文件路径
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_DATA_FILE = os.path.join(_DATA_DIR, "uai_review_data.json")


def _load_review_data() -> tuple:
    """从JSON文件加载审查数据和严重度修正表"""
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("findings", {}), data.get("severity_adjust", {})
    except FileNotFoundError:
        logger.warning(f"审查数据文件不存在: {_DATA_FILE}，使用空数据")
        return {}, {}
    except json.JSONDecodeError as e:
        logger.error(f"审查数据文件JSON解析失败: {e}")
        return {}, {}
    except Exception as e:
        logger.error(f"加载审查数据失败: {e}")
        return {}, {}


# 延迟加载：首次访问时从JSON读取
_UAI_FINDINGS_CACHE = None
_SEVERITY_ADJUST_CACHE = None


def _get_uai_findings() -> dict:
    """获取UAI审查发现数据（懒加载）"""
    global _UAI_FINDINGS_CACHE
    if _UAI_FINDINGS_CACHE is None:
        findings, _ = _load_review_data()
        _UAI_FINDINGS_CACHE = findings
    return _UAI_FINDINGS_CACHE


def _get_severity_adjust() -> dict:
    """获取严重度修正表（懒加载）"""
    global _SEVERITY_ADJUST_CACHE
    if _SEVERITY_ADJUST_CACHE is None:
        _, severity_adjust = _load_review_data()
        _SEVERITY_ADJUST_CACHE = severity_adjust
    return _SEVERITY_ADJUST_CACHE


# 向后兼容：保留原有变量名，但改为动态属性访问
class _LazyDict:
    """延迟加载的字典包装器，保持与原有代码的兼容性"""
    def __init__(self, loader_func):
        self._loader = loader_func
        self._data = None

    def _ensure_loaded(self):
        if self._data is None:
            self._data = self._loader()

    def __getitem__(self, key):
        self._ensure_loaded()
        return self._data[key]

    def __contains__(self, key):
        self._ensure_loaded()
        return key in self._data

    def __iter__(self):
        self._ensure_loaded()
        return iter(self._data)

    def __len__(self):
        self._ensure_loaded()
        return len(self._data)

    def get(self, key, default=None):
        self._ensure_loaded()
        return self._data.get(key, default)

    def items(self):
        self._ensure_loaded()
        return self._data.items()

    def keys(self):
        self._ensure_loaded()
        return self._data.keys()

    def values(self):
        self._ensure_loaded()
        return self._data.values()


# 向后兼容的导出
UAI_FINDINGS = _LazyDict(_get_uai_findings)
SEVERITY_ADJUST = _LazyDict(_get_severity_adjust)
