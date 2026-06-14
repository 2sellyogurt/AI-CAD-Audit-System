# -*- coding: utf-8 -*-
"""图签信息提取器 + 结构化数据标注

从DXF图纸中提取图签（Title Block）元数据：
  1. 属性块（ATTRIB）解析 - 按Tag名提取（图名/图号/日期等）
  2. 矩形框+文字关联提取 - 利用标题栏坐标窗口捕获文字
  3. 正则匹配字段含义 - 智能识别工程名称/子项/图名/图号/图别/比例/日期
  4. 结构化输出为JSON/Excel

输出字段：
  file_id, drawing_no, drawing_name, project_name, sub_project,
  discipline, drawing_type, scale, date, version, designer,
  checker, approver, frame_size, bounds
"""

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import ezdxf

try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

logger = logging.getLogger("v7.title_block_extractor")

ATTRIB_TAG_MAP = {
    "图名": "drawing_name",
    "图纸名称": "drawing_name",
    "DRAWING_NAME": "drawing_name",
    "图号": "drawing_no",
    "图纸编号": "drawing_no",
    "DRAWING_NO": "drawing_no",
    "DWG_NO": "drawing_no",
    "工程名称": "project_name",
    "项目名称": "project_name",
    "PROJECT_NAME": "project_name",
    "子项名称": "sub_project",
    "SUB_PROJECT": "sub_project",
    "图别": "drawing_type",
    "图纸类别": "drawing_type",
    "DRAWING_TYPE": "drawing_type",
    "比例": "scale",
    "SCALE": "scale",
    "日期": "date",
    "设计日期": "date",
    "DATE": "date",
    "版次": "version",
    "版本": "version",
    "VERSION": "version",
    "REV": "version",
    "设计": "designer",
    "设计人": "designer",
    "DESIGNER": "designer",
    "DESIGNED_BY": "designer",
    "审核": "checker",
    "审核人": "checker",
    "CHECKER": "checker",
    "CHECKED_BY": "checker",
    "校对": "checker",
    "审定": "approver",
    "批准": "approver",
    "APPROVER": "approver",
    "APPROVED_BY": "approver",
    "图幅": "frame_size",
    "FRAME_SIZE": "frame_size",
    "专业": "discipline",
    "DISCIPLINE": "discipline",
}

TEXT_LABEL_FIELD_MAP = {
    "项目名称": "project_name",
    "PROJECT": "project_name",
    "子项名称": "sub_project",
    "SUBPROJECT": "sub_project",
    "设计号": "design_no",
    "图号": "drawing_no",
    "图名": "drawing_name",
    "分类": "classification",
    "专业": "discipline",
    "版本号": "version",
    "设计阶段": "design_stage",
    "出图日期": "date",
    "专业负责人": "discipline_leader",
    "设计  计算": "designer",
    "设计": "designer",
    "校对": "checker",
    "制图": "drafter",
    "项目经理": "project_manager",
    "设计总负责人": "chief_designer",
    "审核": "checker",
    "审定": "approver",
    "建设单位": "client",
    "OWNER": "client",
    "设计单位": "design_company",
    "DESIGNER": "design_company",
    "合作设计单位": "co_designer",
    "CO-DESIGNER": "co_designer",
    "图幅": "frame_size",
}

FRAME_BLOCK_KEYWORDS = ["Frame", "图框", "frame", "A0", "A1", "A2", "A3", "A4", "Title"]

