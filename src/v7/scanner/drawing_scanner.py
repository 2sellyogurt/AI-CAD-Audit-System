# -*- coding: utf-8 -*-
"""图纸理解扫描器 —— 阶段1：一次LLM调用完成建筑理解+Agent路由+检查点筛选

在昂贵的逐检查点审查之前，用一次轻量LLM调用回答：
  1. 这是什么建筑类型？（教学/医疗/住宅/办公...）
  2. 图纸属于哪些楼层/区域？
  3. 涉及哪些专业系统？（消防/结构/暖通/给排水/电气...）
  4. 哪些检查点类别需要优先审查？（A级消防？结构安全？无障碍？）
  5. 总体风险等级？(high/medium/low)

输出 ScanResult → orchestrator 据此决定：
  - 激活哪些 Agent
  - 每个 Agent 跑哪些检查点（优先级过滤）
  - 是否需要视觉路径补充
"""

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("v7.scanner")


@dataclass
class ScanResult:
    building_type: str = "unknown"
    floor_info: str = ""
    total_floors: int = 0
    building_area_hint: str = ""
    risk_level: str = "medium"
    relevant_disciplines: List[str] = field(default_factory=list)
    priority_tags: List[str] = field(default_factory=list)
    suggested_skip_disciplines: List[str] = field(default_factory=list)
    visual_required: bool = False
    notes: str = ""
    raw_response: str = ""
    scan_time_ms: float = 0.0

    def has_discipline(self, disc: str) -> bool:
        if disc in self.suggested_skip_disciplines:
            return False
        if not self.relevant_disciplines:
            return True
        return disc in self.relevant_disciplines or disc == "fire"

    def should_skip_tier(self, severity: str) -> bool:
        if self.risk_level == "low" and severity in ("C", "D"):
            return True
        if self.risk_level == "medium" and severity == "D":
            return True
        return False

    def priority_checkpoint_ids(self) -> List[str]:
        ids = []
        for tag in self.priority_tags:
            ids.append(f"TAG_{tag}")
        return ids


SCAN_PROMPT_TEMPLATE = """你是一位资深建筑审图专家，请快速扫描以下施工图文本内容，回答几个关键问题。

请仔细查看文本中的所有标注、说明、表格、图例。

输出严格JSON格式：
{{
  "building_type": "教学实验楼/医院/住宅/办公/商业/工业厂房/其他",
  "floor_info": "具体楼层描述，如'标准层3-5层'或'地下1层+地上6层'",
  "total_floors": 数字,
  "building_area_hint": "总面积或典型楼层面积描述",
  "risk_level": "high/medium/low（消防风险高、结构复杂的为high）",
  "relevant_disciplines": ["building","fire","structure","hvac","plumbing","electrical"]中实际涉及的，
  "suggested_skip_disciplines": ["hvac","plumbing"]等确实不涉及的，
  "priority_tags": ["疏散","防火分区","结构安全","无障碍","消防系统","给排水","暖通","电气","节能","绿建"]中TOP 5，
  "visual_required": true/false（图纸中是否有纯图形表达的图例、符号、方向箭头等需要视觉识别的内容）,
  "notes": "补充说明，如'图纸标注不全，建议重点人工复核消防系统'"
}}

图纸文本内容：
{drawing_text}
"""


class DrawingScanner:
    _MAX_CACHE_SIZE = 50
    _MAX_TEXT_CHARS = 6000  # 最大文本截断长度

    def __init__(self, llm_factory=None):
        self._llm = llm_factory
        self._cache: Dict[str, ScanResult] = {}
        self._cache_order: List[str] = []

    def _get_llm(self):
        if self._llm is None:
            from v7.llm import LLMFactory
            self._llm = LLMFactory()
        return self._llm

    def scan(self, drawing_texts: str, force_refresh: bool = False) -> ScanResult:
        import hashlib
        text_hash = hashlib.md5(drawing_texts.encode()).hexdigest()

        if text_hash in self._cache and not force_refresh:
            logger.info(f"扫描缓存命中: {text_hash[:8]}")
            return self._cache[text_hash]

        start = time.time()
        result = ScanResult()

        try:
            truncated = drawing_texts[:self._MAX_TEXT_CHARS]
            prompt = SCAN_PROMPT_TEMPLATE.format(drawing_text=truncated)
            logger.debug(f"Scanner prompt length: {len(prompt)}, truncated text: {len(truncated)}")

            llm = self._get_llm()
            raw, provider = llm.call_with_failover(prompt, system="", mode="text")
            result.raw_response = raw[:500]

            data = None
            try:
                from v7.llm.base_adapter import LLMBaseAdapter
                extracted = LLMBaseAdapter.extract_json(raw)
                if extracted:
                    data = json.loads(extracted)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败: {str(e)[:100]}")
            except Exception as e:
                logger.warning(f"提取JSON失败: {str(e)}")

            if data is None:
                try:
                    data = json.loads(raw)
                except Exception as e:
                    logger.debug(f"JSON解析失败: {e}")

            if data and isinstance(data, dict):
                result.building_type = str(data.get("building_type", "unknown"))
                result.floor_info = str(data.get("floor_info", ""))
                # 安全转换：total_floors可能为字符串如"六层"
                tf = data.get("total_floors", 0) or 0
                try:
                    result.total_floors = int(tf)
                except (ValueError, TypeError):
                    # 尝试提取数字
                    import re
                    m = re.search(r'\d+', str(tf))
                    result.total_floors = int(m.group()) if m else 0
                result.building_area_hint = str(data.get("building_area_hint", ""))
                # risk_level白名单校验
                rl = str(data.get("risk_level", "medium")).lower().strip()
                result.risk_level = rl if rl in ("low", "medium", "high") else "medium"
                result.relevant_disciplines = list(data.get("relevant_disciplines", ["building", "fire"]))
                result.suggested_skip_disciplines = list(data.get("suggested_skip_disciplines", []))
                result.priority_tags = list(data.get("priority_tags", []))
                result.visual_required = bool(data.get("visual_required", False))
                result.notes = str(data.get("notes", ""))
            else:
                result.notes = f"LLM返回非JSON，已用默认配置。原始响应: {raw[:300]}"

        except Exception as e:
            result.risk_level = "high"
            result.relevant_disciplines = ["building", "fire"]
            result.notes = f"扫描失败: {str(e)[:200]}"

        result.scan_time_ms = (time.time() - start) * 1000
        
        if text_hash in self._cache:
            self._cache_order.remove(text_hash)
        elif len(self._cache) >= self._MAX_CACHE_SIZE:
            oldest_key = self._cache_order.pop(0)
            del self._cache[oldest_key]
        self._cache[text_hash] = result
        self._cache_order.append(text_hash)

        logger.info(
            f"扫描完成: type={result.building_type}, risk={result.risk_level}, "
            f"disciplines={result.relevant_disciplines}, visual={result.visual_required}, "
            f"{result.scan_time_ms:.0f}ms"
        )
        return result
