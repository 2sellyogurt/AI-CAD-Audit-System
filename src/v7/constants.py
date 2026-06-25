# -*- coding: utf-8 -*-
"""全局共享常量定义

供 admin 页面、审查引擎、前端等统一引用，避免多处硬编码导致的数据不一致。
"""

# ════════════════════════════════════════════════════════
# 专业分类
# ════════════════════════════════════════════════════════

DISCIPLINE_LABELS = {
    "building": "建筑",
    "structure": "结构",
    "hvac": "暖通",
    "plumbing": "给排水",
    "electrical": "电气",
    "fire": "消防",
    "curtain_wall": "幕墙",
    "decoration": "装饰",
    "landscape": "景观",
    "foundation_pit": "基坑",
    "cross": "综合审查",
    "unknown": "未分类",
}

DISCIPLINE_LIST = list(DISCIPLINE_LABELS.keys())


# ════════════════════════════════════════════════════════
# 严重度定义
# ════════════════════════════════════════════════════════

SEVERITY_META = {
    "A": {"label": "A-强制", "color": "#e94560", "order": 0},
    "B": {"label": "B-重要", "color": "#e67e22", "order": 1},
    "C": {"label": "C-一般", "color": "#3498db", "order": 2},
    "D": {"label": "D-提示", "color": "#95a5a6", "order": 3},
}


# ════════════════════════════════════════════════════════
# 审查路径
# ════════════════════════════════════════════════════════

ROUTE_LABELS = {
    "text": "文本",
    "visual": "视觉",
    "dual": "双路径",
}


# ════════════════════════════════════════════════════════
# 图纸状态
# ════════════════════════════════════════════════════════

DRAWING_STATUS_LABELS = {
    "pending": "待审查",
    "reviewing": "审查中",
    "completed": "已完成",
    "failed": "失败",
}


# ════════════════════════════════════════════════════════
# LLM 提供商
# ════════════════════════════════════════════════════════