FIELD_REGEX_PATTERNS = [
    (re.compile(r"工\s*程\s*名\s*称\s*[:：]\s*([^\n]{2,60})"), "project_name"),
    (re.compile(r"项\s*目\s*名\s*称\s*[:：]\s*([^\n]{2,60})"), "project_name"),
    (re.compile(r"子\s*项\s*名\s*称\s*[:：]\s*([^\n]{2,40})"), "sub_project"),
    (re.compile(r"图\s*名\s*[:：]\s*([^\n]{2,40})"), "drawing_name"),
    (re.compile(r"图\s*纸\s*名\s*称\s*[:：]\s*([^\n]{2,40})"), "drawing_name"),
    (re.compile(r"图\s*号\s*[:：]\s*([^\n]{2,30})"), "drawing_no"),
    (re.compile(r"图\s*纸\s*编\s*号\s*[:：]\s*([^\n]{2,30})"), "drawing_no"),
    (re.compile(r"图\s*别\s*[:：]\s*([^\n]{2,20})"), "drawing_type"),
    (re.compile(r"比\s*例\s*[:：]\s*([^\n]{2,20})"), "scale"),
    (re.compile(r"日\s*期\s*[:：]\s*([^\n]{4,30})"), "date"),
    (re.compile(r"版\s*次\s*[:：]\s*([^\n]{2,10})"), "version"),
    (re.compile(r"设\s*计\s*人?\s*[:：]\s*([^\n]{2,10})"), "designer"),
    (re.compile(r"审\s*核\s*人?\s*[:：]\s*([^\n]{2,10})"), "checker"),
    (re.compile(r"校\s*对\s*人?\s*[:：]\s*([^\n]{2,10})"), "checker"),
    (re.compile(r"审\s*定\s*[:：]\s*([^\n]{2,10})"), "approver"),
    (re.compile(r"批\s*准\s*[:：]\s*([^\n]{2,10})"), "approver"),
    (re.compile(r"图\s*幅\s*[:：]\s*([^\n]{2,10})"), "frame_size"),
    (re.compile(r"专\s*业\s*[:：]\s*([^\n]{2,20})"), "discipline"),
    (re.compile(r"设计阶段\s*[:：]\s*([^\n]{2,20})"), "design_stage"),
    (re.compile(r"建设单位\s*[:：]\s*([^\n]{2,60})"), "client"),
]


def _extract_attribs_from_insert(insert_entity) -> Dict[str, str]:
    result = {}
    try:
        if not hasattr(insert_entity, "attribs"):
            return result
        for attrib in insert_entity.attribs:
            tag = attrib.dxf.tag if hasattr(attrib.dxf, "tag") else ""
            value = attrib.dxf.text if hasattr(attrib.dxf, "text") else ""
            if tag and value:
                tag_clean = tag.strip().upper()
                value_clean = value.strip()
                if tag_clean in ATTRIB_TAG_MAP:
                    field = ATTRIB_TAG_MAP[tag_clean]
                    result[field] = value_clean
                result[f"_attrib_{tag_clean}"] = value_clean
    except Exception as e:
        logger.debug(f"属性提取失败: {e}")
    return result


def _extract_texts_in_region(msp, x_min: float, y_min: float, x_max: float, y_max: float) -> List[str]:
    texts = []
    try:
        for e in msp.query('TEXT MTEXT'):
            ip = e.dxf.insert
            tx, ty = ip[0], ip[1]
            if x_min <= tx <= x_max and y_min <= ty <= y_max:
                txt = e.dxf.text if e.dxftype() == "TEXT" else (
                    e.plain_text() if hasattr(e, "plain_text") else "")
                if txt and txt.strip():
                    texts.append(txt.strip())
    except Exception as e:
        logger.debug(f"文本提取失败: {e}")
    return texts


def _apply_field_regex(texts: List[str]) -> Dict[str, str]:
    result = {}
    combined = "\n".join(texts)
    for pat, field in FIELD_REGEX_PATTERNS:
        m = pat.search(combined)
        if m:
            val = m.group(1).strip()
            if val and len(val) > 0:
                if field not in result:
                    result[field] = val
    return result


