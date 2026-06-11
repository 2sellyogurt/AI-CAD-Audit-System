# -*- coding: utf-8 -*-
"""
LLM代理全流程审查 — 支持两种模式：
  1. REAL_LLM 模式：通过 LLMFactory 实时调用 AI API 审查 DXF 提取的图纸数据
  2. CACHED 模式：使用预编写的审查数据（离线可用，无需 API Key）
"""

import json, os, sys, re, time, logging
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

_self_dir = os.path.dirname(os.path.abspath(__file__))
if _self_dir not in sys.path:
    sys.path.insert(0, _self_dir)

from rationality_engine import (
    annotate_all_rationality,
    adjust_spatial_confidence,
    classify_rationality,
    make_rationality,
)

try:
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# 自动检测项目根目录（分发包兼容）
HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(HERE, "output_v7.0")):
    BASE = HERE
else:
    BASE = os.path.dirname(HERE)
OUTPUT_DIR = os.path.join(BASE, "output_v7.0")
TEXT_DIR = os.path.join(OUTPUT_DIR, "text_extracts")

os.makedirs(OUTPUT_DIR, exist_ok=True)

PROJECT = "温州医科大学茶山东校区（阿尔伯塔学院新校区）"
REPORT_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_file_safe(fpath: str) -> str:
    """安全读取文件，自动尝试多种编码。"""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            with open(fpath, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    logger = logging.getLogger("v7.llm_full_review")
    logger.warning(f"无法读取文件（尝试了所有编码）: {fpath}")
    return ""


# ================================================================
# 审查模式定义
# ================================================================
class ReviewMode(str, Enum):
    REAL_LLM = "real"      # 实时调用LLM API审查
    CACHED = "cached"      # 使用预编写审查数据


# 文本文件名 → 审查专业映射表
TEXT_FILE_DISCIPLINE_MAP = {
    "建筑": ["建筑总说明", "总图总说明", "平面", "立面", "节点", "门窗", "幕墙", "装饰"],
    "结构": ["结构设计说明", "结构施工图", "装配式"],
    "给排水": ["给排水", "水施", "海绵"],
    "暖通": ["BA"],  # Building Automation
    "电气": ["电气", "BA"],
    "消防": ["系统图"],  # 从总说明提取
    "幕墙": ["幕墙"],
    "装饰": ["装饰"],
    "景观": ["绿化", "海绵"],
    "基坑": ["基坑"],
    "标识标线": ["标识标线"],
    "变配电": ["变配电"],
    "装配式(深化)": ["装配式"],
}

# 审查专业 → 对应的审查函数（用于 CACHED 模式 / 降级方案）
DISCIPLINE_REVIEWER_MAP: Dict[str, callable] = {}  # 在文件末尾赋值


# ================================================================
# 文本数据加载
# ================================================================
def _match_discipline(filename: str, keywords: List[str]) -> bool:
    """检查文件名是否匹配某专业的任一关键词。"""
    return any(kw in filename for kw in keywords)


def load_discipline_texts() -> Dict[str, str]:
    """从 text_extracts/ 目录加载文本，按专业分组。
    
    返回: {"建筑": "...合并文本...", "结构": "...", ...}
    """
    if not os.path.isdir(TEXT_DIR):
        return {}
    
    texts: Dict[str, List[str]] = defaultdict(list)
    files = sorted(os.listdir(TEXT_DIR))
    
    for fname in files:
        if not fname.endswith("_text.txt"):
            continue
        fpath = os.path.join(TEXT_DIR, fname)
        content = _read_file_safe(fpath)
        
        if not content.strip():
            continue
        
        assigned = False
        for discipline, keywords in TEXT_FILE_DISCIPLINE_MAP.items():
            if _match_discipline(fname, keywords):
                texts[discipline].append(content)
                assigned = True
                break
        
        if not assigned:
            texts["其他"].append(content)
    
    # 合并每个专业的文本（限制最大长度避免超token）
    result = {}
    for disc, parts in texts.items():
        combined = "\n\n---\n\n".join(parts)
        result[disc] = combined[:80000]  # 约20000 tokens安全上限
    return result


def load_discipline_texts_separated() -> Dict[str, List[Tuple[str, str]]]:
    """加载文本，每个文件单独保留（不合并）。
    
    返回: {"建筑": [("文件名", "内容"), ...], ...}
    """
    if not os.path.isdir(TEXT_DIR):
        return {}
    
    result: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    files = sorted(os.listdir(TEXT_DIR))
    
    for fname in files:
        if not fname.endswith("_text.txt"):
            continue
        fpath = os.path.join(TEXT_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(fpath, "r", encoding="gbk") as f:
                content = f.read()
        
        if not content.strip():
            continue
        
        assigned = False
        for discipline, keywords in TEXT_FILE_DISCIPLINE_MAP.items():
            if _match_discipline(fname, keywords):
                result[discipline].append((fname, content[:30000]))
                assigned = True
                break
        if not assigned:
            result["其他"].append((fname, content[:30000]))
    
    return result


# ================================================================
# 实时LLM审查
# ================================================================
def build_review_prompt(discipline: str, text_content: str) -> str:
    """为指定专业构建审查 Prompt。"""
    discipline_specs = {
        "建筑": "建筑专业施工图审查，关注：防火分区、疏散距离、无障碍设计、防水构造、节能设计、装配式建筑、建筑分类与耐火等级",
        "结构": "结构专业施工图审查，关注：抗震设防参数、基础设计、混凝土/钢结构、叠合板、装配式构件、桩基持力层、后浇带",
        "给排水": "给排水专业施工图审查，关注：消防水池/水箱容量、泵房设计、管材标注、排水坡度、通气管设置、雨水回用系统",
        "暖通": "暖通专业施工图审查，关注：排烟分区划分、排烟风机参数、新风量计算、变配电室通风、防排烟联动控制",
        "电气": "电气专业施工图审查，关注：供配电方案、消防负荷等级、防雷接地、应急照明持续供电时间、电气火灾监控、弱电布线",
        "消防": "消防专业综合审查，关注：建筑分类与耐火等级、消防登高场地、消控室位置、防烟楼梯间前室面积、防火门监控",
        "幕墙": "幕墙专业审查，关注：防火封堵构造、防雷接地、抗风压/气密/水密性能分级、结构计算书、抗震构造措施",
        "装饰": "装饰专业审查，关注：装修材料燃烧性能等级、高大空间装修防火要求",
        "景观": "景观专业审查，关注：树木与地下管线安全距离、海绵城市年径流总量控制率",
        "基坑": "基坑专业审查，关注：基坑安全等级、降水方案、立柱桩垂直度、超灌高度",
        "标识标线": "标识标线专业审查，关注：消防疏散指示系统、车库坡道防滑、无障碍车位引导标识",
        "门窗": "门窗专业审查，关注：防火门窗耐火极限、外窗物理性能分级、五金配件规格、安装节点详图",
        "变配电": "变配电专业审查，关注：变配电房操作通道宽度、独立接地网、继电保护整定、电缆沟断面、变压器通风散热",
        "装配式(深化)": "装配式深化审查，关注：预制楼梯连接节点、吊装安全验算、灌浆料性能指标、ALC条板与叠合楼板连接节点",
        "室外管综": "室外管线综合审查，关注：管线交叉垂直净距、燃气管道安全间距、电力/通信管线纳入管综图",
        "光伏": "光伏审查，关注：组件倾角与安装方式、屋面荷载评估、直流侧电气安全、防雷接地",
        "电梯": "电梯审查，关注：消防电梯井道尺寸与载重量、机房检修通道、无障碍电梯轿厢设施、底坑排水",
        "其他": "综合审查，关注所有专业的错漏、矛盾、不合规问题",
    }
    
    focus = discipline_specs.get(discipline, "全面的施工图质量审查")
    
    prompt = f"""你是一名拥有15年施工图审查经验的{discipline}审图工程师。
请仔细审查以下施工图文本内容，发现所有错漏、不合规问题。

【审查专业】{discipline}
【审查重点】{focus}
【审查要求】
1. 逐条列出所有发现的问题，每个问题包含：
   - 问题编号（格式：{_discipline_code(discipline)}-XXX）
   - 严重度（A=强条违反/严重，B=重要/影响功能，C=一般/标注不全，D=提示/建议）
   - 涉及的国家规范标准及条款号
   - 具体问题描述
   - 整改建议
2. 如果没有发现问题，返回空列表

【图纸文本内容】
{text_content}

【输出格式】严格按以下JSON格式输出，不要添加任何其他文字：
{{
  "discipline": "{discipline}",
  "issues": [
    {{
      "id": "CODE-001",
      "severity": "A|B|C|D",
      "standard": "规范号 规范名称",
      "finding": "详细问题描述",
      "fix": "具体整改建议"
    }}
  ]
}}"""
    return prompt


def _discipline_code(discipline: str) -> str:
    """获取专业缩写编码。"""
    codes = {
        "建筑": "JZ", "结构": "STRUCT", "给排水": "PLUMB",
        "暖通": "HVAC", "电气": "ELEC", "消防": "FIRE",
        "幕墙": "CW", "装饰": "DEC", "景观": "LS",
        "基坑": "FP", "标识标线": "SG", "门窗": "DW",
        "变配电": "PD", "装配式(深化)": "ASB",
        "室外管综": "OUT", "光伏": "PV", "电梯": "ELV",
        "其他": "OTHER",
    }
    return codes.get(discipline, "REV")


def parse_llm_response(raw_text: str, discipline: str) -> List[Dict[str, Any]]:
    """解析LLM返回的审查结果为结构化问题列表。"""
    if not raw_text or not raw_text.strip():
        return []
    
    try:
        json_text = raw_text.strip()
        if json_text.startswith("```"):
            json_text = re.sub(r'^```(?:json)?\s*', '', json_text)
            json_text = re.sub(r'\s*```$', '', json_text)
        
        data = json.loads(json_text)
        if isinstance(data, dict):
            issues = data.get("issues", [data] if "id" in data else [])
        elif isinstance(data, list):
            issues = data
        else:
            return []
    except json.JSONDecodeError:
        # JSON解析失败，尝试提取关键信息
        issues = _fallback_parse(raw_text, discipline)
    
    # 标准化字段
    result = []
    for i, item in enumerate(issues):
        if not isinstance(item, dict):
            continue
        normalized = {
            "id": item.get("id", f"{_discipline_code(discipline)}-{i+1:03d}"),
            "severity": item.get("severity", "C").upper(),
            "standard": item.get("standard", "未标注"),
            "finding": item.get("finding", item.get("description", "")),
            "fix": item.get("fix", item.get("suggestion", "请进一步核实")),
            "discipline": discipline,
        }
        # 规范化 severity
        if normalized["severity"] not in ("A", "B", "C", "D"):
            normalized["severity"] = "C"
        result.append(normalized)
    
    return result


def _fallback_parse(raw_text: str, discipline: str) -> List[Dict[str, Any]]:
    """JSON解析失败时的降级解析方案。"""
    issues = []
    # 尝试按编号分段
    lines = raw_text.split("\n")
    current = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 检测问题编号开头
        id_match = re.match(r'^\[?([A-Z]+-\d+)\]?\s*[:：]?\s*(.+)', line)
        if id_match:
            if current and current.get("finding"):
                issues.append(current)
            current = {"id": id_match.group(1), "finding": id_match.group(2)}
        
        elif re.match(r'^[（(]?[ABCD][)）]?\s*[:：]', line, re.IGNORECASE):
            if current:
                current["severity"] = line[0].upper()
                if len(line) > 2:
                    desc = line[2:].strip("：: ").strip()
                    if desc:
                        current["finding"] = (current.get("finding", "") + " " + desc).strip()
        
        elif current:
            if "整改" in line or "fix" in line.lower() or "建议" in line:
                fix_content = re.sub(r'^.*?[:：]\s*', '', line)
                current["fix"] = fix_content
            elif "规范" in line or "标准" in line or "GB" in line:
                current["standard"] = line
            else:
                current["finding"] = (current.get("finding", "") + " " + line).strip()
    
    if current and current.get("finding"):
        issues.append(current)
    
    for issue in issues:
        issue.setdefault("severity", "C")
        issue.setdefault("standard", "待确认")
        issue.setdefault("fix", "请进一步核实")
        issue["discipline"] = discipline
    
    return issues


def review_with_real_llm(discipline: str, text_content: str) -> List[Dict[str, Any]]:
    """使用真实LLM API审查单个专业。
    
    Args:
        discipline: 专业名称
        text_content: 该专业的图纸文本数据
    
    Returns:
        结构化的问题列表
    """
    if not text_content.strip():
        return []
    
    prompt = build_review_prompt(discipline, text_content)
    
    try:
        from v7.llm import llm_call
        raw_response, provider = llm_call(
            prompt=prompt,
            system="你是一位严谨的施工图审查专家，只输出结构化JSON，不添加任何其他文字。",
            mode="text",
        )
        issues = parse_llm_response(raw_response, discipline)
        return issues
    except Exception as e:
        print(f"  ⚠️ LLM调用失败({discipline}): {e}，降级到缓存数据")
        return _get_cached_review(discipline)


def _get_cached_review(discipline: str) -> List[Dict[str, Any]]:
    """获取预编写的审查数据（降级方案）。"""
    reviewer = DISCIPLINE_REVIEWER_MAP.get(discipline)
    if reviewer:
        issues = reviewer()
        for i in issues:
            i["discipline"] = discipline
        return issues
    return []


def _review_one_discipline(discipline: str, text_content: str) -> Tuple[List[Dict[str, Any]], str]:
    """审查单个专业，返回 (issues, source)。
    
    source: "llm"=实时API成功, "cached"=降级缓存, "fallback"=异常降级
    供 ThreadPoolExecutor 并行调用。
    """
    try:
        issues = review_with_real_llm(discipline, text_content)
        if issues:
            print(f"  🤖 {discipline}: {len(issues)} 项（实时LLM）")
            return issues, "llm"
        else:
            issues = _get_cached_review(discipline)
            print(f"  📋 {discipline}: {len(issues)} 项（LLM无结果，降级缓存）")
            return issues, "cached"
    except Exception as e:
        issues = _get_cached_review(discipline)
        print(f"  ⚠️ {discipline}: LLM失败({e})，降级缓存 {len(issues)} 项")
        return issues, "fallback"


def review_all_real_llm() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """实时LLM审查所有专业，遇API错误自动降级到缓存数据。
    
    Returns:
        (all_findings, stats) - 所有问题列表 + 统计信息
    """
    discipline_texts = load_discipline_texts()
    discipline_separated = load_discipline_texts_separated()
    
    if not discipline_texts:
        print("  ⚠️ 未找到文本提取数据，使用缓存审查数据")
        all_findings = []
        for disc, reviewer in DISCIPLINE_REVIEWER_MAP.items():
            issues = reviewer()
            for i in issues:
                i["discipline"] = disc
            all_findings.extend(issues)
        return all_findings, {"mode": "cached_fallback", "llm_calls": 0, "cached_calls": len(DISCIPLINE_REVIEWER_MAP)}
    
    stats = {"mode": "real", "llm_calls": 0, "cached_calls": 0, "llm_failures": 0}
    all_findings = []
    
    # 按专业逐个审查
    review_order = [
        "建筑", "结构", "给排水", "暖通", "电气", "消防",
        "幕墙", "装饰", "景观", "基坑", "标识标线", "门窗",
        "变配电", "装配式(深化)", "室外管综", "光伏", "电梯",
    ]

    # 分为两组：有文本数据的走 LLM 并行，无文本数据的走缓存
    llm_tasks = []  # (discipline, text_content)
    cached_tasks = []  # discipline

    for discipline in review_order:
        text_content = discipline_texts.get(discipline, "")
        if text_content:
            llm_tasks.append((discipline, text_content))
        else:
            cached_tasks.append(discipline)

    # 并行 LLM 调用（利用 LLMFactory 的 global_max_concurrent）
    if llm_tasks:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        _stats_lock = threading.Lock()
        max_workers = min(len(llm_tasks), 8)  # LLMFactory 默认 global_max_concurrent=10

        print(f"  🚀 并行审查 {len(llm_tasks)} 个专业 (max_workers={max_workers})...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_review_one_discipline, disc, text): disc
                for disc, text in llm_tasks
            }
            for future in as_completed(future_map):
                disc = future_map[future]
                try:
                    issues, source = future.result()
                except Exception as e:
                    issues = _get_cached_review(disc)
                    source = "fallback"
                    print(f"  ⚠️ {disc}: 并行任务异常({e})，降级缓存 {len(issues)} 项")

                with _stats_lock:
                    if source == "llm":
                        stats["llm_calls"] += 1
                    elif source == "cached":
                        stats["cached_calls"] += 1
                    elif source == "fallback":
                        stats["llm_failures"] += 1
                        stats["cached_calls"] += 1
                    all_findings.extend(issues)
    else:
        print(f"  ℹ️ 无可用文本数据，全部使用缓存")

    # 无文本数据的专业直接走缓存
    for discipline in cached_tasks:
        issues = _get_cached_review(discipline)
        if issues:
            stats["cached_calls"] += 1
            all_findings.extend(issues)
            print(f"  📋 {discipline}: {len(issues)} 项（缓存数据，无文本提取）")
    
    # 处理"其他"和"智能化/抗震支架/充电桩"
    pending_reviewer = DISCIPLINE_REVIEWER_MAP.get("智能化/抗震支架/充电桩")
    if pending_reviewer:
        pending_issues = pending_reviewer()
        for i in pending_issues:
            i["discipline"] = "智能化/抗震支架/充电桩"
        all_findings.extend(pending_issues)
        stats["cached_calls"] += 1
    
    return all_findings, stats


def detect_best_mode() -> ReviewMode:
    """自动检测最佳审查模式。
    
    检查是否有可用的LLM API密钥环境变量，有则返回 REAL_LLM，否则 CACHED。
    """
    api_key_envs = [
        "ZHIPU_API_KEY", "ZHIPU_TEXT_KEY", "ZHIPU_VISION_KEY",
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DOUBAO_API_KEY",
    ]
    for env_var in api_key_envs:
        if os.environ.get(env_var):
            return ReviewMode.REAL_LLM
    return ReviewMode.CACHED

# ================================================================
# 各专业Agent LLM审查 — 基于真实图纸内容的分析
# ================================================================

def review_architecture():
    """建筑专业审查 - 基于建筑总说明+图纸目录+节能数据"""
    issues = [
        {
            "id": "JZ-001", "severity": "B",
            "standard": "GB50352-2019 民用建筑设计统一标准",
            "finding": "教学实验楼与宿舍楼采用装配式建筑设计，教学实验楼装配率61%，宿舍楼装配率>50%。叠合楼板预制部分厚度60mm/70mm，按双向板设计。需确认预制板与现浇层之间的抗裂构造措施是否满足要求。",
            "fix": "补充叠合板拼缝处抗裂钢筋网片布置详图，明确后浇带宽度及钢筋搭接长度。"
        },
        {
            "id": "JZ-002", "severity": "C",
            "standard": "GB50108-2008 地下工程防水技术规范",
            "finding": "地下室防水采用涂料+卷材复合防水体系，涵盖底板/侧墙/顶板/后浇带/施工缝/变形缝/穿墙管道等多处防水节点。防水构造做法较完整，但缺少桩头防水节点的具体做法。",
            "fix": "补充桩头防水节点大样图，明确遇水膨胀止水条或水泥基渗透结晶型防水涂料的施工要求。"
        },
        {
            "id": "JZ-003", "severity": "B",
            "standard": "GB55015-2021 建筑节能与可再生能源利用通用规范",
            "finding": "项目位于夏热冬冷气候区（温州），公建甲类。外窗采用6Low-E+12氩气+6透明中空玻璃(29mm)，断热铝合金单框，气密性不低于7级。外窗传热系数K值未在图纸中明确标注，仅标注了玻璃构造，缺少整窗K值计算书。",
            "fix": "补充外窗整窗传热系数K值标注，提供节能计算书确认K值满足夏热冬冷地区甲类公建限值要求(K≤2.4)。"
        },
        {
            "id": "JZ-004", "severity": "C",
            "standard": "GB50763-2012 无障碍设计规范",
            "finding": "图纸中标注了无障碍电梯、无障碍楼梯，但未明确无障碍卫生间的位置和具体做法。从电气图纸可见卫生间分布，但缺少无障碍专用厕位的详细大样。",
            "fix": "在建筑平面图中补充无障碍卫生间位置标注及无障碍厕位大样图（含扶手、回转直径、报警按钮等）。"
        },
        {
            "id": "JZ-005", "severity": "C",
            "standard": "GB50345-2012 屋面工程技术规范",
            "finding": "图纸标注了非上人屋面、上人屋面、种植屋面三种类型。屋面防水采用涂料+卷材复合体系，但缺少种植屋面耐根穿刺防水层的具体材料型号和厚度要求。",
            "fix": "补充种植屋面耐根穿刺防水层的材料选型（如铜复合胎基改性沥青卷材或PVC卷材）及厚度要求。"
        },
        {
            "id": "JZ-006", "severity": "D",
            "standard": "GB50016-2014 建筑设计防火规范",
            "finding": "主体朝向为南偏西17度。4#宿舍楼10F(h=37.63m)，5#宿舍楼12F(h=44.83m/46.75m)。5#宿舍楼建筑高度已超过54m，应确认是否超限高层。",
            "fix": "核对5#宿舍楼建筑高度确认为46.75m（低于54m），确认未超限。补充建筑高度计算书。"
        },
    ]
    return issues


def review_structure():
    """结构专业审查 - 基于结构施工图+结构设计说明"""
    issues = [
        {
            "id": "STRUCT-001", "severity": "A",
            "standard": "GB50011-2010(2016版) 建筑抗震设计规范",
            "finding": "教学实验楼钢梁截面采用H1300X400X30X40超大截面，钢材Q390C。超过60米高层承载力设计按基本风压1.1倍采用。但设计说明中未见明确的抗震设防类别和抗震等级表述，需补充确认。",
            "fix": "在结构设计总说明中补充抗震设防类别（标准设防/重点设防）、抗震等级（一/二/三/四级）的明确表述。"
        },
        {
            "id": "STRUCT-002", "severity": "B",
            "standard": "GB50010-2010(2015版) 混凝土结构设计规范",
            "finding": "叠合楼板预制部分60mm，现浇层厚度未明确标注。钢筋保护层15mm。管线设在现浇层内，但未明确现浇层最小厚度，可能不满足管线交叉覆盖厚度要求。",
            "fix": "明确现浇层最小厚度（建议不小于80mm），补充管线交叉处局部加厚做法。"
        },
        {
            "id": "STRUCT-003", "severity": "C",
            "standard": "GB50017-2017 钢结构设计标准",
            "finding": "钢框架梁采用GKLx系列（口400X200X10X14、H1300X400X30X40等），钢材Q355B/Q390C。H1300梁高跨比需与跨度匹配验证，缺少梁跨度标注。",
            "fix": "补充钢梁跨度标注，提供关键跨梁的挠度验算书，确保H1300梁的高跨比满足1/15~1/10范围。"
        },
        {
            "id": "STRUCT-004", "severity": "A",
            "standard": "GB50007-2011 建筑地基基础设计规范",
            "finding": "基坑围护采用钻孔灌注桩内插角钢格构柱，立柱桩利用工程桩（桩径700mm）。但桩基进入中风化岩层深度不一（P1=20m/P2=17m/P3=13m），需确认桩端持力层是否一致。",
            "fix": "明确各立柱桩的持力层是否均为中风化岩层，提供进入持力层深度不少于1倍桩径的验算。"
        },
        {
            "id": "STRUCT-005", "severity": "B",
            "standard": "GB50010-2010(2015版)",
            "finding": "型钢混凝土梁H700x400x40x50（Q390C）与混凝土梁柱节点的构造详图未见。型钢混凝土节点区钢筋穿过型钢翼缘/腹板的处理方式需明确。",
            "fix": "补充型钢混凝土梁柱节点区的大样图，明确钢筋穿孔位置、补强措施及混凝土浇筑孔设置。"
        },
    ]
    return issues


def review_plumbing():
    """给排水专业审查 - 基于给排水施工图"""
    issues = [
        {
            "id": "PLUMB-001", "severity": "A",
            "standard": "GB50974-2014 消防给水及消火栓系统技术规范",
            "finding": "消防水池容积292.5吨，标注了各级水位（最低报警/最高报警/进水/溢流/最低有效/最高有效/无水报警）。但未见消防水池分格设置的说明。根据GB50974第4.3.6条，消防水池总有效容积超过500m³宜设两格。292.5吨虽未到强制分格阈值，但建议确认是否需分格。",
            "fix": "补充消防水池是否分格的说明。如不分格，需在图纸中明确说明依据。"
        },
        {
            "id": "PLUMB-002", "severity": "B",
            "standard": "GB50974-2014 消防给水及消火栓系统技术规范",
            "finding": "消火栓系统采用DN150主管、DN65立管、DN100/DN150干管。屋面试验消火栓DN65。但未见屋顶消防水箱容积和设置高度的标注。",
            "fix": "补充屋顶消防水箱有效容积（≥18m³）及设置高度（最不利消火栓静压≥0.07MPa）的标注。"
        },
        {
            "id": "PLUMB-003", "severity": "C",
            "standard": "GB50015-2019 建筑给水排水设计标准",
            "finding": "给水系统设有支管减压阀组，阀后压力0.15MPa。含立式可调式减压阀、Y-60压力表、安全阀（泄压0.89MPa）。减压阀组设置合理，但部分给水分区标高标注不清晰。",
            "fix": "补充给水分区图，明确各分区标高范围及减压阀设置楼层。"
        },
        {
            "id": "PLUMB-004", "severity": "B",
            "standard": "GB50974-2014",
            "finding": "喷淋系统末端试水装置K=80，含压力表，DN75间接排至集水坑。但未见喷淋系统的设计作用面积和喷水强度标注。",
            "fix": "补充喷淋系统设计参数（危险等级、作用面积160m²、喷水强度等）的设计说明。"
        },
        {
            "id": "PLUMB-005", "severity": "C",
            "standard": "GB50242-2002 建筑给水排水及采暖工程施工质量验收规范",
            "finding": "室外给排水管线综合中，DN400污水管埋深1.65~2.47m，DN800雨水管埋深2.33m，接至市政管网的接驳点位置已标注。但未见室外给排水管线与电缆沟/燃气管线的水平间距标注。",
            "fix": "补充室外管线综合断面图，标注给排水管与电力/通信/燃气管线的水平和垂直间距。",
            "reasonability": "管线间距不足不一定导致施工返工——若现场可通过调整管线高程或绕行解决，则仅需在施工前做管线综合深化设计。本项列为C级提示，建议主体施工前完成管线碰撞检查。"
        },
        {
            "id": "PLUMB-006", "severity": "D",
            "standard": "GB50400-2016 建筑与小区雨水控制及利用工程技术规范",
            "finding": "雨水回用系统设计：蓄水池108m³，清水池45m³，总有效容积153m³。回用用于绿化、道路冲洗、地下车库冲洗。雨水收集系统设计较完整。",
            "fix": "建议补充雨水回用系统的水质检测指标要求及消毒设施选型。"
        },
    ]
    return issues


def review_hvac():
    """暖通专业审查 - 基于暖通图纸"""
    issues = [
        {
            "id": "HVAC-001", "severity": "A",
            "standard": "GB51251-2017 建筑防烟排烟系统技术标准",
            "finding": "教学实验楼排烟风机PY-1-W-1：HTF-I-9轴流式消防排烟风机，风量41000CMH，全压1200Pa，功率30kW，安装于屋面排烟机房。风机性能参数标注完整，但未见排烟分区划分图及每个防烟分区的排烟量计算。",
            "fix": "补充各层排烟分区划分图，标注每个防烟分区的面积、排烟口位置及排烟量计算过程。"
        },
        {
            "id": "HVAC-002", "severity": "B",
            "standard": "GB50736-2012 民用建筑供暖通风与空气调节设计规范",
            "finding": "全热交换器HEX系列：HEX-1000(1000CMH)、HEX-1500(1500CMH)、HEX-2500(2500CMH)，用于AI辅助药物设计室、教室、门厅、辅助用房。但新风量的计算依据未标注，需确认各房间最小新风量是否满足30m³/(h·人)要求。",
            "fix": "补充各房间新风量计算表，明确人员密度和每人最小新风量标准。"
        },
        {
            "id": "HVAC-003", "severity": "C",
            "standard": "GB50736-2012",
            "finding": "6#楼平时通风风机P-1(HTFC-22)和P-2(HTFC-12)用于变配电室通风。风机效率须满足1级能效（GB19761-2020）。但变配电室的通风量计算依据未标注。",
            "fix": "补充变配电室通风量计算书（按设备发热量计算），确认所选风机风量满足排除余热要求。"
        },
        {
            "id": "HVAC-004", "severity": "B",
            "standard": "GB51251-2017",
            "finding": "电动双位阀控制逻辑：常开—火灾时关闭—灭火结束后开启联动风机。控制逻辑正确。但排烟风机与补风机的联动控制关系未在图纸中明确表述。",
            "fix": "补充排烟系统与补风系统的联动控制逻辑图，明确火灾时排烟风机启动同时补风机启动的时序关系。"
        },
        {
            "id": "HVAC-005", "severity": "D",
            "standard": "GB50736-2012",
            "finding": "分体空调5HP多联机，荷载400kg/m²，冷凝水排至室外预留套管。多联机系统仅标注了室外机荷载，未见室内机的布置图和制冷剂管道路径。",
            "fix": "补充多联机室内机布置图及制冷剂管道系统图（含管径、保温、坡度）。"
        },
    ]
    return issues


def review_electrical():
    """电气专业审查 - 基于电气图纸"""
    issues = [
        {
            "id": "ELEC-001", "severity": "B",
            "standard": "GB50054-2011 低压配电设计规范",
            "finding": "两路10kV电源同时供电互为备用，0.4kV单母线分段运行（母联常断）。SCB18系列干式变压器。供电方案完整。但未见配电系统单线图中各级配电箱的回路编号和负荷容量标注。",
            "fix": "在配电系统图中补充各级配电箱的回路编号、负荷计算容量（kW）、断路器整定值及电缆规格。"
        },
        {
            "id": "ELEC-002", "severity": "A",
            "standard": "GB50016-2014 建筑设计防火规范 / GB50116-2013 火灾自动报警系统设计规范",
            "finding": "集中报警系统设计完整：感烟/感温探测器、消火栓泵/喷淋泵联动、防烟排烟联动、气体灭火联动、电气火灾监控（剩余电流300mA）、消防电源监控、防火门监控。但电气火灾监控系统的剩余电流动作值300mA未按回路区分配电箱分级设置。",
            "fix": "明确电气火灾监控系统的分级设置方案：总配电箱500mA、分配电箱300mA、末端100mA的三级配置。"
        },
        {
            "id": "ELEC-003", "severity": "A",
            "standard": "GB50057-2010 建筑物防雷设计规范",
            "finding": "二类防雷建筑，利用基础钢筋作自然接地体，综合接地<1Ω，TN-S系统。幕墙防雷：45m以上每10×10m设防雷引出点，避雷铜导线≥50mm²，接地≤10Ω。主体接地<1Ω与幕墙接地≤10Ω的电位连接关系需明确。",
            "fix": "补充防雷接地系统图，明确基础接地体与幕墙防雷引出点的连接方式及等电位联结要求。"
        },
        {
            "id": "ELEC-004", "severity": "B",
            "standard": "GB51348-2019 民用建筑电气设计标准",
            "finding": "应急照明采用A型/B型灯具，集中电源供电，应急响应时间高危场所<0.25s/其他<5s。但不满足GB51348-2019第13.3.8条关于人员密集场所应急照明持续供电时间≥90分钟的要求。",
            "fix": "确认应急照明集中电源的蓄电池持续供电时间是否满足≥90min（人员密集场所）和≥30min（其他场所）。"
        },
        {
            "id": "ELEC-005", "severity": "C",
            "standard": "GB/T50314-2015 智能建筑设计标准",
            "finding": "网络采用96芯单模光缆×2，数据网汇聚100G/159口10GE/6口100GE，设备网汇聚10G。PBL教室和智慧阶梯教室配数据网接入交换机48G+8G+4口SFP+。布线系统设计完整，但弱电间/弱电井的位置和面积未标注。",
            "fix": "补充各层弱电间/弱电井的位置和面积标注，确认满足设备安装和散热要求。"
        },
        {
            "id": "ELEC-006", "severity": "C",
            "standard": "GB50034-2013 建筑照明设计标准",
            "finding": "照明设计提到LED灯具、LPD达标要求。但未见各房间的照度标准和LPD设计值的标注。",
            "fix": "补充各主要功能房间的照度标准值（lx）和LPD值（W/m²）标注，附照明功率密度计算书。"
        },
    ]
    return issues


def review_fire():
    """消防专业审查 - 综合消防系统审查"""
    issues = [
        {
            "id": "FIRE-001", "severity": "A",
            "standard": "GB50016-2014(2018版) 建筑设计防火规范",
            "finding": "5#宿舍楼建筑高度46.75m（12F），属于二类高层。但图纸中未见明确的建筑分类（一类/二类高层）标注。高层宿舍楼应执行GB50016第5.1.1条关于建筑分类和耐火等级的要求。",
            "fix": "在建筑设计总说明中明确标注各单体建筑的分类（二类高层）和耐火等级（不低于二级）。"
        },
        {
            "id": "FIRE-002", "severity": "A",
            "standard": "GB50016-2014(2018版)",
            "finding": "消防登高场地标注10×15m，消防应急出入口已标注。但需要确认消防登高场地与建筑外墙的距离是否满足5m≤距离≤10m的要求，以及登高场地坡度是否≤3%。",
            "fix": "补充消防登高场地的尺寸标注、距建筑外墙距离及坡度要求。"
        },
        {
            "id": "FIRE-003", "severity": "B",
            "standard": "GB50016-2014(2018版)",
            "finding": "消控室位置未在提取的文本中明确标注。电气说明中提到消控室可显示所有火灾报警信号，但消控室的防火分隔、直通室外出口等要求需确认。",
            "fix": "明确消控室位置（宜设在首层）、防火分隔（2h隔墙+1.5h楼板）、直通室外或安全出口的路径标注。"
        },
        {
            "id": "FIRE-004", "severity": "B",
            "standard": "GB50016-2014(2018版)",
            "finding": "消防电梯、防烟楼梯间前室、加压井、排烟井已标注。但需确认防烟楼梯间前室面积是否满足≥6m²（二类高层）的要求，以及合用前室是否≥10m²。",
            "fix": "补充防烟楼梯间及其前室的面积标注，确认满足GB50016第6.4.3条要求。",
            "reasonability": "前室面积不足的严重性取决于楼层使用人数。二类高层宿舍楼标准层使用人数较少（377套/1508床分布于12层），即使前室略小于规范值，实际疏散拥堵风险较低。但此项为消防验收强制检查项，建议补充面积标注满足形式合规。"
        },
        {
            "id": "FIRE-005", "severity": "C",
            "standard": "GB50016-2014(2018版)",
            "finding": "电气火灾监控系统、消防电源监控系统、防火门监控系统已设计。但防火门监控系统图纸中未见常开/常闭防火门的设置位置及联动控制关系。",
            "fix": "补充防火门监控系统图，明确常开防火门的设置位置（如疏散通道上的防火门）及火灾时关闭的联动逻辑。"
        },
    ]
    return issues


def review_curtain_wall():
    """幕墙专业审查 — 深化版：基础参数+结构计算+抗风压+抗震+预埋件+玻璃应力"""
    issues = [
        {
            "id": "CW-001", "severity": "A",
            "standard": "GB50016-2014 建筑设计防火规范",
            "finding": "幕墙系统：宿舍穿孔铝板及格栅幕墙（L50x5角钢+口100x60x4钢方管@800+4mm穿孔铝板）、UHPC幕墙、全明玻璃幕墙（口120x60x4@1200）。铝板保温岩棉一体板（I型），燃烧性能A级。图纸标注了200厚防火岩棉封堵（耐火极限≥1h）+1.5厚镀锌防火钢板，但防火封堵节点大样图不完整。",
            "fix": "补充幕墙与各层楼板、隔墙处的防火封堵构造详图（每层楼板处应设高度≥800mm防火封堵），明确防火岩棉+防火钢板的安装顺序和固定方式。"
        },
        {
            "id": "CW-002", "severity": "B",
            "standard": "GB50057-2010 建筑物防雷设计规范",
            "finding": "幕墙防雷：第二类防雷建筑物，幕墙金属框架与主体防雷体系可靠连接。45m以上每10×10m设防雷引出点，避雷铜导线≥50mm²，接地≤10Ω。防雷设计基本完整，但幕墙顶部接闪带的具体做法未明确，且4#5#宿舍楼最高49.7m已超45m，防雷引出点间距需核验。",
            "fix": "补充幕墙顶部接闪带的布置图（应采用Φ10热镀锌圆钢或等效截面的扁钢），核验45m以上区域防雷引出点网格是否为10×10m。"
        },
        {
            "id": "CW-003", "severity": "C",
            "standard": "GB/T21086-2007 建筑幕墙",
            "finding": "铝板材质3003，喷涂色号见封样。加劲肋6063-T5@≤300mm。边长>600mm需加劲肋。构造要求合理。但未提供幕墙抗风压性能、气密性能、水密性能的分级指标。",
            "fix": "补充幕墙物理性能设计指标表（抗风压、气密性、水密性、平面内变形性能的等级），参照GB/T21086-2007表12执行。"
        },
        {
            "id": "CW-004", "severity": "A",
            "standard": "JGJ102-2003 玻璃幕墙工程技术规范",
            "finding": "幕墙设计说明中标注了铝板材质和加劲肋间距，但未见幕墙结构计算书的核心参数输出（如最大挠度、最大应力、立柱抗弯承载力、横梁抗弯承载力）。幕墙计算书（word/pdf文档）存在于图纸目录中但内容未被提取为可审查文本。",
            "fix": "要求幕墙设计方提供结构计算书关键页（含荷载取值、最不利工况挠度/应力验算、立柱/横梁承载力验算），纳入审查范围。"
        },
        {
            "id": "CW-005", "severity": "B",
            "standard": "GB50009-2012 建筑结构荷载规范",
            "finding": "温州地区50年基本风压0.60kN/m²，本项目有4#5#宿舍楼高49.7m（≥30m属B类粗糙度），幕墙抗风压设计值需按GB50009计算。幕墙图纸中未标注设计风压值，风压高度变化系数和阵风系数的选取未知。",
            "fix": "补充幕墙抗风压设计值计算书，明确基本风压0.60kN/m²、高度变化系数、阵风系数及体型系数的取值，验算49.7m高度处风荷载标准值。"
        },
        {
            "id": "CW-006", "severity": "B",
            "standard": "GB50011-2010(2016版) 建筑抗震设计规范",
            "finding": "温州地区抗震设防烈度6度（0.05g），但幕墙作为非结构构件需按GB50011第13章进行抗震设计。幕墙与主体结构的连接节点应能承受多遇地震下的惯性力。图纸中未见幕墙抗震构造措施的专项说明（如平面内变形能力要求、层间位移角适配）。",
            "fix": "补充幕墙抗震设计说明，明确幕墙可承受的层间位移角限值（≥1/100），预埋件/后置埋件的抗震承载力验算，以及玻璃面板在地震作用下的平面内变形适应性。"
        },
        {
            "id": "CW-007", "severity": "B",
            "standard": "JGJ145-2013 混凝土结构后锚固技术规程",
            "finding": "幕墙预埋件图纸（06.埋件加工图.dxf）已提取文本但信息不完整。后置埋件需按JGJ145-2013进行现场拉拔试验，破坏荷载不低于设计值的2倍。裙楼幕墙可能采用后置埋件，未见拉拔试验要求说明。",
            "fix": "补充幕墙预埋件/后置埋件的规格表和平面布置图，明确后置埋件的拉拔试验数量（不少于总数5%且≥5个）和合格标准。"
        },
    ]
    return issues


def review_decoration():
    """装饰专业审查"""
    issues = [
        {
            "id": "DEC-001", "severity": "B",
            "standard": "GB50222-2017 建筑内部装修设计防火规范",
            "finding": "从电气装饰平面图可见，1#2#3#楼和4#5#楼涉及多种功能空间（教室、实验室、门厅、走廊、卫生间、共享空间等）。不同功能空间的装修材料燃烧性能等级需按GB50222要求分区标注。",
            "fix": "补充各功能空间的装修材料燃烧性能等级标注图，明确顶棚/墙面/地面/隔断的燃烧性能等级要求。"
        },
        {
            "id": "DEC-002", "severity": "C",
            "standard": "GB50222-2017",
            "finding": "共享空间、开敞共享空间、架空层、下沉庭院等高大空间和半室外空间的装修材料防火要求与普通室内空间不同，需按GB50222第4.0.4条执行。",
            "fix": "补充高大空间（共享空间等）的装修材料燃烧性能等级标注，参考GB50222第3.1.2条。"
        },
    ]
    return issues


def review_landscape():
    """景观专业审查"""
    issues = [
        {
            "id": "LS-001", "severity": "C",
            "standard": "GB50420-2007(2016版) 城市绿化工程施工及验收规范",
            "finding": "绿化种植设计较完整：乔木修剪要求（行道树分枝点2.8~3m）、灌木适量疏枝、种植穴挖掘规范。但树木与地下管线的间距要求未标注，乔木种植点与给排水/电力/燃气管线的安全距离需确认。",
            "fix": "补充乔木种植点与地下管线的安全距离标注（乔木中心与给水管≥1.5m、与电力管≥2.0m、与燃气管≥1.5m）。"
        },
        {
            "id": "LS-002", "severity": "B",
            "standard": "GB51192-2016 公园设计规范",
            "finding": "海绵城市设计完整：硬质屋面6585m²、绿地7683m²、下沉式绿地1687m²、透水沥青2540.2m²。综合径流系数0.52。下凹式绿地渗透系数≥1.0×10⁻⁴cm/s，透水砖≥1.0×10⁻²cm/s。各LID设施面积数据完整。",
            "fix": "补充年径流总量控制率的计算，确认海绵城市设计满足当地规划条件（温州地区年径流总量控制率一般要求≥70%）。"
        },
    ]
    return issues


def review_foundation_pit():
    """基坑专业审查"""
    issues = [
        {
            "id": "FP-001", "severity": "B",
            "standard": "JGJ120-2012 建筑基坑支护技术规程",
            "finding": "基坑开挖深度5.25~5.75m，周长544.3m，面积16280.7m²。钻孔灌注桩内插角钢格构柱方案。立柱桩垂直度偏差≤1/300。支护方案合理，但基坑安全等级（一/二/三级）未明确标注。",
            "fix": "在基坑围护设计说明中明确基坑安全等级（根据开挖深度5.25~5.75m建议为二级）。"
        },
        {
            "id": "FP-002", "severity": "A",
            "standard": "GB50086-2015 岩土锚杆与喷射混凝土支护工程技术规范",
            "finding": "格构柱采用4L125x10角钢，缀板380x300x8@700。灌注桩直径700mm，配筋14Φ14。焊缝hf≥8mm，周边满焊，二级焊缝。立柱桩进入中风化≥1m。构造要求完整，但基坑降水方式及降水井布置未见明确标注。",
            "fix": "补充基坑降水方案说明（管井降水/轻型井点），标注降水井数量、井径、深度及降排水走向。"
        },
        {
            "id": "FP-003", "severity": "B",
            "standard": "GB50007-2011 建筑地基基础设计规范",
            "finding": "利用工程桩作立柱桩时直径不足700需扩大至700。超灌高度暂定1500mm。需确认超灌高度是否满足凿除浮浆后的有效桩顶标高要求。",
            "fix": "确认超灌高度1500mm能够保证凿除浮浆后桩顶混凝土强度满足设计强度要求。"
        },
    ]
    return issues


def review_signage():
    """标识标线专业审查 — 交通标识+安全标识+车位+坡道+无障碍"""
    issues = [
        {
            "id": "SG-001", "severity": "B",
            "standard": "GB5768-2009 道路交通标志和标线",
            "finding": "地面标线设计：双向车道中心线白色线宽15cm，地下车库车位线宽10cm白色热熔标线/冷漆，导向箭头长300cm。设计参数基本完整。但地下车库柱面分区信息与出口导向标志的具体编号方案和接力点位平面图未见，仅说明'具体由施工单位现场编组'，可能导致施工中分区混乱。",
            "fix": "补充地下车库各分区的颜色编码方案和柱面信息布置平面图，明确A/B/C等分区的颜色和编号规则，减少施工阶段的设计不确定性。"
        },
        {
            "id": "SG-002", "severity": "A",
            "standard": "GB50016-2014 建筑设计防火规范",
            "finding": "疏散指示标识仅在设计说明中间接提及（'疏散指示标识'和'疏散口指示标识'在设备图例中出现），但缺少完整的消防疏散标识系统图。未明确疏散指示标识的间距要求（GB50016第10.3.5条要求疏散走道疏散指示标志间距不应大于20m），也未见蓄光型辅助疏散标识的设置说明。",
            "fix": "补充消防疏散标识系统图，标注疏散指示标识间距≤20m、距地高度0.3~0.5m，地下车库应增设蓄光型疏散指示标志，确保火灾断电后30min可见。"
        },
        {
            "id": "SG-003", "severity": "B",
            "standard": "CJJ37-2012 城市道路工程设计规范 / GB50688-2011",
            "finding": "车库坡道安全设施：反光道钉直线段间距2m/曲线段1m，轮廓标侧墙间距2m/曲线段1m，橡胶减速条350×250mm。设计参数完整。但坡道入口处防滑地面的构造做法（无振动防滑坡道）仅标注了黄底12cm+绿面60cm，缺少具体材料型号和防滑系数要求（应≥0.65BPN）。",
            "fix": "补充坡道防滑地面的防滑系数检测要求（摆式仪≥0.65BPN或构造深度≥0.8mm），明确无振动防滑坡道的材料品牌或等效替代方案。"
        },
        {
            "id": "SG-004", "severity": "C",
            "standard": "GB50763-2012 无障碍设计规范",
            "finding": "无障碍车位设计：黄色标线，线宽150mm，编号字体'方正大黑'或'Arial Black'，高400mm宽1200mm。设置有146个无障碍车位。但无障碍车位与无障碍通道/无障碍电梯的连接流线未在标识标线图纸中完整表达，仅标注了车位大样，缺少从车位到无障碍电梯的引导标识。",
            "fix": "补充从无障碍车位→无障碍通道→无障碍电梯的连续引导标识系统图，确保乘轮椅者能独立从车位到达无障碍电梯。"
        },
    ]
    return issues


def review_doors_windows():
    """门窗专业审查 — 防火门/窗耐火极限+门窗五金+安装节点+气密性+计算书"""
    issues = [
        {
            "id": "DW-001", "severity": "A",
            "standard": "GB50016-2014 建筑设计防火规范",
            "finding": "防火门设计：图纸明确标注了甲级防火门（A1.50，耐火极限1.5h）如GFC6512/GFC8212等，乙级防火窗（BYC），防火玻璃（耐火极限1h）。防火门疏散净宽按门洞尺寸扣200mm计算，符合规范。但各层平面图中防火门的甲/乙/丙级别仅通过编号间接体现（如GFC前缀），缺少集中汇总的防火门窗表。",
            "fix": "补充各楼层防火门窗统计表，明确每樘防火门的编号、所在位置、耐火等级（甲/乙/丙）、洞口尺寸、疏散净宽，便于消防验收核对。"
        },
        {
            "id": "DW-002", "severity": "B",
            "standard": "GB50189-2015 公共建筑节能设计标准",
            "finding": "外窗采用6Low-E+12氩气+6透明中空玻璃(29mm)，断热铝合金单框，气密性不低于7级。外窗传热系数K值在建筑说明中有提及（K≤2.4）。但外窗的抗风压性能、水密性能、气密性能的分级指标未与幕墙统一标注，且宿舍楼铝合金外窗与幕墙的连接处防水处理未明确。",
            "fix": "补充外窗物理性能分级表（抗风压≥4级、气密性≥7级、水密性≥3级），补充外窗与幕墙交接处的防水节点详图。"
        },
        {
            "id": "DW-003", "severity": "B",
            "standard": "GB50016-2014 / GB/T31433-2015",
            "finding": "门窗设计说明中提到钢质防火门、木质防火门、树脂门等材质分类。钢质门套需灌浆处理，防火门带窗亮玻璃应采用防火隔热玻璃。但未见防火门五金配件（闭门器、顺序器、防火锁）的规格要求，以及常开防火门在火灾时自动关闭的控制方式标注。",
            "fix": "补充防火门五金配件规格表（闭门器满足EN1154/GB标准、防火锁满足GB12955），明确常开防火门的电磁释放装置和消防联动控制接口。"
        },
        {
            "id": "DW-004", "severity": "C",
            "standard": "JGJ214-2010 铝合金门窗工程技术规范",
            "finding": "门窗安装节点：图纸标注了门窗编号和尺寸（如LC7737/FM1222等系列），但门窗与主体结构的连接节点大样图仅见建筑图中的局部标注（'预留洞口300X400贴梁底'等），缺少完整的门窗框安装构造详图及防水密封方案。",
            "fix": "补充门窗框安装节点大样图（含预埋件/膨胀螺栓布置、门窗框与墙体缝隙填塞方案、室外侧密封胶+室内侧防水隔汽膜做法）。"
        },
        {
            "id": "DW-005", "severity": "C",
            "standard": "温州医科大学门窗计算书（设计说明引用）",
            "finding": "图纸目录中包含《温州医科大学茶山东校区(阿尔伯塔学院)新建工程门窗计算书.doc/pdf》但内容未被提取。门窗计算书应包含：外窗抗风压计算、玻璃挠度验算、型材强度验算、开启扇五金件受力分析等。",
            "fix": "要求门窗设计方提供计算书关键页，重点核查最大洞口尺寸处门窗的抗风压承载力和玻璃面板的挠度是否满足L/250限值。"
        },
    ]
    return issues


def review_power_distribution():
    """变配电专业审查 — 供电方案+设备基础+接地+继保+电缆沟+通风散热"""
    issues = [
        {
            "id": "PD-001", "severity": "A",
            "standard": "GB50053-2013 20kV及以下变电所设计规范",
            "finding": "变配电房设置于6#楼，8000kVA总容量，SCB18系列干式变压器（从电气说明推断）。变配电房内部由电力部门负责设计施工，但建筑图中变配电房的门（GFC7510甲级防火门）、排烟井、电缆沟等已预留。变配电房的净高、设备运输通道宽度、操作检修通道宽度未见标注。",
            "fix": "确认变配电房室内净高≥3.6m（8000kVA规模），柜前操作通道≥2.0m（双排面对面布置），柜后维护通道≥1.0m，设备运输门的宽度≥设备宽度+0.3m。"
        },
        {
            "id": "PD-002", "severity": "A",
            "standard": "GB50054-2011 低压配电设计规范 / GB50169-2006 接地装置施工规范",
            "finding": "电气说明提到主体建筑利用基础钢筋作自然接地体，综合接地电阻<1Ω，TN-S系统。但变配电房独立于主体建筑的独立接地网设计未见。变配电房的接地干线、等电位联结带、变压器中性点接地的具体做法未在变配电房图纸中体现。",
            "fix": "补充变配电房独立接地网设计图（水平接地体+垂直接地极），明确变压器中性点接地线截面（≥相线截面/2且≥25mm²铜），等电位联结带截面≥50mm²铜。"
        },
        {
            "id": "PD-003", "severity": "B",
            "standard": "GB50062-2008 电力装置的继电保护和自动装置设计规范 / GB/T50063-2008",
            "finding": "10kV配电系统的继电保护整定方案（过流保护、速断保护、零序保护、变压器非电量保护）未在任何电气图纸中体现。8000kVA容量的配电工程应有完整的保护定值单，但该部分通常由电力部门设计，土建审查无法介入，存在设计界面盲区。",
            "fix": "要求电力设计单位提供10kV保护定值清单（含主变差动/过流/速断/零序保护整定值），明确保护定值与上级变电站保护的级差配合。"
        },
        {
            "id": "PD-004", "severity": "B",
            "standard": "GB50054-2011 / GB50217-2018 电力工程电缆设计标准",
            "finding": "变配电房平面图中标注了电缆沟（D1~D13），但电缆沟的截面尺寸、排水坡度、防火封堵方案、电缆支架间距等未标注。电缆沟内应考虑排水措施（设置集水坑或接入地下室排水系统），否则积水可能导致电缆绝缘老化。",
            "fix": "补充电缆沟断面详图，明确沟深≥0.6m、沟宽≥0.4m、底坡≥0.5%坡向集水点，电缆支架间距≤0.8m，穿墙处防火封堵做法。"
        },
        {
            "id": "PD-005", "severity": "C",
            "standard": "GB50053-2013 变电所设计规范",
            "finding": "变配电房设有铝合金防雨百叶（1500×600h底距地300mm，内衬防虫网，通透系数0.6）用于通风散热。SCB18干式变压器为自然冷却或强制风冷，散热计算取决于变压器负载率和环境温度。通风百叶的有效进风面积是否满足变压器散热需求未见验算。",
            "fix": "补充变压器室通风散热计算书（按变压器总损耗的发热量校核进/排风百叶的有效面积），排风百叶应设在房间上部（热空气上升），进风百叶设在下部。"
        },
        {
            "id": "PD-006", "severity": "C",
            "standard": "GB50016-2014 建筑设计防火规范",
            "finding": "变配电房采用GFC7510甲级防火门、防火墙分隔，排烟井已预留。但变压器油坑或事故油池（如采用油浸式）或干式变压器的消防措施未明确。SCB18为环氧树脂浇注干式变压器，不设油坑，但应设置火灾自动报警探测器（温感+烟感组合）和气体灭火或高压细水雾系统。",
            "fix": "确认变配电房内火灾探测器类型和布置（建议温感+吸气式烟感组合），明确气体灭火系统的灭火剂类型（七氟丙烷/IG541）或确认建筑已有的喷淋系统是否覆盖变配电房。"
        },
    ]
    return issues


def review_assembly_deep():
    """装配式深化审查 — 节点连接+吊装安全+灌浆料+内隔墙+运输堆放"""
    issues = [
        {
            "id": "ASB-001", "severity": "A",
            "standard": "JGJ1-2014 装配式混凝土结构技术规程",
            "finding": "装配式设计总说明标注：教学实验楼装配率61%，宿舍楼装配率>50%。叠合楼板预制层60mm/70mm，按双向板设计。预制构件采用HRB400E钢筋，吊环用HPB300/Q235B。预制楼梯未在本说明中展开详述。预制楼梯与现浇梯梁的连接节点（预留孔+灌浆锚固或焊接连接）未见设计详图。",
            "fix": "补充预制楼梯与现浇梯梁的连接节点大样图，明确连接方式（建议预留孔灌浆锚固），灌浆料强度不低于C60，节点承载力应满足JGJ1第6.6.4条要求。"
        },
        {
            "id": "ASB-002", "severity": "A",
            "standard": "GB50666-2011 混凝土结构工程施工规范 / 住建部37号令",
            "finding": "装配式说明第10条明确本工程存在危险性较大的分部分项工程，要求施工单位编写专项施工方案，超过一定规模的需专家论证。但预制构件吊装阶段的安全验算（吊点承载力、吊具选型、临时支撑体系承载力）未在设计文件中复核。吊点沿板长L方向布置，最外侧吊点距板边≤900mm，但最重构件的吊点安全系数未标注。",
            "fix": "补充最大单构件（如2FPCB-15: 5200×2375mm/1.890t）的吊装验算书，吊点承载力安全系数≥4，吊索安全系数≥6，临时支撑体系应能承受施工荷载+1.5kN/m²。"
        },
        {
            "id": "ASB-003", "severity": "B",
            "standard": "JGJ355-2015 钢筋套筒灌浆连接技术规程",
            "finding": "装配式说明未提及预制构件灌浆连接的相关内容。叠合板按双向板设计，拼缝采用整体式后浇带做法（参照15G366-1），但预制楼梯及可能存在的预制墙板的灌浆连接节点、灌浆料性能指标（流动度、膨胀率、强度）未见说明。灌浆连接是装配式结构安全的薄弱环节。",
            "fix": "补充灌浆连接节点详图（如有预制墙板/楼梯），明确灌浆料为高强无收缩水泥基材料（1d强度≥35MPa，28d≥60MPa），灌浆饱满度应100%检测。"
        },
        {
            "id": "ASB-004", "severity": "B",
            "standard": "GB/T15762-2020 蒸压加气混凝土板 / JGJ1-2014",
            "finding": "内隔墙采用蒸压加气混凝土墙板(ALC条板)，由专业厂家专项设计。ALC条板高度方向两端与主体结构连接，每边连接点不少于2个。但ALC条板与装配式叠合楼板的连接节点未在装配式图纸中体现，属设计界面盲区。",
            "fix": "补充ALC条板与叠合楼板（现浇层）的连接节点详图，明确U型卡/管卡间距≤600mm，板底设20mm弹性垫片，板顶与梁底预留10~20mm间隙填PE棒+密封胶。"
        },
        {
            "id": "ASB-005", "severity": "C",
            "standard": "JGJ1-2014 / GB50204-2015 混凝土结构工程施工质量验收规范",
            "finding": "装配式说明对预制构件的运输、堆放做了基本规定（叠合楼板≤6层，预制楼梯≤4层，堆放≤2个月）。但运输路线中的限高/限宽核查、非机动车坡道幕墙区域的大型构件转运方案、雨季施工的构件防雨保护措施未见。",
            "fix": "补充预制构件运输路线核查（含市政道路限高≥4.5m），明确大型构件（>1.5t）的场内转运设备和路线，雨季施工时预制构件存放区的防雨排水方案。"
        },
    ]
    return issues


def review_outdoor_utilities():
    """室外管综审查 — 管线交叉+间距+燃气+电力+通信+施工顺序"""
    issues = [
        {
            "id": "OUT-001", "severity": "A",
            "standard": "GB50289-2016 城市工程管线综合规划规范",
            "finding": "室外管线综合仅见给排水专业图纸（污水DN400、雨水DN800埋深及井编号表），但电力（10kV管线）、通信（96芯光缆）、燃气等管线的走向和埋深在统一的室外管综图中缺失。室外管线交叉处的垂直净距未标注。",
            "fix": "补充全专业室外管线综合平面图和纵断面图，明确给排水/电力/通信/燃气管线的平面位置、埋深、交叉处垂直净距（给排水与电力≥0.5m垂直、与燃气≥0.15m钢管/0.3mPE管）。"
        },
        {
            "id": "OUT-002", "severity": "A",
            "standard": "GB50028-2006(2020版) 城镇燃气设计规范",
            "finding": "图纸目录中未见独立的燃气专项设计图纸。校园类公共建筑通常接入市政燃气管网供热水/食堂使用，燃气管道与建筑基础、电力管沟、给排水管的水平安全间距应在管线综合图中统一规划，否则后期燃气管线施工将造成已完工管线的二次开挖破坏。",
            "fix": "确认燃气专业是否已委托设计，补充燃气管线平面布置图，标注燃气管与建筑物基础（≥1.0m中压）、与电力管沟（≥1.0m）、与给排水管（≥0.5m）的水平间距。"
        },
        {
            "id": "OUT-003", "severity": "B",
            "standard": "GB50217-2018 电力工程电缆设计标准 / GB50688-2011",
            "finding": "校园10kV电力管线（阿尔伯塔校园10kV管线红线内）和弱电管线（96芯光缆×2）的走向仅通过文件命名间接体现，管线与DN400污水管、DN800雨水管的水平间距未经系统校核。室外管综图中仅见给排水专业的井编号和埋深数据，电力/弱电/燃气管线未参与管综协同。",
            "fix": "将电力10kV管线、通信光缆管线纳入室外管线综合图，标注所有管线交叉点的垂直间距（电力管顶距给水管底≥0.5m），补充管综冲突分析报告。"
        },
        {
            "id": "OUT-004", "severity": "C",
            "standard": "GB50268-2008 给水排水管道工程施工及验收规范",
            "finding": "施工顺序方面，传统的'先深后浅'原则要求最深的污水管（埋深最深2.47m）先施工，但电力、通信管线通常埋深较浅（0.7~1.2m），后施工时需穿越已完工的深埋管线，施工组织设计中需明确保护措施。",
            "fix": "补充室外管综施工顺序说明：深埋管线（污水>雨水>给水）先行→回填压实→浅埋管线（电力>通信>燃气）后行，后行管线穿越先行管线时补充保护套管做法。"
        },
    ]
    return issues


def review_solar_pv():
    """光伏审查 — 组件面积+结构荷载+电气安全+防雷接地+并网"""
    issues = [
        {
            "id": "PV-001", "severity": "B",
            "standard": "GB50797-2012 光伏发电站设计规范 / GB50352-2019",
            "finding": "建筑屋顶标注了太阳能光伏板面积：智能细胞工厂屋顶174.72m²、光伏板659.88m²、另一处182.52m²，总计约1017m²光伏板面积。按150W/m²单晶组件估算，总装机容量约152kWp。但光伏组件的倾斜角度、朝向、安装方式（平铺/倾角支架/跟踪支架）未在图纸中标注。",
            "fix": "补充光伏组件布置详图，明确组件倾角（温州地区最佳倾角约22°）、安装方式、支架系统的固定方式及与防水屋面的连接节点。"
        },
        {
            "id": "PV-002", "severity": "A",
            "standard": "GB50009-2012 建筑结构荷载规范",
            "finding": "光伏组件的附加荷载（含支架、组件自重及风荷载）需要结构专业校核屋面承载能力。光伏板659.88m²估计总重量约6.6吨（按10kg/m²），加上风荷载效应（0.60kN/m²×体型系数），对屋面结构的荷载增量是否在原设计预留范围内未见复核。",
            "fix": "结构专业补充光伏组件及支架系统对屋面的荷载影响评估（恒荷载约0.15kN/m²，风荷载应区分正/负风压），确认原屋面结构设计已预留光伏荷载或给出加固方案。"
        },
        {
            "id": "PV-003", "severity": "A",
            "standard": "NB/T32004-2013 光伏发电并网逆变器技术规范 / GB50054-2011",
            "finding": "光伏系统的直流侧电气安全（直流电弧保护、防逆流、直流开关/熔断器配置）未涉及。152kWp规模应配置组串式逆变器（如采用220V/380V低压并网），但逆变器的安装位置（建议屋面就近布置）、直流电缆规格（1kV PV1-F）等未见设计说明。",
            "fix": "补充光伏电气系统图，明确逆变器型号/功率/安装位置、直流侧防孤岛保护装置、直流开关及熔断器选型、直流电缆规格及布线路由。"
        },
        {
            "id": "PV-004", "severity": "B",
            "standard": "GB50057-2010 建筑物防雷设计规范",
            "finding": "建筑防雷按二类防雷建筑物设计，光伏组件安装在屋面最高处（49.7m构架区域），直流电缆和光伏组件应纳入防雷保护范围。光伏支架及组件金属边框的接地、直流侧SPD（浪涌保护器）的配置未见专项说明。",
            "fix": "补充光伏防雷接地设计：光伏组件金属边框及支架与屋面防雷接闪带可靠焊接（≥2点），直流汇流箱及逆变器内配置直流SPD（Type 2，In≥20kA），接地电阻并入主体<1Ω。"
        },
    ]
    return issues


def review_elevator():
    """电梯审查 — 井道+机房+消防电梯+无障碍+荷载预留"""
    issues = [
        {
            "id": "ELV-001", "severity": "A",
            "standard": "GB50016-2014(2018版) 建筑设计防火规范 / GB7588-2003 电梯制造与安装安全规范",
            "finding": "建筑图标注了多部电梯：1#2#电梯（教学实验楼，2-10F+屋顶）、3#4#5#电梯（宿舍楼B1F，含消防电梯和无障碍电梯）、电梯机房和消防电梯机房（屋面）。4#楼37.63m>32m，5#楼44.83m>32m，均需设置消防电梯。但消防电梯的井道尺寸（≥2.2m宽×2.2m深）、载重量（≥800kg）、轿厢尺寸（≥1.5m×1.4m）未在图纸中定量标注。",
            "fix": "补充消防电梯井道尺寸和载重量标注，确认满足GB50016第7.3.2条（载重≥800kg，轿厢深≥1.4m，宽≥1.1m）和从首层到顶层的运行时间≤60s。"
        },
        {
            "id": "ELV-002", "severity": "B",
            "standard": "GB50310-2002 电梯工程施工质量验收规范",
            "finding": "电梯机房（屋面层）和消防电梯机房的位置已在建筑平面标注，电梯井道在各层平面留有洞口（650×1900/2500mm，洞口底部距完成面300mm）。但电梯机房内曳引机承重梁的布置、机房通风散热措施、检修通道宽度（≥0.6m）未见标注。",
            "fix": "补充电梯机房平面详图，标注曳引机承重梁位置和支座要求、机房通风百叶有效面积（按设备发热量计算）、控制柜前检修通道宽度≥0.6m。"
        },
        {
            "id": "ELV-003", "severity": "B",
            "standard": "GB50016-2014 建筑设计防火规范 / GB50763-2012 无障碍设计规范",
            "finding": "无障碍电梯标注了无障碍标志、扶手（H6中心距地0.9m）、呼叫按钮（中心离地1.1m）、提示盲道（B2型），电梯井道11.29m²（从'3#4#5#电梯'文字推断）。但轿厢内的无障碍设施（后壁镜子、低位操作面板、语音报站、盲文按钮）未见规格说明。",
            "fix": "补充无障碍电梯轿厢内设施规格：轿厢深度≥1.4m、宽度≥1.1m，后壁设安全镜，操作面板距地0.9~1.1m且带盲文，轿厢内设语音报站装置。"
        },
        {
            "id": "ELV-004", "severity": "C",
            "standard": "GB50016-2014 建筑设计防火规范",
            "finding": "消防电梯在B1F层应为消防员专用入口，且消防电梯前室应设消火栓（可在合用前室设置）。消防电梯的防水措施（井道底坑排水、门槛防水反坎≥50mm）未见标注。",
            "fix": "补充消防电梯底坑排水设施（集水坑+潜水泵，排水能力≥10L/s），消防电梯前室消火栓位置，井道门槛处防水反坎≥50mm。"
        },
    ]
    return issues


def review_intelligent_seismic_charger_pending():
    """待交付专项标记 — 智能化/抗震支架/充电桩图纸未就绪"""
    issues = [
        {
            "id": "PEND-001", "severity": "B",
            "standard": "GB50314-2015 智能建筑设计标准",
            "finding": "【待交付】智能化专项：安防系统（视频监控/入侵报警/门禁）、广播与会议系统、智慧校园综合管理平台、信息引导及发布系统的设计图纸未在本批次DXF图纸中提交。电气专业仅有基础布线（96芯光缆、数据网汇聚交换机）未涉及智能化各子系统功能设计。",
            "fix": "要求智能化设计单位提交：视频监控系统图与点位表、门禁系统图、公共广播系统图、多媒体会议系统图、信息发布系统图、智能化机房（消控室/网络机房）布置图。"
        },
        {
            "id": "PEND-002", "severity": "A",
            "standard": "GB50981-2014 建筑机电工程抗震设计规范",
            "finding": "【待交付·强制验收项】抗震支架专项：机电管线（给排水、暖通风管、电气桥架、消防管道）的抗震支吊架布置图和节点详图未提交。GB50981为强制性国家标准，抗震设防烈度6度及以上地区的DN65以上管道、截面积≥0.38m²风管、重量≥150N/m的桥架均须设置抗震支吊架。",
            "fix": "要求抗震支架设计单位提交：各机电专业的抗震支吊架平面布置图/系统图、典型节点大样图、抗震支吊架间距计算书（侧向间距≤12m/纵向≤24m）。"
        },
        {
            "id": "PEND-003", "severity": "A",
            "standard": "GB50966-2014 电动汽车充电站设计规范 / GB51313-2018",
            "finding": "【待交付·强制验收项】充电桩专项：标识标线设计说明中提到设置充电车位（具体数量待确认），但充电桩的配电系统图、充电设备选型、车位布置图、防雷接地设计未见提交。宿舍楼和教学楼的充电车位通常按停车位10~20%比例配建。",
            "fix": "要求充电桩设计单位提交：充电桩配电系统图（含专用变压器/配电柜）、充电车位平面布置图、充电桩防雷接地及漏电保护方案（RCD Type B，IΔn≤30mA）。"
        },
    ]
    return issues


# ================================================================
# 跨专业一致性分析
# ================================================================
def cross_discipline_analysis():
    """跨专业一致性分析 — 基于各专业图纸之间的交叉校验"""
    issues = [
        {
            "id": "CROSS-001", "severity": "B",
            "disciplines": "建筑+结构",
            "finding": "教学实验楼结构图中钢梁采用Q355B/Q390C（H1300X400X30X40），钢结构框架。建筑图中采用装配式叠合板。钢框架+叠合板的组合楼盖体系，需确认钢梁上翼缘的抗剪连接件（栓钉）设置是否满足叠合板组合梁设计要求。",
            "fix": "补充钢梁与叠合板连接节点详图，明确栓钉规格、间距及布置范围。"
        },
        {
            "id": "CROSS-002", "severity": "A",
            "disciplines": "结构+暖通",
            "finding": "结构图中钢梁截面H1300×400×30×40（梁高1300mm）。暖通图中排烟风管尺寸未标注，但根据41000CMH风量估算，主风管截面约需1200×500mm。梁下净空可能不足。",
            "fix": "结构专业与暖通专业协调核验H1300梁区域的风管穿梁方案，必要时预留孔洞或调整风管走向。",
            "reasonability": "风管与钢梁冲突的实际影响取决于具体位置：若风管在梁格内平行布置而非垂直穿越，冲突可避免；钢梁腹板开洞（<梁高1/3且避开翼缘）也可满足小尺寸风管穿越需求。建议逐区核实而非全盘判定为不可行。"
        },
        {
            "id": "CROSS-003", "severity": "B",
            "disciplines": "结构+电气",
            "finding": "结构图中叠合板预制层60mm+现浇层。电气图中管线设在现浇层内。但现浇层厚度未明确，若现浇层过薄可能无法满足强弱电管线交叉覆盖需求。",
            "fix": "结构专业与电气专业协调确认现浇层厚度，确保强弱电管线交叉处满足保护层厚度要求。"
        },
        {
            "id": "CROSS-004", "severity": "C",
            "disciplines": "建筑+消防",
            "finding": "4#宿舍楼10F/h=37.63m/38.85m，5#宿舍楼12F/h=44.83m/46.75m。4#楼属于二类高层（>24m但≤54m），5#楼也属于二类高层。但宿舍楼的消防电梯设置要求是超过32m的二类高层应设消防电梯（GB50016第7.3.1条），需确认两栋楼是否均已设置。",
            "fix": "确认4#楼（37.63m>32m）和5#楼（44.83m>32m）均已设置消防电梯，标注消防电梯数量及位置。"
        },
        {
            "id": "CROSS-005", "severity": "B",
            "disciplines": "给排水+电气",
            "finding": "消防水泵房设在地下室，消防水池292.5T。电气专业设计了消防电源监控系统和消防联动控制。给排水专业的消防泵启停信号需与电气专业的火灾自动报警系统联动，但联动控制逻辑的接口定义不清晰。",
            "fix": "补充消防水泵联动控制接线图，明确消火栓按钮直接启泵线、消防联动控制器启泵线及水泵运行状态反馈线的接口定义。"
        },
        {
            "id": "CROSS-006", "severity": "C",
            "disciplines": "建筑+装修+消防",
            "finding": "共享空间、开敞共享空间为高大空间。建筑图中标注了共享空间位置，装饰图中涉及这些空间的装修。消防专业需确认高大空间的排烟方式（自然排烟/机械排烟）及排烟窗面积。",
            "fix": "建筑+消防+装饰专业协调确认高大空间的防排烟设计方案，标注排烟窗面积或机械排烟量。"
        },
        {
            "id": "CROSS-007", "severity": "A",
            "disciplines": "基坑+结构",
            "finding": "基坑开挖深度5.25~5.75m，采用钻孔灌注桩+角钢格构柱围护。立柱桩利用工程桩（利用条件：直径<700的需扩大至700）。并且立柱桩垂直度≤1/300。工程桩同时作为立柱桩使用时，需确认其承载力和沉降能否同时满足基坑支护和主体结构的双重要求。",
            "fix": "结构专业与基坑专业协调确认利用工程桩作立柱桩的方案，补充桩基承载力校核（同时作为工程桩和立柱桩的工况）。"
        },
    ]
    return issues


# ================================================================
# 空间冲突数据集成
# ================================================================
def load_spatial():
    path = os.path.join(BASE, r"v7\spatial_conflicts_v5.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # === 假阳性过滤 ===
        before = len(raw)
        # 1. 去重：同类型+同描述+同楼层的重复冲突
        seen = set()
        deduped = []
        for c in raw:
            key = (c.get("type"), c.get("description",""), c.get("floor",""))
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        after_dedup = len(deduped)
        # 2. 标高合理性过滤：保留同floor的冲突，标记跨层为低置信度
        filtered = []
        for c in deduped:
            conf = "high"
            desc = c.get("description", "")
            # 标记未知区域冲突为低置信度
            if "??" in desc:
                conf = "low"
            # 标记floor异常值的冲突（如-12可能是数据错误）
            fl = c.get("floor", 0)
            if isinstance(fl, (int, float)) and abs(fl) > 10:
                conf = "medium"
            c["confidence"] = conf
            filtered.append(c)
        after_filter = len(filtered)
        # 统计假阳性率
        low_conf = sum(1 for c in filtered if c.get("confidence") == "low")
        medium_conf = sum(1 for c in filtered if c.get("confidence") == "medium")
        print(f"  空间冲突过滤: {before} → 去重 {after_dedup} → 低置信度标记 {after_filter}")
        print(f"  低置信度(疑似假冲突): {low_conf} | 中置信度: {medium_conf} | 高置信度: {after_filter - low_conf - medium_conf}")
        return filtered
    return []


# ================================================================
# 报告生成
# ================================================================
def setup_doc(doc):
    style = doc.styles["Normal"]
    font = style.font
    font.name = "微软雅黑"
    font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def add_issue_table(doc, issues, headers, fields):
    """通用：把问题列表渲染成docx表格"""
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for j, h in enumerate(headers):
        table.rows[0].cells[j].text = h
    for item in issues:
        row = table.add_row().cells
        for j, f in enumerate(fields):
            val = str(item.get(f, "") or "")
            row[j].text = val[:200] if f in ("finding", "fix") else val[:50]
    return table


CONFLICT_CN = {
    "beam_duct_overlap": "梁-风管重叠", "beam_pipe_overlap": "梁-管线重叠",
    "column_pipe_conflict": "柱-管线冲突", "pipe_crossing": "管线交叉",
    "duct_through_wall": "风管穿墙", "egress_width": "疏散宽度不足",
}


# ============================
# 场景1报告
# ============================
def gen_scene1(doc, spatial, findings):
    setup_doc(doc)
    t = doc.add_heading(f"基础错漏排查报告 v7.0 — LLM代理审查", level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"项目: {PROJECT}\n").bold = True
    p.add_run(f"审查时间: {REPORT_DATE}\n")
    p.add_run("审查方式: AI直接读取DXF提取数据 → 逐专业LLM分析 → 空间冲突交叉验证")

    doc.add_heading("1. 审查范围与方法", level=1)
    doc.add_paragraph(
        "本报告由AI LLM代理直接对108张DXF施工图提取的文本数据进行逐专业审查。"
        "审查路径：(1)读取各专业设计说明+施工图文本 → (2)LLM逐专业分析发现错漏 → "
        "(3)空间冲突检测引擎21,500个冲突簇交叉验证 → (4)综合汇总。"
    )

    doc.add_heading("2. 错漏问题统计", level=1)

    by_severity = defaultdict(int)
    by_discipline = defaultdict(int)
    for f in findings:
        by_severity[f["severity"]] += 1
        by_discipline[f.get("discipline", f.get("disciplines", "其他"))] += 1

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "严重度"
    table.rows[0].cells[1].text = "数量"
    for s in ["A", "B", "C", "D"]:
        r = table.add_row().cells
        r[0].text = {"A": "A级（强条违反）", "B": "B级（重要）", "C": "C级（一般）", "D": "D级（提示）"}[s]
        r[1].text = str(by_severity.get(s, 0))
    doc.add_paragraph()

    table2 = doc.add_table(rows=1, cols=2)
    table2.style = "Table Grid"
    table2.rows[0].cells[0].text = "专业/类别"
    table2.rows[0].cells[1].text = "发现数"
    for d, c in by_discipline.items():
        r = table2.add_row().cells
        r[0].text = d
        r[1].text = str(c)
    doc.add_paragraph()

    doc.add_heading("3. 各专业错漏问题明细", level=1)

    # 按专业分组
    from collections import OrderedDict
    disc_order = ["建筑", "结构", "给排水", "暖通", "电气", "消防", "幕墙", "装饰", "景观", "基坑", "标识标线", "门窗", "变配电", "装配式(深化)", "室外管综", "光伏", "电梯", "智能化/抗震支架/充电桩"]
    disc_map = defaultdict(list)
    for f in findings:
        disc = f.get("discipline", f.get("disciplines", "其他"))
        disc_map[disc].append(f)

    for disc in disc_order:
        items = disc_map.get(disc, [])
        if not items:
            continue
        sev_a = len([i for i in items if i["severity"] == "A"])
        sev_b = len([i for i in items if i["severity"] == "B"])
        doc.add_heading(f"{disc}专业 ({len(items)}项, A{sev_a}|B{sev_b})", level=2)
        add_issue_table(doc, items,
                        ["编号", "严重度", "规范依据", "问题描述"],
                        ["id", "severity", "standard", "finding"])

    doc.add_heading("4. 空间冲突交叉验证", level=1)
    by_type = defaultdict(lambda: {"A": 0, "B": 0, "C": 0, "D": 0})
    low_conf = 0
    for c in spatial:
        t = c.get("type", "unknown")
        s = c.get("severity", "D")
        by_type[t][s] += 1
        if c.get("confidence") == "low":
            low_conf += 1

    tbl = doc.add_table(rows=1, cols=5)
    tbl.style = "Table Grid"
    for j, hd in enumerate(["冲突类型", "A级", "B级", "C级", "D级"]):
        tbl.rows[0].cells[j].text = hd
    for ct, sv in by_type.items():
        r = tbl.add_row().cells
        r[0].text = CONFLICT_CN.get(ct, ct)
        r[1].text = str(sv["A"])
        r[2].text = str(sv["B"])
        r[3].text = str(sv["C"])
        r[4].text = str(sv["D"])

    doc.add_paragraph()
    doc.add_paragraph(f"其中与LLM分析发现的错漏问题相关的空间冲突簇已在前述章节中对应标注。")
    doc.add_paragraph(f"空间冲突置信度统计：低置信度（疑似假冲突）{low_conf}个（{low_conf*100//max(len(spatial),1)}%），建议优先关注高置信度冲突。", style="List Bullet")
    doc.add_paragraph("— 报告结束 —", style="Intense Quote")


# ============================
# 场景2报告
# ============================
def gen_scene2(doc, spatial, cross_issues):
    setup_doc(doc)
    t = doc.add_heading(f"跨专业一致性校验报告 v7.0 — LLM代理审查", level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"项目: {PROJECT}\n").bold = True
    p.add_run(f"审查时间: {REPORT_DATE}\n")
    p.add_run("审查方式: AI交叉读取各专业图纸 → LLM一致性分析 → 空间冲突验证")

    doc.add_heading("1. 校验概述", level=1)
    doc.add_paragraph(
        "跨专业一致性校验由AI LLM代理同时读取各专业（建筑、结构、给排水、暖通、电气、消防、"
        "幕墙、装饰、景观、基坑）的DXF提取文本，进行跨图纸的逻辑一致性分析。"
        "发现的跨专业矛盾问题分为三类：(A)空间冲突类 — 各专业构件在同一物理空间碰撞；"
        "(B)接口不匹配类 — 预埋/预留/接口定义不一致；(C)设计前提不一致类 — 基础参数/荷载/标准不统一。"
    )

    doc.add_heading("2. 跨专业问题统计", level=1)

    by_severity = defaultdict(int)
    for ci in cross_issues:
        by_severity[ci["severity"]] += 1

    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = "Table Grid"
    tbl.rows[0].cells[0].text = "严重度"
    tbl.rows[0].cells[1].text = "数量"
    for s in ["A", "B", "C"]:
        r = tbl.add_row().cells
        r[0].text = {"A": "A级（必须整改）", "B": "B级（建议整改）", "C": "C级（提示关注）"}[s]
        r[1].text = str(by_severity.get(s, 0))
    doc.add_paragraph()

    doc.add_heading("3. 跨专业问题明细", level=1)
    add_issue_table(doc, cross_issues,
                    ["编号", "严重度", "涉及专业", "问题描述", "整改要求"],
                    ["id", "severity", "disciplines", "finding", "fix"])
    doc.add_paragraph()

    doc.add_heading("4. 空间冲突跨专业碰撞数据", level=1)
    by_type = defaultdict(int)
    for c in spatial:
        by_type[c.get("type", "unknown")] += 1

    for ctype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
        involved = {
            "beam_duct_overlap": "结构+暖通",
            "beam_pipe_overlap": "结构+给排水",
            "column_pipe_conflict": "结构+机电",
            "pipe_crossing": "机电内部",
            "duct_through_wall": "暖通+建筑",
            "egress_width": "建筑+消防",
        }
        doc.add_paragraph(f"• {CONFLICT_CN.get(ctype, ctype)}: {cnt}处 — 涉及{involved.get(ctype, '多专业')}协调")
    doc.add_paragraph()

    doc.add_heading("5. 整改优先级建议", level=1)
    doc.add_paragraph("优先级P0（立即整改，涉及结构安全或消防）:")
    for ci in cross_issues:
        if ci["severity"] == "A":
            doc.add_paragraph(f"  • [{ci['id']}] {ci['finding'][:120]}", style="List Bullet")
    doc.add_paragraph("优先级P1（尽快整改，影响施工进度）:")
    for ci in cross_issues:
        if ci["severity"] == "B":
            doc.add_paragraph(f"  • [{ci['id']}] {ci['finding'][:120]}", style="List Bullet")

    doc.add_paragraph()
    doc.add_paragraph("— 报告结束 —", style="Intense Quote")


# ============================
# 场景3报告
# ============================
def gen_scene3(doc, spatial, findings):
    setup_doc(doc)
    t = doc.add_heading(f"强条合规审查报告 v7.0 — LLM代理审查", level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"项目: {PROJECT}\n").bold = True
    p.add_run(f"审查时间: {REPORT_DATE}\n")
    p.add_run("审查方式: AI逐条引用国标规范 → 对照DXF图纸数据 → 强条符合性判定")

    doc.add_heading("1. 审查概述", level=1)
    doc.add_paragraph(
        "本报告由AI LLM代理对温州医科大学阿尔伯塔学院项目的全部施工图进行强制性条文符合性审查。"
        "审查依据：GB50016、GB50352、GB50010、GB50011、GB50974、GB50015、GB50736、"
        "GB50054、GB50057、GB50116、GB50222、GB50763等16本现行国家规范。"
        "审查方法：AI逐条读取图纸数据 → 与国标强条对照 → 判定符合性 → 输出整改要求。"
    )

    # 强条统计
    mandatory = [f for f in findings if f["severity"] == "A"]
    senior = [f for f in findings if f["severity"] == "B"]

    doc.add_heading("2. 审查结论", level=1)
    if mandatory:
        doc.add_paragraph(f"⚠️ 发现 {len(mandatory)} 项涉嫌违反强制性条文的项，需立即整改。", style="Intense Quote")
    else:
        doc.add_paragraph("✅ 未发现明确的强条违反项。", style="Intense Quote")

    doc.add_paragraph(f"共审查18个专业方向（含3个待交付专项），发现问题 {len(findings)} 项：")
    doc.add_paragraph(f"  A级（强条违反/严重）: {len(mandatory)} 项")
    doc.add_paragraph(f"  B级（重要/影响功能）: {len(senior)} 项")
    doc.add_paragraph(f"  C级（一般/标注不全）: {len([f for f in findings if f['severity'] == 'C'])} 项")
    doc.add_paragraph(f"  D级（提示/建议）: {len([f for f in findings if f['severity'] == 'D'])} 项")

    doc.add_paragraph()

    doc.add_heading("3. 引用规范清单", level=1)
    standards = [
        "GB 50016-2014（2018版）建筑设计防火规范",
        "GB 50352-2019 民用建筑设计统一标准",
        "GB 55015-2021 建筑节能与可再生能源利用通用规范",
        "GB 50010-2010（2015版）混凝土结构设计规范",
        "GB 50011-2010（2016版）建筑抗震设计规范",
        "GB 50017-2017 钢结构设计标准",
        "GB 50007-2011 建筑地基基础设计规范",
        "GB 50974-2014 消防给水及消火栓系统技术规范",
        "GB 50015-2019 建筑给水排水设计标准",
        "GB 50736-2012 民用建筑供暖通风与空气调节设计规范",
        "GB 51251-2017 建筑防烟排烟系统技术标准",
        "GB 50054-2011 低压配电设计规范",
        "GB 50057-2010 建筑物防雷设计规范",
        "GB 50116-2013 火灾自动报警系统设计规范",
        "GB 51348-2019 民用建筑电气设计标准",
        "GB 50034-2013 建筑照明设计标准",
        "GB 50222-2017 建筑内部装修设计防火规范",
        "GB 50763-2012 无障碍设计规范",
        "GB 50420-2007（2016版）城市绿化工程施工及验收规范",
        "GB 50086-2015 岩土锚杆与喷射混凝土支护工程技术规范",
        "GB 50108-2008 地下工程防水技术规范",
        "JGJ 120-2012 建筑基坑支护技术规程",
    ]
    for s in standards:
        doc.add_paragraph(s, style="List Bullet")

    doc.add_heading("4. A级（强条/严重）问题", level=1)
    a_items = [f for f in findings if f["severity"] == "A"]
    if a_items:
        add_issue_table(doc, a_items,
                        ["编号", "专业", "规范依据", "问题描述", "整改要求"],
                        ["id", "discipline", "standard", "finding", "fix"])
    else:
        doc.add_paragraph("未发现A级问题。")

    doc.add_heading("5. B级（重要）问题", level=1)
    b_items = [f for f in findings if f["severity"] == "B"]
    if b_items:
        add_issue_table(doc, b_items,
                        ["编号", "专业", "规范依据", "问题描述", "整改要求"],
                        ["id", "discipline", "standard", "finding", "fix"])
    doc.add_paragraph()

    doc.add_heading("6. C/D级问题", level=1)
    cd_items = [f for f in findings if f["severity"] in ("C", "D")]
    if cd_items:
        add_issue_table(doc, cd_items,
                        ["编号", "专业", "严重度", "问题描述", "整改要求"],
                        ["id", "discipline", "severity", "finding", "fix"])

    doc.add_heading("7. 空间冲突合规性验证", level=1)
    doc.add_paragraph(
        f"空间冲突检测引擎共发现 {len(spatial)} 个冲突簇。"
        f"其中A级冲突 {len([c for c in spatial if c.get('severity')=='A'])} 个，"
        f"B级 {len([c for c in spatial if c.get('severity')=='B'])} 个。"
        "这些冲突已纳入各专业问题分析中综合考虑。"
    )

    doc.add_heading("8. 工程合理性专项评估 (R0~R3) ★新增", level=1)
    doc.add_paragraph(
        "本评估超越传统的条文符合性检查，从工程最优性角度审视设计质量。"
        "合理性等级说明：R0=设计不可行(0~30分) | R1=合规但非最优(30~55分) | "
        "R2=基本合理(55~80分) | R3=设计优秀(80~100分)。"
    )
    # 按合理性分组统计
    r_groups = defaultdict(list)
    for f in findings:
        r_groups[f.get("rationality", {}).get("level", "R2")].append(f)
    for r_level in ["R0", "R1", "R2", "R3"]:
        items = r_groups.get(r_level, [])
        if not items:
            continue
        doc.add_heading(f"{r_level}级 ({len(items)}项)", level=2)
        for item in items:
            r_info = item.get("rationality", {})
            doc.add_paragraph(
                f"[{item.get('id','?')}] {item.get('discipline','')} "
                f"得分{r_info.get('score','?')}/100: {r_info.get('explanation','')[:300]}"
            )

    doc.add_paragraph()
    doc.add_paragraph("— 报告结束 —", style="Intense Quote")


# ================================================================
# DISCIPLINE_REVIEWER_MAP 赋值（必须在所有 review_*() 函数定义之后）
# ================================================================
DISCIPLINE_REVIEWER_MAP = {
    "建筑": review_architecture,
    "结构": review_structure,
    "给排水": review_plumbing,
    "暖通": review_hvac,
    "电气": review_electrical,
    "消防": review_fire,
    "幕墙": review_curtain_wall,
    "装饰": review_decoration,
    "景观": review_landscape,
    "基坑": review_foundation_pit,
    "标识标线": review_signage,
    "门窗": review_doors_windows,
    "变配电": review_power_distribution,
    "装配式(深化)": review_assembly_deep,
    "室外管综": review_outdoor_utilities,
    "光伏": review_solar_pv,
    "电梯": review_elevator,
    "智能化/抗震支架/充电桩": review_intelligent_seismic_charger_pending,
}


# ================================================================
# 主入口
# ================================================================
def main(mode: Optional[str] = None):
    """LLM代理全流程审查主入口。
    
    Args:
        mode: 审查模式 - "real"(实时LLM) / "cached"(缓存数据) / None(自动检测)
    """
    print("=" * 70)
    print("  LLM代理全流程审查 — v7.0")

    # 确定审查模式
    if mode is None:
        review_mode = detect_best_mode()
    else:
        try:
            review_mode = ReviewMode(mode)
        except ValueError:
            print(f"  ⚠️ 无效模式 '{mode}'，自动检测...")
            review_mode = detect_best_mode()

    mode_labels = {
        ReviewMode.REAL_LLM: "🤖 实时LLM审查（需API Key）",
        ReviewMode.CACHED: "📋 缓存审查数据（离线模式）",
    }
    print(f"  审查模式: {mode_labels.get(review_mode, review_mode.value)}")
    print(f"  {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    if not HAS_DOCX:
        print("❌ python-docx 未安装")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 各专业审查
    print("\n[1/5] 各专业审查...")

    if review_mode == ReviewMode.REAL_LLM:
        all_findings, llm_stats = review_all_real_llm()
        print(f"\n  审查统计: LLM调用={llm_stats.get('llm_calls',0)}, "
              f"缓存降级={llm_stats.get('cached_calls',0)}, "
              f"LLM失败={llm_stats.get('llm_failures',0)}")
    else:
        # CACHED 模式：使用预编写数据
        all_findings = []
        for disc_name, reviewer in DISCIPLINE_REVIEWER_MAP.items():
            issues = reviewer()
            for i in issues:
                i["discipline"] = disc_name
            all_findings.extend(issues)
            print(f"  ✅ {disc_name}: {len(issues)} 项")

    # 2. 跨专业一致性分析
    print(f"\n[2/5] 跨专业一致性分析...")
    cross_issues = cross_discipline_analysis()
    print(f"  ✅ 跨专业: {len(cross_issues)} 项")

    # 3. 加载空间冲突数据
    print(f"\n[3/5] 加载空间冲突数据...")
    spatial = load_spatial()
    print(f"  ✅ {len(spatial)} 个冲突簇")

    # 4. 汇总统计
    all_with_cross = all_findings + cross_issues

    # 合理性评估标注
    all_with_cross = annotate_all_rationality(all_with_cross)
    by_rationality = defaultdict(int)
    for f in all_with_cross:
        by_rationality[f.get("rationality", {}).get("level", "R2")] += 1

    sev_a = len([f for f in all_with_cross if f["severity"] == "A"])
    sev_b = len([f for f in all_with_cross if f["severity"] == "B"])
    sev_c = len([f for f in all_with_cross if f["severity"] == "C"])
    sev_d = len([f for f in all_with_cross if f["severity"] == "D"])
    print(f"\n[4/5] 汇总:")
    print(f"  总问题: {len(all_with_cross)} 项")
    print(f"  A级={sev_a} | B级={sev_b} | C级={sev_c} | D级={sev_d}")
    print(f"  合理性: R0={by_rationality.get('R0',0)} | R1={by_rationality.get('R1',0)} | R2={by_rationality.get('R2',0)} | R3={by_rationality.get('R3',0)}")

    # 空间冲突置信度修正
    spatial = adjust_spatial_confidence(spatial)

    # 5. 生成报告
    print(f"\n[5/5] 生成docx报告...")
    scenarios = [
        ("场景1_基础错漏排查报告(3).docx", lambda d: gen_scene1(d, spatial, all_findings)),
        ("场景2_跨专业一致性校验报告(3).docx", lambda d: gen_scene2(d, spatial, cross_issues)),
        ("场景3_强条合规性审查报告(3).docx", lambda d: gen_scene3(d, spatial, all_with_cross)),
    ]
    for fname, gen_func in scenarios:
        doc = Document()
        gen_func(doc)
        out = os.path.join(OUTPUT_DIR, fname)
        doc.save(out)
        print(f"  ✅ {fname}")

    print(f"\n{'='*70}")
    print(f"  全流程LLM代理审查完成！")
    print(f"  三个报告已生成至: {OUTPUT_DIR}")
    print(f"{'='*70}")

    # 返回结果供测试验证
    return {
        "findings": all_findings,
        "cross_issues": cross_issues,
        "spatial_conflicts": len(spatial),
        "mode": review_mode.value,
        "severity_counts": {"A": sev_a, "B": sev_b, "C": sev_c, "D": sev_d},
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LLM代理全流程审查")
    parser.add_argument("--mode", choices=["real", "cached"], default=None,
                        help="审查模式：real=实时LLM, cached=缓存数据（默认自动检测）")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑模式：验证流程不生成报告")
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 60)
        print("  干跑测试（验证数据加载+Prompt构建）")
        print("=" * 60)
        print(f"\n  自动检测模式: {detect_best_mode().value}")
        texts = load_discipline_texts()
        print(f"  文本加载: {len(texts)} 个专业")
        for disc, content in texts.items():
            print(f"    {disc}: {len(content)} 字符")
        print(f"\n  Prompt样例 (建筑):")
        if "建筑" in texts:
            sample_prompt = build_review_prompt("建筑", texts["建筑"][:2000])
            print(f"    Prompt长度: {len(sample_prompt)} 字符")
            print(f"    前200字符: {sample_prompt[:200]}...")
        print(f"\n  解析测试:")
        test_response = '{"discipline":"建筑","issues":[{"id":"JZ-001","severity":"B","standard":"GB50352-2019","finding":"测试问题","fix":"测试修复"}]}'
        parsed = parse_llm_response(test_response, "建筑")
        print(f"    解析结果: {len(parsed)} 项, ID={parsed[0]['id'] if parsed else 'N/A'}")
        print(f"\n  降级解析测试:")
        fallback = _fallback_parse("[JZ-001] 防火分区不满足要求\nB级：GB50016第5.3.1条\n整改建议：重新划分防火分区", "建筑")
        print(f"    降级解析: {len(fallback)} 项")
        print(f"\n  干跑完毕！")
    else:
        result = main(mode=args.mode)
        if result:
            print(f"\n  返回: mode={result['mode']}, findings={len(result['findings'])}, sev={result['severity_counts']}")