LLM_PROVIDERS = [
    {
        "provider": "zhipu",
        "name": "智谱AI (Zhipu)",
        "color": "#1677ff",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_text_model": "glm-4-flash",
        "default_vision_model": "glm-4v",
        "region": "国产",
        "recommended": True,
        "text_models": [
            {"id": "glm-4-flash", "name": "GLM-4-Flash", "price": "免费", "speed": "极快", "desc": "轻量高速，适合大批量审查"},
            {"id": "glm-4-plus", "name": "GLM-4-Plus", "price": "¥0.05/千token", "speed": "快", "desc": "综合能力最强，推荐首选"},
            {"id": "glm-4-air", "name": "GLM-4-Air", "price": "¥0.001/千token", "speed": "快", "desc": "性价比之选"},
        ],
        "vision_models": [
            {"id": "glm-4v", "name": "GLM-4V", "price": "¥0.05/千token", "speed": "快", "desc": "支持图纸识别"},
            {"id": "glm-4v-plus", "name": "GLM-4V-Plus", "price": "¥0.1/千token", "speed": "中等", "desc": "高精度图纸分析"},
        ],
    },
    {
        "provider": "deepseek",
        "name": "DeepSeek",
        "color": "#536dfe",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_text_model": "deepseek-chat",
        "default_vision_model": "",
        "region": "国产",
        "recommended": True,
        "text_models": [
            {"id": "deepseek-chat", "name": "DeepSeek-V3", "price": "¥0.002/千token", "speed": "快", "desc": "推理能力强，代码审查优秀"},
            {"id": "deepseek-reasoner", "name": "DeepSeek-R1", "price": "¥0.004/千token", "speed": "中等", "desc": "深度推理，规范条文分析精准"},
        ],
        "vision_models": [],
        "vision_note": "DeepSeek暂不支持视觉模型，图纸识别需配合其他厂商",
    },
    {
        "provider": "qwen",
        "name": "通义千问 (Qwen)",
        "color": "#8b5cf6",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_text_model": "qwen-plus",
        "default_vision_model": "qwen-vl-plus",
        "region": "国产",
        "recommended": True,
        "text_models": [
            {"id": "qwen-plus", "name": "Qwen-Plus", "price": "¥0.004/千token", "speed": "快", "desc": "阿里出品，中文理解优秀"},
            {"id": "qwen-max", "name": "Qwen-Max", "price": "¥0.02/千token", "speed": "中等", "desc": "旗舰模型，综合能力最强"},
            {"id": "qwen-turbo", "name": "Qwen-Turbo", "price": "¥0.001/千token", "speed": "极快", "desc": "高性价比，快速筛查"},
        ],
        "vision_models": [
            {"id": "qwen-vl-plus", "name": "Qwen-VL-Plus", "price": "¥0.008/千token", "speed": "快", "desc": "视觉理解能力强"},
            {"id": "qwen-vl-max", "name": "Qwen-VL-Max", "price": "¥0.02/千token", "speed": "中等", "desc": "高精度视觉分析"},
        ],
    },
    {
        "provider": "doubao",
        "name": "豆包 (Doubao)",
        "color": "#ff6b35",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_text_model": "doubao-1.5-pro-32k",
        "default_vision_model": "doubao-1.5-vision-pro",
        "region": "国产",
        "recommended": False,
        "text_models": [
            {"id": "doubao-1.5-pro-32k", "name": "Doubao-1.5-Pro", "price": "¥0.003/千token", "speed": "快", "desc": "字节跳动出品，长上下文支持"},
            {"id": "doubao-1.5-lite-32k", "name": "Doubao-1.5-Lite", "price": "¥0.0006/千token", "speed": "极快", "desc": "超低成本"},
        ],
        "vision_models": [
            {"id": "doubao-1.5-vision-pro", "name": "Doubao-Vision-Pro", "price": "¥0.005/千token", "speed": "快", "desc": "支持图纸识别"},
        ],
    },
    {
        "provider": "openai",
        "name": "OpenAI",
        "color": "#10a37f",
        "default_base_url": "https://api.openai.com/v1",
        "default_text_model": "gpt-4o",
        "default_vision_model": "gpt-4o",
        "region": "海外",
        "recommended": False,
        "text_models": [
            {"id": "gpt-4o", "name": "GPT-4o", "price": "$5/百万token", "speed": "快", "desc": "OpenAI旗舰，综合能力最强"},
            {"id": "gpt-4o-mini", "name": "GPT-4o-Mini", "price": "$0.15/百万token", "speed": "极快", "desc": "低成本替代方案"},
        ],
        "vision_models": [
            {"id": "gpt-4o", "name": "GPT-4o", "price": "$5/百万token", "speed": "快", "desc": "原生视觉支持"},
        ],
    },
    {
        "provider": "ollama",
        "name": "Ollama (本地)",
        "color": "#000000",
        "default_base_url": "http://localhost:11434/v1",
        "default_text_model": "qwen2.5:7b",
        "default_vision_model": "llava:latest",
        "region": "本地",
        "recommended": False,
        "text_models": [
            {"id": "qwen2.5:7b", "name": "Qwen2.5-7B", "price": "免费", "speed": "取决于硬件", "desc": "本地运行，数据不出境"},
            {"id": "qwen2.5:14b", "name": "Qwen2.5-14B", "price": "免费", "speed": "取决于硬件", "desc": "更大参数，效果更好"},
            {"id": "deepseek-r1:14b", "name": "DeepSeek-R1-14B", "price": "免费", "speed": "取决于硬件", "desc": "本地推理模型"},
        ],
        "vision_models": [
            {"id": "llava:latest", "name": "LLaVA", "price": "免费", "speed": "取决于硬件", "desc": "本地视觉模型"},
        ],
        "local_note": "需先安装Ollama并下载模型: ollama pull qwen2.5:7b",
    },
]

LLM_PROVIDER_MAP = {p["provider"]: p for p in LLM_PROVIDERS}


