# -*- coding: utf-8 -*-
"""跨图纸上下文分析模块

提取多图纸中的关键参数（轴网、楼层、房间标签、关键尺寸），
跨图纸比对一致性，生成跨图纸一致性问题。
"""

from __future__ import annotations

import re
import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("v7.cross_drawing")


@dataclass
class CrossDrawingIssue:
    issue_id: str = ""
    issue_type: str = ""
    severity: str = "B"
    description: str = ""
    suggestion: str = ""
    drawing_a: str = ""
    drawing_b: str = ""
    evidence_a: str = ""
    evidence_b: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "drawing_a": self.drawing_a,
            "drawing_b": self.drawing_b,
            "evidence_a": self.evidence_a,
            "evidence_b": self.evidence_b,
        }


@dataclass
class DrawingMeta:
    name: str = ""
    discipline: str = ""
    text: str = ""
    axis_range_x: Set[str] = field(default_factory=set)
    axis_range_y: Set[str] = field(default_factory=set)
    floor_labels: Set[str] = field(default_factory=set)
    room_labels: Set[str] = field(default_factory=set)
    dimensions: List[Tuple[str, str, str]] = field(default_factory=list)
    elevation_values: List[Tuple[str, str]] = field(default_factory=list)
    fire_ratings: Set[str] = field(default_factory=set)


FLOOR_PATTERN = re.compile(r'([一二三四五六七八九十\d]+|[B][F\d]*|[地下]+\d*)\s*[层Ff]', re.IGNORECASE)
ROOM_LABEL_PATTERN = re.compile(r'([A-Z\u4e00-\u9fff]{2,6})\s*(办公室|实验室|教室|宿舍|卫生间|配电房|机房|控制室|泵房|风机房|电梯厅|前室|走道|楼梯间|门厅|大堂|会议室|资料室|仓库|厨房|餐厅|休息室|更衣室|值班室)', re.IGNORECASE)
DIMENSION_PATTERN = re.compile(r'(?:宽|长|深|高|净宽|净高|间距|距离|开间|进深|跨)[度]?\s*[:：]?\s*([\d.]+\s*[mM米毫厘cm])', re.IGNORECASE)
GENERIC_DIM_PATTERN = re.compile(r'(\d{2,5})\s*(?:mm|M\b|米)', re.IGNORECASE)
ELEVATION_PATTERN = re.compile(r'(?:标高|EL|±)\s*[：:]?\s*([+-]?\d+\.?\d*)\s*[mM]?', re.IGNORECASE)
FIRE_RATING_PATTERN = re.compile(r'(?:耐火等级|耐火极限|防火等级)\s*[:：]?\s*([一二三四I]+[级]?)', re.IGNORECASE)
FIRE_RATING_NUM_PATTERN = re.compile(r'[耐]*火[极等限]*[级]*\s*[:：]?\s*(\d+\.?\d*)\s*[hH小]', re.IGNORECASE)

# 预编译 _extract_axis_sets 使用的正则（提取到模块级避免重复编译）
_AXIS_RANGE_X = re.compile(r'[①②③④⑤⑥⑦⑧⑨⑩\d]+[轴轴线]*\s*[-~—–]\s*[①②③④⑤⑥⑦⑧⑨⑩\d]+[轴轴线]*')
_AXIS_RANGE_Y = re.compile(r'[A-HJ-Za-hj-z]+[轴轴线]*\s*[-~—–]\s*[A-HJ-Za-hj-z]+[轴轴线]*')
_AXIS_SINGLE = re.compile(r'(?:[①②③④⑤⑥⑦⑧⑨⑩\d]|[A-HJ-Za-hj-z])\s*[轴轴]')
_MAX_ISSUES_PER_CHECK = 5  # 每个检查方法返回的最大问题数