def _extract_title_block_texts(msp, frame_bounds: Optional[Tuple[float, float, float, float]] = None
                               ) -> List[str]:
    if frame_bounds is None:
        return _extract_texts_in_region(msp, -1e9, -1e9, 1e9, 1e9)
    x0, y0, x1, y1 = frame_bounds
    w = x1 - x0
    h = y1 - y0
    title_zone_h = h * 0.15
    title_zone_x0 = x0
    title_zone_x1 = x1
    title_zone_y0 = y0
    title_zone_y1 = y0 + title_zone_h
    texts = _extract_texts_in_region(msp, title_zone_x0, title_zone_y0,
                                     title_zone_x1, title_zone_y1)
    if len(texts) < 3:
        texts_right = _extract_texts_in_region(msp, x1 - w * 0.3, y0, x1, y1)
        texts.extend(texts_right)
    return texts


def _extract_from_block_definition(block) -> Dict[str, str]:
    result = {}
    try:
        labels = []
        values = []
        for entity in block:
            t = entity.dxftype()
            try:
                ip = entity.dxf.insert
                if t == "TEXT":
                    txt = entity.dxf.text
                    if txt.strip():
                        labels.append((ip[0], ip[1], txt.strip()))
                elif t == "MTEXT":
                    txt = entity.plain_text() if hasattr(entity, "plain_text") else ""
                    if txt.strip():
                        values.append((ip[0], ip[1], txt.strip()))
            except Exception as e:
                logger.debug(f"文本值提取失败: {e}")
                continue

        if not labels or not values:
            return result

        for lx, ly, label_text in labels:
            label_clean = label_text.strip()
            if label_clean not in TEXT_LABEL_FIELD_MAP:
                continue
            field = TEXT_LABEL_FIELD_MAP[label_clean]

            best_val = None
            best_dist = 200.0  # 放宽距离阈值，同时考虑X和Y
            for vx, vy, val_text in values:
                dx = abs(vx - lx)
                dy = abs(vy - ly)
                # 标签右侧的值优先，但允许左右摆动
                dist = (dx * 0.3 + dy * 0.7)  # Y权重更高（同行优先）
                if dist < best_dist:
                    best_dist = dist
                    best_val = val_text

            if best_val:
                if field not in result:
                    result[field] = best_val

    except Exception as e:
        logger.debug(f"正则匹配失败: {e}")
    return result


def _is_frame_block_name(block_name: str) -> bool:
    bn_lower = block_name.lower()
    for kw in FRAME_BLOCK_KEYWORDS:
        if kw.lower() in bn_lower:
            return True
    return False


