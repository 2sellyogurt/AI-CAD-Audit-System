# -*- coding: utf-8 -*-
"""检查点Prompt模板

基于检查点参数自动填充的Prompt模板。
文本路径和视觉路径使用不同模板。
"""

import os
import logging
import threading
import yaml

logger = logging.getLogger("v7.prompt_templates")

_symbol_cache = None
_symbol_lock = threading.Lock()
_MAX_TEXT_CHARS = 90000  # 文本路径最大字符数


def _load_symbol_legend():
    global _symbol_cache
    if _symbol_cache is not None:
        return _symbol_cache
    with _symbol_lock:
        if _symbol_cache is not None:
            return _symbol_cache
        legend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "definitions", "symbol_legend.yaml"
        )
        try:
            with open(legend_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            symbols = data.get("symbols", {})
            lines = []
            high_confusion_keys = {"QD", "PI", "FM", "QDJ", "RDJ"}
            high_lines = []
            normal_lines = []
            for k, v in symbols.items():
                if isinstance(v, dict):
                    parts = [v.get('meaning', str(v))]
                    if v.get('not_meaning'):
                        parts.append(f"⚠绝对不是{v['not_meaning']}")
                    line = f"  {k} = {'，'.join(parts)}"
                else:
                    line = f"  {k} = {v}"
                if k in high_confusion_keys:
                    high_lines.append(line)
                else:
                    normal_lines.append(line)
            notes = data.get("notes", "")
            legend = "常见施工图代号含义：\n"
            if high_lines:
                legend += "【极易混淆代号——必须优先核实】\n" + "\n".join(high_lines) + "\n\n【其他代号】\n"
            legend += "\n".join(normal_lines) + "\n\n" + notes
            _symbol_cache = legend
        except FileNotFoundError:
            logger.warning(f"代号定义文件不存在: {legend_path}")
            _symbol_cache = ""
        except Exception as e:
            logger.warning(f"加载代号定义失败: {str(e)}")
            _symbol_cache = ""
    return _symbol_cache


def _get_symbol_context() -> str:
    legend = _load_symbol_legend()
    if not legend:
        return ""
    return f"\n【施工图代号参考——必须据此解读短代号含义】\n{legend}\n"


def _build_output_format(cp, evidence_field="标注原文片段", location_field="文本位置特征") -> str:
    """构建公共的输出格式部分。"""
    lines = [
        "【输出要求】",
        "- 如果没有发现问题，只输出\"无问题\"三个字",
        "- 如果发现问题，严格按照以下JSON格式输出，不得添加任何其他内容：",
        '{"verdict": "不合规",',
        f' "confidence": "high|medium|low",',
        f' "evidence": "{evidence_field}",',
        f' "current_value": "标注数值",',
    ]
    if cp.limit_value is not None:
        lines.append(f' "expected_value": "{cp.limit_value}{cp.unit}",')
    lines.append(f' "suggestion": "具体整改建议",')
    lines.append(f' "location_hint": "{location_field}"}}')
    return "\n".join(lines)


def build_text_prompt(checkpoint, drawing_texts: str) -> str:
    """构建文本路径审查Prompt。"""
    cp = checkpoint
    limit_desc = _build_limit_description(cp)
    obj_desc = "、".join(cp.target_object) if cp.target_object else "相关构件"

    prompt = (
        f"你是一名有15年经验的{_discipline_name(cp.discipline.value)}工程师，正在审查施工图。\n\n"
        f"【检查点编号】{cp.id}\n"
        f"【检查点名称】{cp.name}\n"
        f"【规范依据】{cp.standard_code}第{cp.standard_clause}条"
    )
    if cp.clause_text:
        prompt += f"：{cp.clause_text}"
    prompt += "\n"

    prompt += f"【检查步骤】\n"
    prompt += f"1. 仔细查看以下图纸文本内容，找到所有与{obj_desc}相关的标注\n"
    if cp.check_type.value.startswith("dimension"):
        prompt += f"2. 读取每个{cp.target_property or '相关'}的标注数值\n"
        prompt += f"3. 判断每个数值是否{limit_desc}\n"
        prompt += f"4. 记录所有不满足要求的{obj_desc}\n"
    elif cp.check_type.value == "text_presence":
        prompt += f"2. 检查文本中是否明确出现了{cp.target_property or '相关要求'}\n"
        prompt += f"3. 如果未出现，记录为不合规\n"
    elif cp.check_type.value == "text_absence":
        prompt += f"2. 检查文本中是否出现了不应出现的内容\n"
        prompt += f"3. 如果出现，记录为不合规\n"
    elif cp.check_type.value == "fire_rating":
        prompt += f"2. 检查防火等级标注\n"
        prompt += f"3. 判断是否符合规范要求的耐火极限\n"
    else:
        prompt += f"2. 根据规范要求逐一检查\n"
        prompt += f"3. 记录所有不合规项\n"

    prompt += f"\n【图纸文本内容】\n{drawing_texts[:_MAX_TEXT_CHARS]}\n\n"

    prompt += _get_symbol_context()
    prompt += "\n" + _build_output_format(cp)

    return prompt


def build_vision_prompt(checkpoint, image_count: int) -> str:
    """构建视觉路径审查Prompt。"""
    cp = checkpoint
    limit_desc = _build_limit_description(cp)
    obj_desc = "、".join(cp.target_object) if cp.target_object else "相关构件"

    prompt = (
        f"你是一名有15年经验的{_discipline_name(cp.discipline.value)}工程师，正在审查施工图。\n\n"
        f"请仔细查看以下{image_count}张施工图纸截图。\n\n"
        f"【检查点编号】{cp.id}\n"
        f"【检查点名称】{cp.name}\n"
        f"【规范依据】{cp.standard_code}第{cp.standard_clause}条"
    )
    if cp.clause_text:
        prompt += f"：{cp.clause_text}"
    prompt += "\n"

    prompt += f"【检查步骤】\n"
    prompt += f"1. 在截图中找到所有标注为{obj_desc}的位置\n"
    if cp.check_type.value.startswith("dimension"):
        prompt += f"2. 读取每个{cp.target_property or '相关'}的标注数值\n"
        prompt += f"3. 判断每个数值是否{limit_desc}\n"
        prompt += f"4. 记录所有不满足要求的{obj_desc}，标注其在图纸中的轴线位置\n"
    else:
        prompt += f"2. 逐一检查是否符合规范要求\n"
        prompt += f"3. 记录所有不合规项，标注其在图纸中的轴线位置\n"

    prompt += "\n" + _build_output_format(cp, "标注截图描述", "轴线坐标（如A轴/3轴）")
    prompt += _get_symbol_context()

    return prompt


def _build_limit_description(checkpoint) -> str:
    op = checkpoint.operator
    val = checkpoint.limit_value
    unit = checkpoint.unit
    if op in (">=", "≥"):
        return f"≥{val}{unit}"
    elif op in ("<=", "≤"):
        return f"≤{val}{unit}"
    elif op == ">":
        return f">{val}{unit}"
    elif op == "<":
        return f"<{val}{unit}"
    elif op == "==":
        return f"={val}{unit}"
    elif op == "in":
        return f"在{val}范围内"
    return f"满足规范要求"


def _discipline_name(discipline: str) -> str:
    names = {
        "building": "一级注册建筑",
        "structure": "一级注册结构",
        "hvac": "注册暖通",
        "plumbing": "注册给排水",
        "electrical": "注册电气",
        "fire": "注册消防",
        "cross": "教授级高级",
    }
    return names.get(discipline, "资深审图")