class CrossDrawingContext:

    _NON_SPATIAL_KEYWORDS = [
        "设计说明", "总说明", "系统图", "目录", "物料表",
        "设计总说明", "门窗设计说明", "幕墙设计说明", "装配式建筑设计总说明",
        "电气总设计说明", "结构设计说明", "园建设计说明",
        "标识标线", "管线", "海绵", "base", "校园base",
    ]

    def __init__(self):
        self._metas: Dict[str, DrawingMeta] = {}

    @classmethod
    def _is_spatial_drawing(cls, name: str) -> bool:
        name_lower = name.lower()
        for kw in cls._NON_SPATIAL_KEYWORDS:
            if kw in name_lower:
                return False
        return True

    def add_drawing(self, name: str, discipline: str, text_content: str) -> None:
        meta = DrawingMeta(name=name, discipline=discipline, text=text_content)
        meta.axis_range_x = self._extract_axis_sets(text_content, "x")
        meta.axis_range_y = self._extract_axis_sets(text_content, "y")
        meta.floor_labels = self._extract_floors(text_content)
        meta.room_labels = self._extract_rooms(text_content)
        meta.dimensions = self._extract_dimensions(text_content)
        meta.elevation_values = self._extract_elevations(text_content)
        meta.fire_ratings = self._extract_fire_ratings(text_content)
        self._metas[name] = meta

    def analyze(self) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        metas = list(self._metas.values())
        if len(metas) < 2:
            return issues

        issues.extend(self._check_axis_consistency(metas))
        issues.extend(self._check_floor_consistency(metas))
        issues.extend(self._check_room_label_consistency(metas))
        issues.extend(self._check_dimension_consistency(metas))
        issues.extend(self._check_elevation_consistency(metas))
        issues.extend(self._check_fire_rating_consistency(metas))

        for i, issue in enumerate(issues):
            issue.issue_id = f"XD-{i+1:03d}"
        return issues

    def get_context_summary(self) -> str:
        if not self._metas:
            return "无跨图纸数据"
        lines = [f"共{len(self._metas)}张图纸参与跨图纸上下文分析："]
        for name, meta in self._metas.items():
            lines.append(
                f"  [{meta.discipline}] {name}: "
                f"轴网({len(meta.axis_range_x)}x{len(meta.axis_range_y)}), "
                f"楼层{len(meta.floor_labels)}, "
                f"房间{len(meta.room_labels)}, "
                f"尺寸{len(meta.dimensions)}处"
            )
        return "\n".join(lines)

    @staticmethod
    def _extract_axis_sets(text: str, direction: str) -> Set[str]:
        values: Set[str] = set()
        pattern = _AXIS_RANGE_X if direction == "x" else _AXIS_RANGE_Y
        for m in pattern.finditer(text):
            values.add(m.group().strip())
        for m in _AXIS_SINGLE.finditer(text):
            values.add(m.group().strip())
        return values

    @staticmethod
    def _extract_floors(text: str) -> Set[str]:
        values: Set[str] = set()
        for m in FLOOR_PATTERN.finditer(text):
            values.add(m.group().strip())
        if not values:
            singles = re.findall(r'(?:一层|二层|三层|四层|五层|六层|地下一层|地下二层|首层|屋面|机房层)', text)
            for s in singles:
                values.add(s)
        return values

    @staticmethod
    def _extract_rooms(text: str) -> Set[str]:
        values: Set[str] = set()
        for m in ROOM_LABEL_PATTERN.finditer(text):
            values.add(m.group().strip())
        return values

    @staticmethod
    def _extract_dimensions(text: str) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for m in DIMENSION_PATTERN.finditer(text):
            context_start = max(0, m.start() - 20)
            context_end = min(len(text), m.end() + 5)
            label = text[context_start:m.start()].strip()
            results.append((label, m.group(1), "explicit"))
        for m in GENERIC_DIM_PATTERN.finditer(text):
            val = int(m.group(1))
            if 100 <= val <= 50000:
                results.append((m.group(0), str(val), "generic"))
        return results[:50]

    @staticmethod
    def _extract_elevations(text: str) -> List[Tuple[str, str]]:
        results: List[Tuple[str, str]] = []
        for m in ELEVATION_PATTERN.finditer(text):
            results.append((m.group(0), m.group(1)))
        return results

    @staticmethod
    def _extract_fire_ratings(text: str) -> Set[str]:
        values: Set[str] = set()
        for m in FIRE_RATING_PATTERN.finditer(text):
            values.add(m.group().strip())
        for m in FIRE_RATING_NUM_PATTERN.finditer(text):
            values.add(f"耐火{float(m.group(1))}h")
        return values

    def _check_axis_consistency(self, metas: List[DrawingMeta]) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        spatial_metas = [m for m in metas if self._is_spatial_drawing(m.name)]
        for i in range(len(spatial_metas)):
            for j in range(i + 1, len(spatial_metas)):
                a, b = spatial_metas[i], spatial_metas[j]
                # 检查 X 方向轴网
                if a.axis_range_x and b.axis_range_x:
                    if a.axis_range_x != b.axis_range_x and len(a.axis_range_x) > 1 and len(b.axis_range_x) > 1:
                        issues.append(CrossDrawingIssue(
                            issue_type="axis_mismatch",
                            severity="A",
                            description=f"跨图纸轴网不一致：{a.name}({a.discipline})与{b.name}({b.discipline})的X向轴网范围不匹配",
                            suggestion=f"核对两图纸轴网定义，确保轴号对应一致。如确属不同分区，需在设计说明中明确分区范围",
                            drawing_a=a.name, drawing_b=b.name,
                            evidence_a=", ".join(sorted(a.axis_range_x)[:10]),
                            evidence_b=", ".join(sorted(b.axis_range_x)[:10]),
                        ))
                # 检查 Y 方向轴网
                if a.axis_range_y and b.axis_range_y:
                    if a.axis_range_y != b.axis_range_y and len(a.axis_range_y) > 1 and len(b.axis_range_y) > 1:
                        issues.append(CrossDrawingIssue(
                            issue_type="axis_mismatch",
                            severity="A",
                            description=f"跨图纸轴网不一致：{a.name}({a.discipline})与{b.name}({b.discipline})的Y向轴网范围不匹配",
                            suggestion=f"核对两图纸轴网定义，确保轴号对应一致。如确属不同分区，需在设计说明中明确分区范围",
                            drawing_a=a.name, drawing_b=b.name,
                            evidence_a=", ".join(sorted(a.axis_range_y)[:10]),
                            evidence_b=", ".join(sorted(b.axis_range_y)[:10]),
                        ))
        return issues[:_MAX_ISSUES_PER_CHECK]

    def _check_floor_consistency(self, metas: List[DrawingMeta]) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        same_disc_metas = defaultdict(list)
        for m in metas:
            same_disc_metas[m.discipline].append(m)

        for disc, disc_metas in same_disc_metas.items():
            if len(disc_metas) < 2:
                continue
            all_floors: Set[str] = set()
            for m in disc_metas:
                all_floors.update(m.floor_labels)
            for m in disc_metas:
                missing = all_floors - m.floor_labels
                if missing and len(m.floor_labels) > 0:
                    issues.append(CrossDrawingIssue(
                        issue_type="floor_coverage",
                        severity="B",
                        description=f"{m.name}({disc})缺少楼层标注：{', '.join(sorted(missing))}在其它{ disc}图纸中出现但本图未标注",
                        suggestion=f"确认{m.name}的楼层适用范围，在图名或说明中标注所覆盖的楼层",
                        drawing_a=m.name, drawing_b="其他同专业图纸",
                        evidence_a=", ".join(sorted(m.floor_labels)),
                        evidence_b=", ".join(sorted(missing)),
                    ))
        return issues[:_MAX_ISSUES_PER_CHECK]

    def _check_room_label_consistency(self, metas: List[DrawingMeta]) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        for i in range(len(metas)):
            for j in range(i + 1, len(metas)):
                a, b = metas[i], metas[j]
                common = a.room_labels & b.room_labels
                if not common:
                    continue
                for room in list(common)[:3]:
                    dm_a = [d for d in a.dimensions if room.split()[0] in d[0]][:1]
                    dm_b = [d for d in b.dimensions if room.split()[0] in d[0]][:1]
                    if dm_a and dm_b and dm_a[0][1] != dm_b[0][1]:
                        issues.append(CrossDrawingIssue(
                            issue_type="room_dimension_mismatch",
                            severity="A",
                            description=f"房间\"{room}\"在不同图纸中尺寸不一致：{a.name}标注{dm_a[0][1]}，{b.name}标注{dm_b[0][1]}",
                            suggestion=f"核实\"{room}\"的正确尺寸，统一各图纸标注",
                            drawing_a=a.name, drawing_b=b.name,
                            evidence_a=dm_a[0][0], evidence_b=dm_b[0][0],
                        ))
        return issues[:_MAX_ISSUES_PER_CHECK]

    def _check_dimension_consistency(self, metas: List[DrawingMeta]) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        building_metas = [m for m in metas if m.discipline == "building" and self._is_spatial_drawing(m.name)]
        structure_metas = [m for m in metas if m.discipline == "structure" and self._is_spatial_drawing(m.name)]
        for bm in building_metas:
            for sm in structure_metas:
                b_dims = {str(d[1]).replace("mm", "").replace("m", "").strip() for d in bm.dimensions}
                s_dims = {str(d[1]).replace("mm", "").replace("m", "").strip() for d in sm.dimensions}
                only_b = b_dims - s_dims
                only_s = s_dims - b_dims
                if len(only_b) > 3 or len(only_s) > 3:
                    issues.append(CrossDrawingIssue(
                        issue_type="cross_discipline_dimension",
                        severity="B",
                        description=f"建筑图{bm.name}与结构图{sm.name}的关键尺寸存在差异，建筑特有{len(only_b)}处，结构特有{len(only_s)}处",
                        suggestion="核对建筑与结构专业的关键控制尺寸是否一致，特别关注轴线间距和总尺寸",
                        drawing_a=bm.name, drawing_b=sm.name,
                        evidence_a="", evidence_b="",
                    ))
        return issues[:_MAX_ISSUES_PER_CHECK]

    def _check_elevation_consistency(self, metas: List[DrawingMeta]) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        spatial_metas = [m for m in metas if self._is_spatial_drawing(m.name)]
        for i in range(len(spatial_metas)):
            for j in range(i + 1, len(spatial_metas)):
                a, b = spatial_metas[i], spatial_metas[j]
                a_vals = set(float(v[1]) for v in a.elevation_values if v[1].replace('.', '').replace('-', '').isdigit())
                b_vals = set(float(v[1]) for v in b.elevation_values if v[1].replace('.', '').replace('-', '').isdigit())
                common_vals = a_vals & b_vals
                if common_vals:
                    continue
                # 改进的基准面判断：同时检查最小值和最大值偏移
                if a_vals and b_vals:
                    min_diff = abs(min(a_vals) - min(b_vals))
                    max_diff = abs(max(a_vals) - max(b_vals)) if len(a_vals) > 1 and len(b_vals) > 1 else min_diff
                    if min_diff < 0.5 and max_diff < 0.5:
                        continue
                    # 系统性偏移（各标高差值一致）→ 不同基准面
                    if len(a_vals) > 1 and len(b_vals) > 1 and abs(min_diff - max_diff) < 0.5:
                        issues.append(CrossDrawingIssue(
                            issue_type="elevation_datum_mismatch",
                            severity="B",
                            description=f"{a.name}({a.discipline})与{b.name}({b.discipline})的标高存在系统性偏移({min_diff:.2f}m)，可能使用了不同的基准面",
                            suggestion="确认两图纸是否使用同一标高基准（如均为±0.000=绝对标高），如不同需换算",
                            drawing_a=a.name, drawing_b=b.name,
                            evidence_a=str(sorted(a_vals)[:5]),
                            evidence_b=str(sorted(b_vals)[:5]),
                        ))
                        continue
                # 非系统性差异：检查单值不匹配
                if a_vals and b_vals and abs(min(a_vals) - min(b_vals)) < 0.5:
                    continue
                if len(a_vals) > 1 and len(b_vals) > 1:
                    issues.append(CrossDrawingIssue(
                        issue_type="elevation_mismatch",
                        severity="B",
                        description=f"{a.name}({a.discipline})与{b.name}({b.discipline})的标高体系不一致，可能使用了不同的基准面",
                        suggestion="确认两图纸是否使用同一标高基准（如均为±0.000=绝对标高），如不同需换算",
                        drawing_a=a.name, drawing_b=b.name,
                        evidence_a=str(sorted(a_vals)[:5]),
                        evidence_b=str(sorted(b_vals)[:5]),
                    ))
        return issues[:_MAX_ISSUES_PER_CHECK]

    def _check_fire_rating_consistency(self, metas: List[DrawingMeta]) -> List[CrossDrawingIssue]:
        issues: List[CrossDrawingIssue] = []
        fire_drawings = [m for m in metas if m.discipline == "fire"]
        building_drawings = [m for m in metas if m.discipline == "building"]
        for fm in fire_drawings:
            for bm in building_drawings:
                if fm.fire_ratings != bm.fire_ratings and fm.fire_ratings and bm.fire_ratings:
                    issues.append(CrossDrawingIssue(
                        issue_type="fire_rating_mismatch",
                        severity="A",
                        description=f"消防图{fm.name}与建筑图{bm.name}的耐火等级标注不一致",
                        suggestion="核对消防设计与建筑设计说明中的耐火等级，必须保持一致",
                        drawing_a=fm.name, drawing_b=bm.name,
                        evidence_a=", ".join(sorted(fm.fire_ratings)),
                        evidence_b=", ".join(sorted(bm.fire_ratings)),
                    ))
        return issues[:_MAX_ISSUES_PER_CHECK]