# ════════════════════════════════════════════════════════
# 费用单价（每百万token）
# ════════════════════════════════════════════════════════

PRICE_PER_MTOK = {
    "zhipu": {"input": 0.5, "output": 0.5},
    "deepseek": {"input": 1.0, "output": 2.0},
    "qwen": {"input": 2.0, "output": 6.0},
    "doubao": {"input": 0.8, "output": 2.0},
    "openai": {"input": 5.0, "output": 15.0},
    "ollama": {"input": 0.0, "output": 0.0},
}


# ════════════════════════════════════════════════════════
# 审查问题状态
# ════════════════════════════════════════════════════════

ISSUE_STATUS_LABELS = {
    "open": "待处理",
    "resolved": "已解决",
    "dismissed": "已忽略",
    "modified": "已变更",
}

ISSUE_STATUS_COLORS = {
    "open": "#e94560",
    "resolved": "#27ae60",
    "dismissed": "#95a5a6",
    "modified": "#e67e22",
}


# ════════════════════════════════════════════════════════
# Agent 配置（从 discipline_agents.py 集中提取）
# ════════════════════════════════════════════════════════

AGENT_CONFIGS = {
    "agent_building": {
        "name": "建筑工程师Agent",
        "discipline": "building",
        "role_title": "一级注册建筑师",
        "experience_years": 15,
        "standards": ["GB50016", "GB50352", "GB50763"],
        "system_prompt": (
            "你是一级注册建筑师，拥有15年住宅和公共建筑设计经验。"
            "你精通GB50016《建筑设计防火规范》、GB50352《民用建筑设计统一标准》、"
            "GB50763《无障碍设计规范》。你的审查风格严谨、细致，特别关注："
            "疏散宽度、防火分区、无障碍设施、构造做法、标注完整性。"
            "你的结论必须直接可用于施工图审查意见书。"
        ),
        "content_keywords": [
            "建筑", "平面", "立面", "剖面", "门窗", "楼梯", "电梯", "阳台", "无障碍",
            "防火门", "疏散", "踏步", "坡道", "栏杆", "女儿墙", "变形缝", "屋面",
        ],
        "primary_disciplines": ["building", "unknown"],
    },
    "agent_structure": {
        "name": "结构工程师Agent",
        "discipline": "structure",
        "role_title": "一级注册结构工程师",
        "experience_years": 15,
        "standards": ["GB50010", "GB50011", "GB50007"],
        "system_prompt": (
            "你是一级注册结构工程师，拥有15年混凝土结构和钢结构设计经验。"
            "你精通GB50010《混凝土结构设计规范》、GB50011《建筑抗震设计规范》、"
            "GB50007《建筑地基基础设计规范》。你特别关注："
            "构件截面尺寸、配筋率、抗震构造措施、基础设计。"
            "你的结论必须精确、可量化。"
        ),
        "content_keywords": [
            "梁", "板", "柱", "剪力墙", "配筋", "箍筋", "纵筋", "轴压比", "混凝土",
            "钢筋", "锚固", "荷载", "基础", "桩", "承台", "地梁",
        ],
        "primary_disciplines": ["structure", "building", "unknown"],
    },
    "agent_hvac": {
        "name": "暖通工程师Agent",
        "discipline": "hvac",
        "role_title": "注册暖通工程师",
        "experience_years": 15,
        "standards": ["GB50736", "GB51251"],
        "system_prompt": (
            "你是注册暖通工程师，拥有15年暖通空调和防排烟设计经验。"
            "你精通GB50736《民用建筑供暖通风与空气调节设计规范》、"
            "GB51251《建筑防烟排烟系统技术标准》。你特别关注："
            "风管截面尺寸、防排烟系统完整性、设备选型合理性、保温措施。"
        ),
        "content_keywords": [
            "通风", "空调", "供暖", "排烟", "送风", "新风", "风管", "风口", "风机",
            "冷媒", "散热器", "防烟", "加压送风", "排烟口", "防火阀",
        ],
        "primary_disciplines": ["hvac", "building", "unknown"],
    },
    "agent_plumbing": {
        "name": "给排水工程师Agent",
        "discipline": "plumbing",
        "role_title": "注册给排水工程师",
        "experience_years": 15,
        "standards": ["GB50015", "GB50974"],
        "system_prompt": (
            "你是注册给排水工程师，拥有15年建筑给排水和消防给水设计经验。"
            "你精通GB50015《建筑给水排水设计标准》、"
            "GB50974《消防给水及消火栓系统技术规范》。你特别关注："
            "管道管径、消火栓布置间距、喷淋覆盖范围、排水坡度。"
        ),
        "content_keywords": [
            "给水", "排水", "消火栓", "喷淋", "雨水", "污水", "废水", "管道",
            "管径", "坡度", "阀门", "水表", "地漏", "通气管", "化粪池",
        ],
        "primary_disciplines": ["plumbing", "building", "unknown"],
    },
    "agent_electrical": {
        "name": "电气工程师Agent",
        "discipline": "electrical",
        "role_title": "注册电气工程师",
        "experience_years": 15,
        "standards": ["GB50054", "GB50057"],
        "system_prompt": (
            "你是注册电气工程师，拥有15年建筑电气设计经验。"
            "你精通GB50054《低压配电设计规范》、"
            "GB50057《建筑物防雷设计规范》。你特别关注："
            "配电箱容量、桥架填充率、防雷接地措施、应急照明设置。"
        ),
        "content_keywords": [
            "配电箱", "电缆", "桥架", "照明", "插座", "开关", "防雷", "接地",
            "弱电", "应急照明", "疏散指示", "火灾报警", "烟感", "温感",
        ],
        "primary_disciplines": ["electrical", "building", "unknown"],
    },
    "agent_fire": {
        "name": "消防工程师Agent",
        "discipline": "fire",
        "role_title": "注册消防工程师",
        "experience_years": 12,
        "standards": ["GB50016", "GB50116", "GB50974"],
        "system_prompt": (
            "你是注册消防工程师，拥有12年建筑消防设计和审查经验。"
            "你精通GB50016《建筑设计防火规范》、GB50116《火灾自动报警系统设计规范》、"
            "GB50974《消防给水及消火栓系统技术规范》。"
            "你跨专业审查所有消防相关标注，特别关注："
            "防火分区完整性、疏散距离和宽度、消火栓和喷淋覆盖、报警系统设置、防火门和防火卷帘。"
            "当消防结论与其他专业矛盾时，安全优先——以消防结论为准。"
        ),
        "content_keywords": [
            "消防", "防火", "灭火", "报警", "消火栓", "喷淋", "疏散", "防火门", "防火卷帘",
        ],
        "primary_disciplines": ["fire"],
        "fire_keywords": ["消防", "防火", "灭火", "报警", "消火栓", "喷淋", "疏散", "防火门", "防火卷帘"],
    },
    "agent_curtain_wall": {
        "name": "幕墙工程师Agent",
        "discipline": "curtain_wall",
        "role_title": "注册幕墙工程师",
        "experience_years": 12,
        "standards": ["GB/T21086", "GB50016", "JGJ102"],
        "system_prompt": (
            "你是注册幕墙工程师，拥有12年建筑幕墙设计经验。"
            "你精通GB/T21086《建筑幕墙》、GB50016《建筑设计防火规范》、JGJ102《玻璃幕墙工程技术规范》。"
            "你特别关注：幕墙结构连接、防火封堵、玻璃厚度、密封胶选型、避雷连接。"
        ),
        "content_keywords": [
            "幕墙", "玻璃", "石材", "铝板", "龙骨", "密封胶", "连接件",
            "预埋件", "胶缝", "横梁", "立柱", "开启扇",
        ],
        "primary_disciplines": ["curtain_wall", "building", "unknown"],
    },
    "agent_decoration": {
        "name": "装饰工程师Agent",
        "discipline": "decoration",
        "role_title": "注册室内设计师",
        "experience_years": 12,
        "standards": ["GB50222", "GB50352", "GB50016"],
        "system_prompt": (
            "你是注册室内设计师，拥有12年建筑装饰设计经验。"
            "你精通GB50222《建筑内部装修设计防火规范》、GB50352《民用建筑设计统一标准》。"
            "你特别关注：装修材料燃烧性能等级、隔墙防火极限、吊顶标高标注、地面防滑等级。"
        ),
        "content_keywords": [
            "装饰", "吊顶", "墙面", "地面", "踢脚", "轻钢龙骨", "石膏板",
            "乳胶漆", "瓷砖", "木饰面", "软包", "地毯", "石材",
        ],
        "primary_disciplines": ["decoration", "building", "unknown"],
    },
    "agent_landscape": {
        "name": "景观工程师Agent",
        "discipline": "landscape",
        "role_title": "注册景观设计师",
        "experience_years": 10,
        "standards": ["GB50420", "GB50016", "CJJ37"],
        "system_prompt": (
            "你是注册景观设计师，拥有10年园林景观设计经验。"
            "你精通GB50420《城市绿化工程施工及验收规范》、CJJ37《城市道路设计规范》。"
            "你特别关注：绿化用地面积、道路转弯半径、室外台阶坡度、景观照明配电。"
        ),
        "content_keywords": [
            "绿化", "种植", "乔木", "灌木", "草坪", "铺装", "园路", "水景",
            "亭", "廊", "花池", "树池", "座凳", "景观照明", "绿地", "小品",
        ],
        "primary_disciplines": ["landscape", "building", "unknown"],
    },
    "agent_foundation_pit": {
        "name": "基坑工程师Agent",
        "discipline": "foundation_pit",
        "role_title": "注册岩土工程师",
        "experience_years": 15,
        "standards": ["GB50086", "GB50007", "JGJ120"],
        "system_prompt": (
            "你是注册岩土工程师，拥有15年基坑支护设计经验。"
            "你精通GB50086《岩土锚杆与喷射混凝土支护工程技术规范》、"
            "GB50007《建筑地基基础设计规范》、JGJ120《建筑基坑支护技术规程》。"
            "你特别关注：基坑支护形式、降水井间距、锚杆长度、监测点布置、排水沟截面。"
        ),
        "content_keywords": [
            "基坑", "支护", "降水", "锚杆", "土钉", "排桩", "地下连续墙",
            "边坡", "监测点", "排水沟", "截水沟", "放坡",
        ],
        "primary_disciplines": ["foundation_pit", "structure", "unknown"],
    },
    "agent_free_review": {
        "name": "自由审查Agent",
        "discipline": "cross",
        "role_title": "教授级高级工程师",
        "experience_years": 20,
        "standards": ["GB50016", "GB50352", "GB50010", "GB50015", "GB50054", "GB50736"],
        "system_prompt": (
            "你是教授级高级工程师，拥有20年综合审图经验。"
            "你不受检查点限制，请自由浏览所有图纸标注。"
            "找出任何不符合规范、不合理或值得关注的问题。"
            "你的视角是跨专业的——看到建筑和结构标注矛盾、机电和建筑冲突等问题。"
            "对于每个发现问题，必须引用具体的规范条文。"
        ),
        "content_keywords": [],
        "primary_disciplines": [],
    },
}


# ════════════════════════════════════════════════════════
# 图纸内容分类关键词（从 drawing_extractor.py 集中提取）
# ════════════════════════════════════════════════════════

CONTENT_DISCIPLINE_KEYWORDS = {
    k: v["content_keywords"]
    for k, v in AGENT_CONFIGS.items()
    if v["content_keywords"]
}

# 兼容旧代码的 key 映射（agent_id -> discipline）
DISCIPLINE_KEYWORDS = {
    v["discipline"]: v["content_keywords"]
    for k, v in AGENT_CONFIGS.items()
    if v["content_keywords"]
}