class TitleBlockExtractor:
    """图签信息提取器"""

    def __init__(self):
        self._drawing_number_cache: Dict[str, str] = {}

    def extract_from_attrib_blocks(self, doc) -> Dict[str, str]:
        msp = doc.modelspace()
        result = {}
        for e in msp.query('INSERT'):
            attribs = _extract_attribs_from_insert(e)
            for k, v in attribs.items():
                if not k.startswith("_attrib_") and k not in result:
                    result[k] = v
        return result

    def extract_from_frame_text(self, msp, frame_bounds: Tuple[float, float, float, float]
                                ) -> Dict[str, str]:
        texts = _extract_title_block_texts(msp, frame_bounds)
        return _apply_field_regex(texts)

    def extract_from_global_text(self, msp) -> Dict[str, str]:
        texts = []
        for e in msp.query('TEXT MTEXT'):
            try:
                txt = e.dxf.text if e.dxftype() == "TEXT" else (
                    e.plain_text() if hasattr(e, "plain_text") else "")
                if txt and txt.strip():
                    texts.append(txt.strip())
            except Exception as e:
                logger.debug(f"文本提取失败: {e}")
                continue
        return _apply_field_regex(texts)

    def extract_from_frame_blocks(self, doc) -> Dict[str, str]:
        result = {}
        msp = doc.modelspace()
        for e in msp.query('INSERT'):
            bn = e.dxf.name
            if not _is_frame_block_name(bn):
                continue
            if bn not in doc.blocks:
                continue
            block = doc.blocks[bn]
            frame_data = _extract_from_block_definition(block)
            for k, v in frame_data.items():
                if k not in result:
                    result[k] = v
        return result

    def extract(self, dxf_path: str,
                frames: Optional[List[Tuple[str, float, float, float, float]]] = None
                ) -> Dict[str, Any]:
        file_name = os.path.basename(dxf_path)
        result = {
            "file_id": file_name,
            "file_path": dxf_path,
            "drawing_no": "",
            "drawing_name": "",
            "project_name": "",
            "sub_project": "",
            "discipline": "",
            "drawing_type": "",
            "scale": "",
            "date": "",
            "version": "",
            "designer": "",
            "checker": "",
            "approver": "",
            "frame_size": "",
            "frame_count": 0,
            "frame_metadata": [],
            "client": "",
            "design_company": "",
            "design_no": "",
            "discipline_leader": "",
            "project_manager": "",
            "chief_designer": "",
            "drafter": "",
            "classification": "",
            "design_stage": "",
            "co_designer": "",
        }

        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
        except Exception as e:
            logger.error(f"读取DXF失败: {dxf_path}: {e}")
            result["_error"] = str(e)
            return result

        attrib_data = self.extract_from_attrib_blocks(doc)
        for k, v in attrib_data.items():
            if k in result and v:
                result[k] = v

        frame_block_data = self.extract_from_frame_blocks(doc)
        for k, v in frame_block_data.items():
            if k in result and not result[k] and v:
                result[k] = v

        if frames is None:
            global_data = self.extract_from_global_text(msp)
            for k, v in global_data.items():
                if k in result and not result[k] and v:
                    result[k] = v
        else:
            result["frame_count"] = len(frames)
            for i, (name, x0, y0, x1, y1) in enumerate(frames):
                frame_data = {
                    "index": i + 1,
                    "frame_name": name,
                    "bounds": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                    "drawing_no": "",
                    "drawing_name": "",
                    "scale": "",
                    "date": "",
                }
                frame_text_data = self.extract_from_frame_text(msp, (x0, y0, x1, y1))
                for k, v in frame_text_data.items():
                    if k in frame_data and v:
                        frame_data[k] = v
                    if k in result and not result[k] and v:
                        result[k] = v
                frame_data["_text_sample"] = _extract_title_block_texts(
                    msp, (x0, y0, x1, y1))[:10]
                result["frame_metadata"].append(frame_data)

        if not result["drawing_no"]:
            result["drawing_no"] = self._guess_drawing_number(file_name, result)

        if not result["discipline"]:
            result["discipline"] = self._guess_discipline(result)

        return result

    @staticmethod
    def _guess_drawing_number(file_name: str, data: Dict) -> str:
        patterns = [
            r'(建施|结施|暖施|水施|电施|消施)[-_\s]*(\d+)',
            r'图号[:：]\s*([A-Za-z0-9\-_]+)',
            r'(\d{5,})',
        ]
        for pat in patterns:
            m = re.search(pat, file_name)
            if m:
                return m.group(0)
        return ""

    @staticmethod
    def _guess_discipline(data: Dict) -> str:
        combined = " ".join([
            data.get("drawing_name", ""),
            data.get("drawing_no", ""),
            data.get("file_id", ""),
            data.get("drawing_type", ""),
        ]).lower()
        if any(k in combined for k in ("建施", "建筑", "总图", "平面", "立面", "门窗", "幕墙", "装饰")):
            return "building"
        if any(k in combined for k in ("结施", "结构", "基础", "配筋", "桩基", "预制", "埋件")):
            return "structure"
        if any(k in combined for k in ("暖施", "暖通", "空调", "通风", "供暖", "防排烟")):
            return "hvac"
        if any(k in combined for k in ("水施", "给排水", "给水", "排水", "消火栓", "喷淋", "海绵")):
            return "plumbing"
        if any(k in combined for k in ("电施", "电气", "配电", "照明", "防雷", "弱电", "变配电")):
            return "electrical"
        if any(k in combined for k in ("消施", "消防", "防火", "报警", "灭火")):
            return "fire"
        return "unknown"

    def extract_batch(self, dxf_paths: List[str],
                      detector=None) -> List[Dict[str, Any]]:
        results = []
        for dxf_path in dxf_paths:
            frames = None
            if detector is not None:
                try:
                    frames = detector.detect_frames(dxf_path)
                except Exception as e:
                    logger.debug(f"图框检测失败: {dxf_path}, {e}")
            data = self.extract(dxf_path, frames=frames)
            results.append(data)
        return results

    def to_json(self, data: List[Dict[str, Any]], output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"图签元数据导出JSON: {output_path} ({len(data)}条)")
        return output_path

    def to_excel(self, data: List[Dict[str, Any]], output_path: str) -> str:
        try:
            import pandas as pd
        except ImportError:
            logger.warning("pandas未安装，使用CSV替代Excel")
            return self._to_csv(data, output_path.replace(".xlsx", ".csv"))

        rows = []
        for item in data:
            frames = item.get("frame_metadata", [])
            base = {k: v for k, v in item.items()
                    if not isinstance(v, (list, dict)) and k != "frame_metadata"}
            if frames:
                for fm in frames:
                    row = dict(base)
                    row["frame_index"] = fm.get("index", "")
                    row["frame_name"] = fm.get("frame_name", "")
                    row["frame_bounds"] = str(fm.get("bounds", ""))
                    row["frame_drawing_no"] = fm.get("drawing_no", "")
                    row["frame_drawing_name"] = fm.get("drawing_name", "")
                    rows.append(row)
            else:
                base["frame_index"] = ""
                base["frame_name"] = ""
                base["frame_bounds"] = ""
                base["frame_drawing_no"] = ""
                base["frame_drawing_name"] = ""
                rows.append(base)

        df = pd.DataFrame(rows)
        columns = [
            "file_id", "drawing_no", "drawing_name", "project_name",
            "sub_project", "discipline", "drawing_type", "scale",
            "date", "version", "designer", "checker", "approver",
            "frame_size", "frame_count", "frame_index", "frame_name",
            "frame_bounds", "frame_drawing_no", "frame_drawing_name",
        ]
        columns = [c for c in columns if c in df.columns]
        if not columns:
            logger.warning(f"没有找到匹配的列，使用所有可用列")
            columns = df.columns.tolist()
        df = df[columns]

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        if _HAS_OPENPYXL:
            df.to_excel(output_path, index=False, engine="openpyxl")
            logger.info(f"图签元数据导出Excel: {output_path} ({len(rows)}行)")
        else:
            csv_path = output_path.replace(".xlsx", ".csv")
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            logger.warning(f"openpyxl未安装，已导出为CSV: {csv_path}")
            output_path = csv_path
        return output_path

    def _to_csv(self, data: List[Dict[str, Any]], output_path: str) -> str:
        import csv
        rows = []
        for item in data:
            frames = item.get("frame_metadata", [])
            base = {k: v for k, v in item.items()
                    if not isinstance(v, (list, dict)) and k != "frame_metadata"}
            if frames:
                for fm in frames:
                    row = dict(base)
                    row["frame_index"] = fm.get("index", "")
                    row["frame_name"] = fm.get("frame_name", "")
                    row["frame_bounds"] = str(fm.get("bounds", ""))
                    row["frame_drawing_no"] = fm.get("drawing_no", "")
                    row["frame_drawing_name"] = fm.get("drawing_name", "")
                    rows.append(row)
            else:
                rows.append(base)

        if not rows:
            return output_path

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"图签元数据导出CSV: {output_path} ({len(rows)}行)")
        return output_path