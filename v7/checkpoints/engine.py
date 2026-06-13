# -*- coding: utf-8 -*-
"""参数化检查点引擎

YAML驱动检查点管理：
  加载 → 验证 → 填充Prompt模板 → 路由决策 → 执行审查 → 解析结果

核心能力：
  - 15种检查类型（dimension_min/max/range、text_presence/absence等）
  - 双路径路由（text/visual/dual）
  - A级检查点强制升级为dual
  - 结果标准化为CheckResult
  - 批量执行+统计
"""

from __future__ import annotations

import os
import re
import time
import glob
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .checkpoint_schema import (
    CheckType, Route, Severity, Discipline, ExecutionStatus,
    CheckpointDefinition, CheckResult, CheckBatchResult,
)
from .templates.prompt_templates import build_text_prompt, build_vision_prompt

logger = logging.getLogger("v7.checkpoints")


class CheckpointEngine:

    def __init__(self, definitions_dir: str = "", llm_factory=None):
        if not definitions_dir:
            definitions_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "checkpoints", "definitions"
            )
        self._definitions_dir = definitions_dir
        self._llm = llm_factory
        self._checkpoints: Dict[str, CheckpointDefinition] = {}
        self._by_discipline: Dict[str, List[CheckpointDefinition]] = {}
        self._by_type: Dict[str, List[CheckpointDefinition]] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._checkpoints.clear()
        self._by_discipline.clear()
        self._by_type.clear()

        yaml_files = glob.glob(os.path.join(self._definitions_dir, "*.yaml"))
        yaml_files += glob.glob(os.path.join(self._definitions_dir, "*.yml"))

        for yaml_file in sorted(yaml_files):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not data:
                    continue
                checkpoints_data = data.get("checkpoints", [data] if isinstance(data, dict) else data)
                if isinstance(checkpoints_data, dict):
                    checkpoints_data = [checkpoints_data]
                for item in checkpoints_data:
                    if not isinstance(item, dict) or not item.get("id"):
                        continue
                    cp = CheckpointDefinition.from_yaml(item)
                    if cp.enabled:
                        self._checkpoints[cp.id] = cp
                        disc = cp.discipline.value
                        ctype = cp.check_type.value
                        self._by_discipline.setdefault(disc, []).append(cp)
                        self._by_type.setdefault(ctype, []).append(cp)
            except Exception as e:
                logger.error(f"加载检查点文件失败: {yaml_file}: {e}", exc_info=True)

        logger.info(f"检查点引擎加载完成: {len(self._checkpoints)}个检查点, "
                     f"{len(self._by_discipline)}个专业, {len(self._by_type)}种类型")

    def reload(self) -> None:
        self._load_all()

    @property
    def all_checkpoints(self) -> List[CheckpointDefinition]:
        return sorted(self._checkpoints.values(), key=lambda c: (c.discipline.value, c.priority), reverse=True)

    @property
    def total_count(self) -> int:
        return len(self._checkpoints)

    def get(self, checkpoint_id: str) -> Optional[CheckpointDefinition]:
        return self._checkpoints.get(checkpoint_id)

    def list_by_discipline(self, discipline: str) -> List[CheckpointDefinition]:
        return sorted(self._by_discipline.get(discipline, []), key=lambda c: c.priority, reverse=True)

    def list_by_type(self, check_type: str) -> List[CheckpointDefinition]:
        return self._by_type.get(check_type, [])

    def resolve_route(self, cp: CheckpointDefinition) -> Route:
        if cp.route == Route.DUAL:
            return Route.DUAL
        if cp.severity in (Severity.A, Severity.B):
            return Route.DUAL
        return cp.route

    def execute_one(
        self,
        checkpoint: CheckpointDefinition,
        text_context: str = "",
        image_paths: Optional[List[str]] = None,
    ) -> CheckResult:
        """执行单个检查点审查。"""
        start_time = time.time()
        route = self.resolve_route(checkpoint)
        result = CheckResult(
            checkpoint_id=checkpoint.id,
            checkpoint_name=checkpoint.name,
            severity=checkpoint.severity.value,
            standard_code=checkpoint.standard_code,
            standard_clause=checkpoint.standard_clause,
            execution_status=ExecutionStatus.EXECUTED,
            attempt_time=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start_time)),
        )

        try:
            if route in (Route.TEXT, Route.DUAL) and text_context:
                text_result = self._execute_text_path(checkpoint, text_context)
                if route == Route.TEXT:
                    return text_result
                result = text_result

            if route in (Route.VISUAL, Route.DUAL) and image_paths:
                vis_result = self._execute_vision_path(checkpoint, image_paths)
                if route == Route.VISUAL:
                    return vis_result
                if route == Route.DUAL:
                    if result.verdict and vis_result.verdict:
                        if vis_result.confidence == "high" and result.confidence != "high":
                            result = vis_result
                        result.route_used = "dual"
                        result.model_used += f"+{vis_result.model_used}"
        except Exception as e:
            result.verdict = "待核实"
            result.confidence = "low"
            result.error = str(e)
            result.execution_status = ExecutionStatus.FAILED
            result.failure_reason = str(e)

        result.execution_status = ExecutionStatus.EXECUTED
        result.processing_time_ms = (time.time() - start_time) * 1000
        return result

    def _execute_text_path(self, cp: CheckpointDefinition, text: str) -> CheckResult:
        start = time.time()
        from v7.llm import LLMFactory
        prompt = build_text_prompt(cp, text)
        raw, provider = LLMFactory().call_with_failover(prompt, system="", mode="text")
        return self._parse_result(cp, raw, "text", provider, start)

    def _execute_vision_path(self, cp: CheckpointDefinition, image_paths: List[str]) -> CheckResult:
        start = time.time()
        from v7.llm import LLMFactory
        from v7.preprocessor.image_enhancer import enhance_png
        from v7.preprocessor.grid_splitter import split_to_grid, cleanup_grids

        # 步骤1：对每张原始图纸做图像增强（对比度/锐化），提高视觉模型识别率
        enhanced_paths = []
        for img_path in image_paths:
            if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                enhanced = enhance_png(img_path)
                enhanced_paths.append(enhanced)

        # 步骤2：将增强后的图纸按内容密度切分为多个网格子图，便于视觉模型逐格审查
        all_grids = []
        for enhanced_path in enhanced_paths:
            grids, _ = split_to_grid(enhanced_path, min_density=0.005)
            all_grids.extend(grids)

        try:
            # 分支A：网格数≤3，将全部网格合并送一次视觉模型审查（速度快，适合简单图纸）
            if len(all_grids) <= 3:
                prompt = build_vision_prompt(cp, len(all_grids))
                raw, provider = LLMFactory().call_with_failover(
                    prompt, system="", mode="vision",
                    image_paths=all_grids, complex_vision=(cp.severity in (Severity.A,))
                )
                result = self._parse_result(cp, raw, "visual", provider, start)
                result.route_used = "visual"
                result.model_used = f"{provider}(enhanced)"
                return result
            else:
                # 分支B：网格数>3，逐格送视觉模型审查，收集所有不合规结果后取置信度最高的
                provider_used = ""
                grid_results = []
                grid_prompt = build_vision_prompt(cp, 1)
                for grid_path in all_grids:
                    raw, provider = LLMFactory().call_with_failover(
                        grid_prompt, system="", mode="vision",
                        image_paths=[grid_path], complex_vision=(cp.severity in (Severity.A,))
                    )
                    provider_used = provider
                    parsed = self._parse_result(cp, raw, "visual", provider, start)
                    if parsed.verdict == "不合规":
                        grid_results.append(parsed)

                if grid_results:
                    best = max(grid_results, key=lambda r: (
                        2 if r.confidence == "high" else 1 if r.confidence == "medium" else 0
                    ))
                    best.route_used = "visual"
                    best.model_used = f"{provider_used}(grid_{len(all_grids)})"
                    best.processing_time_ms = (time.time() - start) * 1000
                    return best

                result = self._parse_result(cp, "无问题", "visual", provider_used, start)
                result.route_used = "visual"
                result.model_used = f"{provider_used}(grid_{len(all_grids)}_all_ok)"
                return result
        finally:
            cleanup_grids(all_grids)
            for enhanced_path in enhanced_paths:
                if enhanced_path not in image_paths:
                    try:
                        os.remove(enhanced_path)
                    except OSError:
                        pass

    def _parse_result(
        self, cp: CheckpointDefinition, raw: str, route: str, provider: str, start_time: float
    ) -> CheckResult:
        import json
        result = CheckResult(
            checkpoint_id=cp.id, checkpoint_name=cp.name,
            severity=cp.severity.value,
            standard_code=cp.standard_code, standard_clause=cp.standard_clause,
            route_used=route, model_used=f"{provider}",
            processing_time_ms=(time.time() - start_time) * 1000,
            raw_llm_output=raw[:500],
        )

        raw_stripped = raw.strip()
        if raw_stripped == "无问题" or raw_stripped.startswith("无问题"):
            result.verdict = "合规"
            result.confidence = "high"
            return result

        try:
            extracted = LLMBaseAdapter.extract_json(raw)
            data = json.loads(extracted)
            result.verdict = data.get("verdict", "待核实")
            result.confidence = data.get("confidence", "medium")
            result.evidence = data.get("evidence", "")
            desc = data.get("description", "")
            if desc and not desc.startswith("{") and not desc.startswith("```"):
                result.description = desc
            result.current_value = data.get("current_value", "")
            result.expected_value = data.get("expected_value", str(cp.limit_value) if cp.limit_value else "")
            sug = data.get("suggestion", cp.suggestion_template or "")
            if sug and not sug.startswith("{") and not sug.startswith("```"):
                result.suggestion = sug
            result.location = data.get("location", data.get("location_hint", ""))
        except Exception:
            if "不合规" in raw or "不符合" in raw or "不满足" in raw:
                result.verdict = "不合规"
                result.confidence = "low"
                clean_evidence = re.sub(r'```json\s*|\s*```', '', raw)
                clean_evidence = re.sub(r'\{[^{}]*"verdict"\s*:\s*"[^"]*"[^{}]*\}', '', clean_evidence)
                clean_evidence = re.sub(r'\s{2,}', ' ', clean_evidence).strip()
                result.evidence = clean_evidence[:300] if clean_evidence else raw[:300]
            elif "合规" in raw:
                result.verdict = "合规"
                result.confidence = "low"
            else:
                result.verdict = "待核实"
                result.confidence = "low"

        return result

    def execute_batch(
        self,
        checkpoints: List[CheckpointDefinition],
        text_context: str = "",
        image_paths: Optional[List[str]] = None,
        max_concurrent: int = 5,
    ) -> List[CheckResult]:
        results = []
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(self.execute_one, cp, text_context, image_paths): cp
                for cp in checkpoints
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    cp = futures[future]
                    results.append(CheckResult(
                        checkpoint_id=cp.id, checkpoint_name=cp.name,
                        verdict="待核实", confidence="low", error=str(e),
                    ))
        return results

    def execute_by_discipline(
        self, discipline: str, text_context: str = "",
        image_paths: Optional[List[str]] = None,
    ) -> List[CheckResult]:
        cps = self.list_by_discipline(discipline)
        return self.execute_batch(cps, text_context, image_paths)

    def get_statistics(self, results: List[CheckResult]) -> Dict[str, Any]:
        stats = {"total": len(results), "compliant": 0, "non_compliant": 0,
                 "pending": 0, "error": 0, "by_severity": {}}
        for result in results:
            if result.verdict == "合规":
                stats["compliant"] += 1
            elif result.verdict == "不合规":
                stats["non_compliant"] += 1
            elif result.error:
                stats["error"] += 1
            else:
                stats["pending"] += 1
            sev = result.severity or "unknown"
            stats["by_severity"].setdefault(sev, 0)
            stats["by_severity"][sev] += 1
        return stats


from v7.llm.base_adapter import LLMBaseAdapter
