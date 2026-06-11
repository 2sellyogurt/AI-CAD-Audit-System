# -*- coding: utf-8 -*-
"""6个专业Agent + 自由审查Agent

每个Agent=独立的角色人设+专属规范库+图纸过滤+检查点集。
"""

import logging
from typing import Any, Dict, List

from .base_agent import BaseAgent, AgentConfig, AgentReport

# 【对抗性增强】各专业内容级关键词——用于图纸内容回退匹配
CONTENT_DISCIPLINE_KEYWORDS: Dict[str, List[str]] = {
    "building": ["建筑", "平面", "立面", "剖面", "门窗", "楼梯", "电梯", "阳台", "无障碍",
                 "防火门", "疏散", "踏步", "坡道", "栏杆", "女儿墙", "变形缝", "屋面"],
    "structure": ["梁", "板", "柱", "剪力墙", "配筋", "箍筋", "纵筋", "轴压比", "混凝土",
                  "钢筋", "锚固", "荷载", "基础", "桩", "承台", "地梁"],
    "hvac": ["通风", "空调", "供暖", "排烟", "送风", "新风", "风管", "风口", "风机",
             "冷媒", "散热器", "防烟", "加压送风", "排烟口", "防火阀"],
    "plumbing": ["给水", "排水", "消火栓", "喷淋", "雨水", "污水", "废水", "管道",
                 "管径", "坡度", "阀门", "水表", "地漏", "通气管", "化粪池"],
    "electrical": ["配电箱", "电缆", "桥架", "照明", "插座", "开关", "防雷", "接地",
                   "弱电", "应急照明", "疏散指示", "火灾报警", "烟感", "温感"],
    "fire": ["防火分区", "疏散", "防火门", "防火卷帘", "灭火器", "报警", "烟感",
             "温感", "消防", "灭火", "消火栓", "喷淋", "疏散宽度", "疏散距离"],
    "landscape": ["绿化", "种植", "乔木", "灌木", "草坪", "铺装", "园路", "水景",
                  "亭", "廊", "花池", "树池", "座凳", "景观照明", "绿地", "小品"],
    "foundation_pit": ["基坑", "支护", "降水", "锚杆", "土钉", "排桩", "地下连续墙",
                       "边坡", "监测点", "排水沟", "截水沟", "放坡"],
    "curtain_wall": ["幕墙", "玻璃", "石材", "铝板", "龙骨", "密封胶", "连接件",
                     "预埋件", "胶缝", "横梁", "立柱", "开启扇"],
    "decoration": ["装饰", "吊顶", "墙面", "地面", "踢脚", "轻钢龙骨", "石膏板",
                   "乳胶漆", "瓷砖", "木饰面", "软包", "地毯", "石材"],
}

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
    """
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
        logger.info(
            f"[{agent_name}] 内容级回退匹配到 {len(content_matched)} 张图纸: "
            + ", ".join(getattr(c, "readable_name", "") or getattr(c, "file_path", "")
                        for c in content_matched)
        )
        matched.extend(content_matched)

    return matched


class BuildingAgent(BaseAgent):
    """建筑专业审查Agent——一级注册建筑师，15年经验"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_building",
            name="建筑工程师Agent",
            discipline="building",
            role_title="一级注册建筑师",
            experience_years=15,
            standards=["GB50016", "GB50352", "GB50763"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是一级注册建筑师，拥有15年住宅和公共建筑设计经验。"
            "你精通GB50016《建筑设计防火规范》、GB50352《民用建筑设计统一标准》、"
            "GB50763《无障碍设计规范》。你的审查风格严谨、细致，特别关注："
            "疏散宽度、防火分区、无障碍设施、构造做法、标注完整性。"
            "你的结论必须直接可用于施工图审查意见书。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["building"],
            agent_name=self.config.name,
        )


class StructureAgent(BaseAgent):
    """结构专业审查Agent——一级注册结构师，15年经验"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_structure",
            name="结构工程师Agent",
            discipline="structure",
            role_title="一级注册结构工程师",
            experience_years=15,
            standards=["GB50010", "GB50011", "GB50007"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是一级注册结构工程师，拥有15年混凝土结构和钢结构设计经验。"
            "你精通GB50010《混凝土结构设计规范》、GB50011《建筑抗震设计规范》、"
            "GB50007《建筑地基基础设计规范》。你特别关注："
            "构件截面尺寸、配筋率、抗震构造措施、基础设计。"
            "你的结论必须精确、可量化。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["structure", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["structure"],
            agent_name=self.config.name,
        )


class HvacAgent(BaseAgent):
    """暖通专业审查Agent——注册暖通工程师，15年经验"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_hvac",
            name="暖通工程师Agent",
            discipline="hvac",
            role_title="注册暖通工程师",
            experience_years=15,
            standards=["GB50736", "GB51251"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册暖通工程师，拥有15年暖通空调和防排烟设计经验。"
            "你精通GB50736《民用建筑供暖通风与空气调节设计规范》、"
            "GB51251《建筑防烟排烟系统技术标准》。你特别关注："
            "风管截面尺寸、防排烟系统完整性、设备选型合理性、保温措施。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["hvac", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["hvac"],
            agent_name=self.config.name,
        )


