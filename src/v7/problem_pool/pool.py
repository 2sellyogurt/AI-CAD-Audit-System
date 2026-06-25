# -*- coding: utf-8 -*-
"""统一问题池

核心能力：
  1. 接收所有Agent/检查点的审查结果 → 标准化为UnifiedIssue
  2. 构建完整溯源链（data_source → processors → verification）
  3. 双路径验证标记（is_dual_verified）
  4. 生成CAD一键定位脚本
  5. 截图路径关联
  6. 导出为标准JSON
"""

from __future__ import annotations

import os
import json
import time
import uuid
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("v7.problem_pool")


@dataclass
class DataSource:
    type: str = ""
    file: str = ""
    entity_id: str = ""
    raw_text: str = ""
    extract_method: str = ""
    extract_time: str = ""
    page: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "file": self.file,
            "entity_id": self.entity_id,
            "raw_text": self.raw_text,
            "extract_method": self.extract_method,
            "extract_time": self.extract_time,
            "page": self.page,
        }


@dataclass
class ProcessorStep:
    module: str = ""
    version: str = ""
    input_summary: str = ""
    output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "version": self.version,
            "input": self.input_summary,
            "output": self.output,
        }


@dataclass
class Verification:
    text_path: Optional[Dict[str, Any]] = None
    visual_path: Optional[Dict[str, Any]] = None
    is_dual_verified: bool = False
    cross_check_result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {"is_dual_verified": self.is_dual_verified}
        if self.text_path:
            result["text_path"] = self.text_path
        if self.visual_path:
            result["visual_path"] = self.visual_path
        if self.cross_check_result:
            result["cross_check_result"] = self.cross_check_result
        return result


@dataclass
class Provenance:
    data_source: DataSource = field(default_factory=DataSource)
    processors: List[ProcessorStep] = field(default_factory=list)
    verification: Verification = field(default_factory=Verification)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_source": self.data_source.to_dict(),
            "processors": [p.to_dict() for p in self.processors],
            "verification": self.verification.to_dict(),
        }


@dataclass
class UnifiedIssue:
    issue_id: str = ""
    professional: str = ""
    checkpoint_id: str = ""
    checkpoint_name: str = ""
    drawing_name: str = ""
    discipline: str = ""

    location: str = ""
    cad_coords: Dict[str, Any] = field(default_factory=dict)
    cad_script: str = ""

    description: str = ""
    standard_code: str = ""
    standard_clause: str = ""
    clause_text: str = ""
    current_value: Any = None
    expected_value: Any = None
    severity: str = "C"
    suggestion: str = ""
    confidence: str = "medium"

    screenshot: str = ""
    provenance: Provenance = field(default_factory=Provenance)

    route_used: str = ""
    model_used: str = ""
    agent_name: str = ""
    create_time: str = ""
    review_status: str = "pending"
    review_comment: str = ""
    reviewed_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "professional": self.professional,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_name": self.checkpoint_name,
            "drawing_name": self.drawing_name,
            "discipline": self.discipline,
            "location": self.location,
            "cad_coords": self.cad_coords,
            "cad_script": self.cad_script,
            "description": self.description,
            "standard_code": self.standard_code,
            "standard_clause": self.standard_clause,
            "clause_text": self.clause_text,
            "current_value": self.current_value,
            "expected_value": self.expected_value,
            "severity": self.severity,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
            "screenshot": self.screenshot,
            "provenance": self.provenance.to_dict(),
            "route_used": self.route_used,
            "model_used": self.model_used,
            "agent_name": self.agent_name,
            "create_time": self.create_time,
            "review_status": self.review_status,
            "review_comment": self.review_comment,
            "reviewed_by": self.reviewed_by,
        }


