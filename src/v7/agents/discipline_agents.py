# -*- coding: utf-8 -*-
"""6个专业Agent + 自由审查Agent

每个Agent=独立的角色人设+专属规范库+图纸过滤+检查点集。
配置统一从 v7.constants.AGENT_CONFIGS 加载，避免硬编码。
"""

import logging
from typing import Any, Dict, List

from v7.constants import AGENT_CONFIGS, CONTENT_DISCIPLINE_KEYWORDS

from .base_agent import BaseAgent, AgentConfig, AgentReport

# 内容级匹配的阈值：需要匹配的关键字数量
_CONTENT_MATCH_THRESHOLD = 2
# 自由审查的最大文本长度
_FREE_REVIEW_MAX_TEXT = 8000


def _filter_with_content_fallback(
    drawing_infos: List[Any],
    primary_disciplines: List[str],
    content_keywords: List[str],
    agent_name: str = "",
) -> List[Any]:
    """专业图纸双重匹配：
    1. discipline 字段精确匹配（来自文件名分类）
    2. content_disciplines / text_content 内容级回退匹配
    3. 当 primary_disciplines 为空时（自由审查），返回所有图纸
    """
    # 自由审查模式：不过滤，返回所有图纸
    if not primary_disciplines:
        return list(drawing_infos)

    matched: List[Any] = []
    unmatched: List[Any] = []

    for d in drawing_infos:
        disc = getattr(d, "discipline", "") or ""
        if disc in primary_disciplines:
            matched.append(d)
        else:
            unmatched.append(d)

    if not content_keywords or not unmatched:
        return matched

    content_matched: List[Any] = []
    for d in unmatched:
        # 检查 content_disciplines（预计算的文本级分类）
        content_discs: list = getattr(d, "content_disciplines", []) or []
        if any(cd in content_discs for cd in primary_disciplines):
            content_matched.append(d)
            continue
        # 检查 text_content 中是否含专业关键字
        text: str = getattr(d, "text_content", "") or getattr(d, "ocr_text", "") or ""
        if text:
                score = sum(1 for kw in content_keywords if kw in text)
                if score >= _CONTENT_MATCH_THRESHOLD:
                    content_matched.append(d)

    if content_matched:
        import logging
        logger = logging.getLogger("v7.agents.discipline")
        names = [getattr(c, "readable_name", "") or getattr(c, "file_path", "") for c in content_matched]
        logger.info(
            f"[{agent_name}] 内容级回退匹配到 {len(content_matched)} 张图纸: "
            + ", ".join(names)
        )
        matched.extend(content_matched)

    return matched


class _ConfigurableAgent(BaseAgent):
    """基于 constants.py 配置动态构建的 Agent 基类。"""

    def __init__(self, agent_id: str):
        cfg = AGENT_CONFIGS.get(agent_id)
        if not cfg:
            raise ValueError(f"未知的 agent_id: {agent_id}")
        self._agent_id = agent_id
        super().__init__(AgentConfig(
            agent_id=agent_id,
            name=cfg["name"],
            discipline=cfg["discipline"],
            role_title=cfg["role_title"],
            experience_years=cfg["experience_years"],
            standards=cfg["standards"],
        ))

    def build_system_prompt(self) -> str:
        return AGENT_CONFIGS[self._agent_id]["system_prompt"]

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        cfg = AGENT_CONFIGS[self._agent_id]
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=cfg.get("primary_disciplines", [cfg["discipline"], "unknown"]),
            content_keywords=cfg.get("content_keywords", []),
            agent_name=self.config.name,
        )


class BuildingAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_building")


class StructureAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_structure")


class HvacAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_hvac")


class PlumbingAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_plumbing")


class ElectricalAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_electrical")


class FireAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_fire")

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        cfg = AGENT_CONFIGS["agent_fire"]
        fire_keywords = cfg.get("fire_keywords", cfg.get("content_keywords", []))
        results = []
        for d in drawing_infos:
            disc = getattr(d, "discipline", "")
            text = getattr(d, "text_content", "") or ""
            if disc == "fire":
                results.append(d)
            elif disc != "fire" and any(kw in text for kw in fire_keywords):
                results.append(d)
        return results


class FreeReviewAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_free_review")

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return list(drawing_infos)

    def get_checkpoints(self) -> List[Any]:
        return []

    def execute(self, drawing_infos, problem_pool=None, image_paths=None):
        """自由审查不走检查点，直接对图纸文本做开放式审查，结果接入问题池。"""
        import json
        import time
        from v7.llm import LLMFactory
        from v7.problem_pool import UnifiedIssue, Provenance, DataSource
        from v7.checkpoints import CheckResult
        from v7.checkpoints.templates.prompt_templates import _get_symbol_context

        start = time.time()
        self._report = AgentReport(
            agent_id=self.config.agent_id,
            agent_name=self.config.name,
            discipline=self.config.discipline,
        )

        drawings = self.filter_drawings(drawing_infos)
        if not drawings:
            self._report.total_time_ms = (time.time() - start) * 1000
            return self._report

        llm_factory = LLMFactory()
        symbol_ctx = _get_symbol_context()
        merged_text = "\n\n=====\n\n".join(
            f"【{getattr(d, 'readable_name', '')}】\n{getattr(d, 'text_content', '') or ''}"
            for d in drawings
        )
        if not merged_text or len(merged_text) < 200:
            self._report.total_time_ms = (time.time() - start) * 1000
            return self._report

        try:
            prompt = (
                f"{self.build_system_prompt()}\n\n"
                f"请审查以下施工图纸的标注内容，找出所有你认为不符合规范、不合理、或值得关注的问题。\n"
                f"对于每个问题，必须提供：问题描述、规范依据、整改建议。\n\n"
                f"{symbol_ctx}"
                f"【合并图纸文本内容】\n{merged_text[:_FREE_REVIEW_MAX_TEXT]}\n\n"
                f'输出格式：{{"findings": [{{"description": "...", "standard": "...", "suggestion": "..."}}]}}'
            )
            raw, provider = llm_factory.call_with_failover(prompt, system="", mode="text")
            self._report.executed += 1

            findings = []
            try:
                from v7.llm.base_adapter import LLMBaseAdapter
                extracted = LLMBaseAdapter.extract_json(raw)
                if extracted:
                    parsed = json.loads(extracted)
                    findings = parsed.get("findings", [])
            except Exception as e:
                logger = logging.getLogger("v7.agents.discipline")
                logger.warning(f"自由审查结果解析失败: {str(e)}")

            all_names = ", ".join(getattr(d, "readable_name", "") for d in drawings)
            for finding in findings:
                issue = UnifiedIssue(
                    issue_id=f"FREE-{self._report.executed}-{len(findings)}",
                    checkpoint_id="FREE_REVIEW",
                    checkpoint_name=finding.get("description", "自由审查发现")[:50],
                    professional=self.config.discipline,
                    description=finding.get("description", ""),
                    severity="B",
                    suggestion=finding.get("suggestion", ""),
                    standard_code=finding.get("standard_code", finding.get("standard", "")),
                    standard_clause="",
                    drawing_name=all_names,
                    location=finding.get("location", ""),
                    route_used="text",
                    provenance=Provenance(
                        data_source=DataSource(
                            type="dxf_text",
                            file=all_names,
                            raw_text=finding.get("description", "")[:200],
                            extract_method="free_review_agent",
                        ),
                    ),
                    create_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
                if problem_pool:
                    problem_pool.add_issue(issue)
                    self._report.issues_found += 1

        except Exception as e:
            logger = logging.getLogger("v7.agents.discipline")
            logger.error(f"自由审查执行失败: {e}")
            self._report.errors += 1

        self._report.total_time_ms = (time.time() - start) * 1000
        return self._report


class CurtainWallAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_curtain_wall")


class DecorationAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_decoration")


class LandscapeAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_landscape")


class FoundationPitAgent(_ConfigurableAgent):
    def __init__(self):
        super().__init__("agent_foundation_pit")