class PlumbingAgent(BaseAgent):
    """给排水专业审查Agent——注册给排水工程师，15年经验"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_plumbing",
            name="给排水工程师Agent",
            discipline="plumbing",
            role_title="注册给排水工程师",
            experience_years=15,
            standards=["GB50015", "GB50974"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册给排水工程师，拥有15年建筑给排水和消防给水设计经验。"
            "你精通GB50015《建筑给水排水设计标准》、"
            "GB50974《消防给水及消火栓系统技术规范》。你特别关注："
            "管道管径、消火栓布置间距、喷淋覆盖范围、排水坡度。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["plumbing", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["plumbing"],
            agent_name=self.config.name,
        )


class ElectricalAgent(BaseAgent):
    """电气专业审查Agent——注册电气工程师，15年经验"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_electrical",
            name="电气工程师Agent",
            discipline="electrical",
            role_title="注册电气工程师",
            experience_years=15,
            standards=["GB50054", "GB50057"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册电气工程师，拥有15年建筑电气设计经验。"
            "你精通GB50054《低压配电设计规范》、"
            "GB50057《建筑物防雷设计规范》。你特别关注："
            "配电箱容量、桥架填充率、防雷接地措施、应急照明设置。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["electrical", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["electrical"],
            agent_name=self.config.name,
        )


class FireAgent(BaseAgent):
    """消防专业审查Agent——注册消防工程师，12年经验，跨专业"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_fire",
            name="消防工程师Agent",
            discipline="fire",
            role_title="注册消防工程师",
            experience_years=12,
            standards=["GB50016", "GB50116", "GB50974"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册消防工程师，拥有12年建筑消防设计和审查经验。"
            "你精通GB50016《建筑设计防火规范》、GB50116《火灾自动报警系统设计规范》、"
            "GB50974《消防给水及消火栓系统技术规范》。"
            "你跨专业审查所有消防相关标注，特别关注："
            "防火分区完整性、疏散距离和宽度、消火栓和喷淋覆盖、报警系统设置、防火门和防火卷帘。"
            "当消防结论与其他专业矛盾时，安全优先——以消防结论为准。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        fire_keywords = ["消防", "防火", "灭火", "报警", "消火栓", "喷淋", "疏散", "防火门", "防火卷帘"]
        results = []
        for d in drawing_infos:
            disc = getattr(d, "discipline", "")
            text = getattr(d, "text_content", "") or ""
            if disc == "fire":
                results.append(d)
            elif disc != "fire" and any(kw in text for kw in fire_keywords):
                results.append(d)
        return results


class FreeReviewAgent(BaseAgent):
    """自由审查Agent——资深审图专家，20年经验，无检查点限制"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_free_review",
            name="自由审查Agent",
            discipline="cross",
            role_title="教授级高级工程师",
            experience_years=20,
            standards=["GB50016", "GB50352", "GB50010", "GB50015", "GB50054", "GB50736"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是教授级高级工程师，拥有20年综合审图经验。"
            "你不受检查点限制，请自由浏览所有图纸标注。"
            "找出任何不符合规范、不合理或值得关注的问题。"
            "你的视角是跨专业的——看到建筑和结构标注矛盾、机电和建筑冲突等问题。"
            "对于每个发现问题，必须引用具体的规范条文。"
        )

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

        except Exception:
            self._report.errors += 1

        self._report.total_time_ms = (time.time() - start) * 1000
        return self._report


class CurtainWallAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_curtain_wall",
            name="幕墙工程师Agent",
            discipline="curtain_wall",
            role_title="注册幕墙工程师",
            experience_years=12,
            standards=["GB/T21086", "GB50016", "JGJ102"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册幕墙工程师，拥有12年建筑幕墙设计经验。"
            "你精通GB/T21086《建筑幕墙》、GB50016《建筑设计防火规范》、JGJ102《玻璃幕墙工程技术规范》。"
            "你特别关注：幕墙结构连接、防火封堵、玻璃厚度、密封胶选型、避雷连接。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["curtain_wall", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["curtain_wall"],
            agent_name=self.config.name,
        )


class DecorationAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_decoration",
            name="装饰工程师Agent",
            discipline="decoration",
            role_title="注册室内设计师",
            experience_years=12,
            standards=["GB50222", "GB50352", "GB50016"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册室内设计师，拥有12年建筑装饰设计经验。"
            "你精通GB50222《建筑内部装修设计防火规范》、GB50352《民用建筑设计统一标准》。"
            "你特别关注：装修材料燃烧性能等级、隔墙防火极限、吊顶标高标注、地面防滑等级。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["decoration", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["decoration"],
            agent_name=self.config.name,
        )


class LandscapeAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_landscape",
            name="景观工程师Agent",
            discipline="landscape",
            role_title="注册景观设计师",
            experience_years=10,
            standards=["GB50420", "GB50016", "CJJ37"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册景观设计师，拥有10年园林景观设计经验。"
            "你精通GB50420《城市绿化工程施工及验收规范》、CJJ37《城市道路设计规范》。"
            "你特别关注：绿化用地面积、道路转弯半径、室外台阶坡度、景观照明配电。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["landscape", "building", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["landscape"],
            agent_name=self.config.name,
        )


class FoundationPitAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="agent_foundation_pit",
            name="基坑工程师Agent",
            discipline="foundation_pit",
            role_title="注册岩土工程师",
            experience_years=15,
            standards=["GB50086", "GB50007", "JGJ120"],
        ))

    def build_system_prompt(self) -> str:
        return (
            "你是注册岩土工程师，拥有15年基坑支护设计经验。"
            "你精通GB50086《岩土锚杆与喷射混凝土支护工程技术规范》、"
            "GB50007《建筑地基基础设计规范》、JGJ120《建筑基坑支护技术规程》。"
            "你特别关注：基坑支护形式、降水井间距、锚杆长度、监测点布置、排水沟截面。"
        )

    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        return _filter_with_content_fallback(
            drawing_infos,
            primary_disciplines=["foundation_pit", "structure", "unknown"],
            content_keywords=CONTENT_DISCIPLINE_KEYWORDS["foundation_pit"],
            agent_name=self.config.name,
        )
