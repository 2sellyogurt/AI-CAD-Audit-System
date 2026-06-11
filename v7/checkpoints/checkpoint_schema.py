# -*- coding: utf-8 -*-
"""检查点数据模型

定义检查点的YAML配置结构、检查类型枚举、路由策略。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CheckType(str, Enum):
    DIMENSION_MIN = "dimension_min"
    DIMENSION_MAX = "dimension_max"
    DIMENSION_RANGE = "dimension_range"
    TEXT_PRESENCE = "text_presence"
    TEXT_ABSENCE = "text_absence"
    VALUE_EQUAL = "value_equal"
    VALUE_LIST = "value_list"
    COUNT_MIN = "count_min"
    SPATIAL_RELATION = "spatial_relation"
    CROSS_DISCIPLINE_CONSISTENCY = "cross_discipline"
    FIRE_RATING = "fire_rating"
    SLOPE_CHECK = "slope_check"
    CLEARANCE_CHECK = "clearance_check"
    MATERIAL_SPEC = "material_spec"
    FREE_REVIEW = "free_review"


class Route(str, Enum):
    TEXT = "text"
    VISUAL = "visual"
    DUAL = "dual"


class Severity(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class Discipline(str, Enum):
    BUILDING = "building"
    STRUCTURE = "structure"
    HVAC = "hvac"
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    FIRE = "fire"
    CROSS = "cross"
    CURTAIN_WALL = "curtain_wall"
    LANDSCAPE = "landscape"
    FOUNDATION_PIT = "foundation_pit"
    DECORATION = "decoration"
    BUILDING_EXTRA = "building_extra"
    FACADE = "facade"
    DOOR_WINDOW = "door_window"
    PREFAB = "prefab"
    SUBSTATION = "substation"
    SMART = "smart"
    SUN_SHADE = "sun_shade"
    SIGN = "sign"
    ELEVATOR = "elevator"

    @classmethod
    def _missing_(cls, value: str) -> "Discipline":
        value_lower = value.lower().replace(" ", "_")
        for member in cls:
            if member.value == value_lower:
                return member
        return cls.BUILDING


@dataclass
class CheckpointDefinition:
    id: str
    name: str
    discipline: Discipline
    standard_code: str
    standard_clause: str
    clause_text: str = ""
    check_type: CheckType = CheckType.DIMENSION_MIN
    route: Route = Route.TEXT
    severity: Severity = Severity.B

    target_object: List[str] = field(default_factory=list)
    target_property: str = ""
    operator: str = ""
    limit_value: Any = None
    unit: str = ""
    value_range: Optional[List[Any]] = None
    keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    regex_pattern: str = ""

    description: str = ""
    suggestion_template: str = ""
    priority: int = 0
    enabled: bool = True

    applicable_building_types: List[str] = field(default_factory=list)
    applicable_floors: List[str] = field(default_factory=list)

    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> "CheckpointDefinition":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            discipline=Discipline(data.get("discipline", "building")),
            standard_code=data.get("standard_code", ""),
            standard_clause=data.get("standard_clause", ""),
            clause_text=data.get("clause_text", ""),
            check_type=CheckType(data.get("check_type", "dimension_min")),
            route=Route(data.get("route", "text")),
            severity=Severity(data.get("severity", "B")),
            target_object=data.get("target_object", []),
            target_property=data.get("target_property", ""),
            operator=data.get("operator", ""),
            limit_value=data.get("limit_value"),
            unit=data.get("unit", ""),
            value_range=data.get("value_range"),
            keywords=data.get("keywords", []),
            exclude_keywords=data.get("exclude_keywords", []),
            regex_pattern=data.get("regex_pattern", ""),
            description=data.get("description", ""),
            suggestion_template=data.get("suggestion_template", ""),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            applicable_building_types=data.get("applicable_building_types", []),
            applicable_floors=data.get("applicable_floors", []),
            _raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "discipline": self.discipline.value,
            "standard_code": self.standard_code,
            "standard_clause": self.standard_clause,
            "check_type": self.check_type.value,
            "route": self.route.value,
            "severity": self.severity.value,
            "target_object": self.target_object,
            "target_property": self.target_property,
            "operator": self.operator,
            "limit_value": self.limit_value,
            "unit": self.unit,
            "enabled": self.enabled,
        }


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"
    NO_DRAWINGS = "no_drawings"


@dataclass
class CheckResult:
    checkpoint_id: str
    checkpoint_name: str
    discipline: str = ""  # 所属专业
    verdict: str = ""
    confidence: str = "medium"
    severity: str = ""
    evidence: str = ""
    description: str = ""
    current_value: Any = None
    expected_value: Any = None
    standard_code: str = ""
    standard_clause: str = ""
    suggestion: str = ""
    location: str = ""
    raw_llm_output: str = ""

    route_used: str = ""
    model_used: str = ""
    processing_time_ms: float = 0.0
    error: str = ""

    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    attempt_time: str = ""
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_name": self.checkpoint_name,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "severity": self.severity,
            "evidence": self.evidence,
            "description": self.description,
            "current_value": self.current_value,
            "expected_value": self.expected_value,
            "standard_code": self.standard_code,
            "standard_clause": self.standard_clause,
            "suggestion": self.suggestion,
            "location": self.location,
            "route_used": self.route_used,
            "model_used": self.model_used,
            "processing_time_ms": self.processing_time_ms,
            "error": self.error,
            "execution_status": self.execution_status.value,
            "attempt_time": self.attempt_time,
            "failure_reason": self.failure_reason,
        }


@dataclass
class CheckBatchResult:
    checkpoint_id: str
    total_drawings: int = 0
    issues_found: int = 0
    checks_passed: int = 0
    errors: int = 0
    skipped: int = 0
    results: List[CheckResult] = field(default_factory=list)
    total_time_ms: float = 0.0
    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "total_drawings": self.total_drawings,
            "issues_found": self.issues_found,
            "checks_passed": self.checks_passed,
            "errors": self.errors,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "total_time_ms": self.total_time_ms,
            "execution_status": self.execution_status.value,
            "failure_reason": self.failure_reason,
        }