class ProblemPool:

    def __init__(self):
        self._issues: Dict[str, UnifiedIssue] = {}
        self._compliant_results: List[Dict[str, Any]] = []
        self._issues_by_drawing: Dict[str, List[str]] = {}
        self._issues_by_checkpoint: Dict[str, List[str]] = {}
        self._issues_by_discipline: Dict[str, List[str]] = {}
        self._merge_distance: float = 10.0
        self._lock = threading.Lock()

    @property
    def issues(self):
        """公开的问题字典。"""
        return self._issues

    @property
    def issue_count(self) -> int:
        """当前问题总数。"""
        return len(self._issues)

    def add_from_checkpoint(
        self,
        checkpoint_result,
        text_entity: Optional[Any] = None,
        image_path: str = "",
        agent_name: str = "",
    ) -> str:
        cr = checkpoint_result
        issue = UnifiedIssue(
            issue_id=self._generate_id(cr.checkpoint_id),
            discipline=cr.discipline or "",
            checkpoint_id=cr.checkpoint_id,
            checkpoint_name=cr.checkpoint_name,
            drawing_name=text_entity.file if text_entity else "",
            location=cr.location or "",
            description=cr.description or cr.evidence or "",
            standard_code=cr.standard_code,
            standard_clause=cr.standard_clause,
            current_value=cr.current_value,
            expected_value=cr.expected_value,
            severity=cr.severity or "C",
            suggestion=cr.suggestion or "",
            confidence=cr.confidence,
            route_used=cr.route_used,
            model_used=cr.model_used,
            agent_name=agent_name,
            screenshot=image_path,
            create_time=datetime.now(timezone.utc).isoformat(),
            provenance=Provenance(
                data_source=DataSource(
                    type="dxf_text" if cr.route_used == "text" else "render_png",
                    file=text_entity.file if text_entity else "",
                    entity_id=text_entity.entity_id if text_entity else "",
                    raw_text=text_entity.raw_text if text_entity else "",
                    extract_method="ezdxf_parse" if cr.route_used == "text" else "vision_ocr",
                    extract_time=datetime.now(timezone.utc).isoformat(),
                ),
                processors=[
                    ProcessorStep(
                        module="checkpoint_engine", version="7.0.0",
                        input_summary=cr.checkpoint_id,
                        output=f"{cr.verdict}" if cr.verdict else "",
                    ),
                ],
                verification=Verification(
                    text_path={"model": cr.model_used, "verdict": cr.verdict, "confidence": cr.confidence}
                    if cr.route_used == "text" else None,
                    visual_path={"model": cr.model_used, "verdict": cr.verdict, "confidence": cr.confidence}
                    if cr.route_used == "visual" else None,
                    is_dual_verified=(cr.route_used == "dual"),
                ),
            ),
        )

        if text_entity:
            issue.cad_coords = {
                "x": getattr(text_entity, "x", 0),
                "y": getattr(text_entity, "y", 0),
                "z": getattr(text_entity, "z", 0),
            }
            issue.cad_script = self._generate_cad_script(issue)

        with self._lock:
            self._issues[issue.issue_id] = issue
            # 更新二级索引
            if issue.drawing_name:
                self._issues_by_drawing.setdefault(issue.drawing_name, []).append(issue.issue_id)
            self._issues_by_checkpoint.setdefault(issue.checkpoint_id, []).append(issue.issue_id)
            self._issues_by_discipline.setdefault(issue.discipline, []).append(issue.issue_id)
        
        return issue.issue_id

    def add_issue(self, issue: UnifiedIssue) -> str:
        if not issue.issue_id:
            issue.issue_id = self._generate_id(issue.checkpoint_id)
        if not issue.create_time:
            issue.create_time = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._issues[issue.issue_id] = issue
        return issue.issue_id

    def enhance_dual_path(
        self, issue_id: str, visual_result, image_path: str = ""
    ) -> None:
        with self._lock:
            issue = self._issues.get(issue_id)
            if not issue:
                return
            vr = visual_result
            issue.provenance.verification.visual_path = {
                "model": vr.model_used, "verdict": vr.verdict,
                "confidence": vr.confidence, "evidence": vr.evidence,
            }
            issue.provenance.verification.is_dual_verified = True
            issue.route_used = "dual"
            issue.confidence = vr.confidence if vr.confidence == "high" else issue.confidence
            if image_path:
                issue.screenshot = image_path

    def get(self, issue_id: str) -> Optional[UnifiedIssue]:
        return self._issues.get(issue_id)

    def get_all(self) -> List[UnifiedIssue]:
        return sorted(self._issues.values(), key=lambda i: (
            {"A": 0, "B": 1, "C": 2, "D": 3}.get(i.severity, 9),
            i.create_time,
        ))

    def record_compliance(self, checkpoint_id: str, checkpoint_name: str,
                          severity: str, agent_name: str, confidence: str,
                          drawing_name: str = "", route_used: str = "") -> None:
        with self._lock:
            self._compliant_results.append({
                "checkpoint_id": checkpoint_id,
                "checkpoint_name": checkpoint_name,
                "severity": severity,
                "agent_name": agent_name,
                "confidence": confidence,
                "drawing_name": drawing_name,
                "route_used": route_used,
                "verdict": "合规",
                "timestamp": time.time(),
            })

    def get_compliant_results(self) -> List[Dict[str, Any]]:
        return list(self._compliant_results)

    def get_by_discipline(self, discipline: str) -> List[UnifiedIssue]:
        return [i for i in self._issues.values() if i.discipline == discipline]

    def get_pending_review(self) -> List[UnifiedIssue]:
        return [i for i in self._issues.values() if i.review_status == "pending"]

    def get_dual_verified(self) -> List[UnifiedIssue]:
        return [i for i in self._issues.values() if i.provenance.verification.is_dual_verified]

    def get_single_path(self) -> List[UnifiedIssue]:
        return [i for i in self._issues.values() if not i.provenance.verification.is_dual_verified]

    def count_by_severity(self) -> Dict[str, int]:
        counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for i in self._issues.values():
            counts[i.severity] = counts.get(i.severity, 0) + 1
        return counts

    def count_dual_verified(self) -> int:
        return sum(1 for i in self._issues.values() if i.provenance.verification.is_dual_verified)

    def stats(self) -> Dict[str, Any]:
        sev = self.count_by_severity()
        return {
            "total_issues": len(self._issues),
            "by_severity": sev,
            "dual_verified": self.count_dual_verified(),
            "dual_verified_pct": round(self.count_dual_verified() / max(len(self._issues), 1) * 100, 1),
            "pending_review": len(self.get_pending_review()),
            "by_discipline": self._discipline_stats(),
        }

    def to_list(self) -> List[Dict[str, Any]]:
        return [i.to_dict() for i in self.get_all()]

    def to_json(self, path: str) -> str:
        data = {
            "stats": self.stats(),
            "issues": self.to_list(),
            "export_time": datetime.now(timezone.utc).isoformat(),
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"问题池导出: {path} ({len(self._issues)}个问题)")
        return path

    def _generate_id(self, checkpoint_id: str) -> str:
        ts = int(time.time() * 1000)
        short_uuid = uuid.uuid4().hex[:6]
        return f"{checkpoint_id}-{ts}-{short_uuid}"

    def _generate_cad_script(self, issue: UnifiedIssue) -> str:
        coords = issue.cad_coords
        if not coords or "x" not in coords:
            return ""
        x, y = coords["x"], coords["y"]
        z = coords.get("z", 0)
        scale = 5000
        return (
            f"_.ZOOM _C {x},{y},{z} {scale}\n"
            f"_.CIRCLE {x},{y},{z} 1000\n"
        )

    def _discipline_stats(self) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for i in self._issues.values():
            d = i.discipline or "unknown"
            stats[d] = stats.get(d, 0) + 1
        return stats

    def generate_contradiction_log(
        self, conflict_issues: List[tuple]
    ) -> List[Dict[str, Any]]:
        log = []
        for issue_a, issue_b, conflict_type in conflict_issues:
            log.append({
                "issue_a_id": issue_a.issue_id if hasattr(issue_a, "issue_id") else issue_a,
                "issue_b_id": issue_b.issue_id if hasattr(issue_b, "issue_id") else issue_b,
                "conflict_type": conflict_type,
                "time": datetime.now(timezone.utc).isoformat(),
            })
        return log
