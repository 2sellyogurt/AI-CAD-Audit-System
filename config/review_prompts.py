# -*- coding: utf-8 -*-
"""
审查提示词配置

包含：
- 风险等级定义（RISK_LEVELS）
- 证据链要求（EVIDENCE_REQUIREMENTS）
- 执行规则（EXECUTION_RULES）
- 分批处理策略（BATCH_STRATEGY）
"""

RISK_LEVELS = {
    "严重": {
        "code": "CRITICAL",
        "color": "红色",
        "criteria": "强条违规、结构安全隐患、消防系统失效",
        "response": "必须立即整改，不得通过审查",
        "deduction_points": 30,
    },
    "重要": {
        "code": "MAJOR",
        "color": "橙色",
        "criteria": "非强条违规、净高不足、管线碰撞、跨专业不一致",
        "response": "应整改，影响使用功能或施工质量",
        "deduction_points": 15,
    },
    "一般": {
        "code": "MODERATE",
        "color": "黄色",
        "criteria": "标注不完整、间距偏小、优化建议",
        "response": "建议整改，不影响安全但影响品质",
        "deduction_points": 5,
    },
    "提示": {
        "code": "INFO",
        "color": "蓝色",
        "criteria": "信息提示、参考建议、低置信度待核实项",
        "response": "供参考，人工复核即可",
        "deduction_points": 0,
    },
}

EVIDENCE_REQUIREMENTS = {
    "required_fields": ["file", "evidence"],
    "optional_fields": ["line", "original_text", "raw_text"],
    "low_confidence_triggers": {
        "missing_file": True,
        "missing_evidence": True,
        "file_is_unknown": True,
    },
    "confidence_levels": {
        "L0": "无证据，纯推测",
        "L1": "基础证据，仅有文件名",
        "L2": "增强证据，有文件名+行号+规则ID",
        "L3": "完整证据，有文件名+行号+规则ID+原文引用",
    },
}

EXECUTION_RULES = {
    "skip_low_confidence_in_report": True,
    "log_low_confidence": True,
    "require_file_reference": True,
    "require_evidence_text": True,
    "max_issues_per_file": 50,
    "deduplicate_by_rule_id": True,
}

BATCH_STRATEGY = {
    "batch_size": 10,
    "overlap": 2,
    "max_retries": 3,
    "timeout_seconds": 120,
    "priority_order": ["严重", "重要", "一般", "提示"],
}

LLM_JUDGMENT_CONFIG = {
    "enabled": True,
    "mode": "primary",
    "descriptions": {
        "primary": "LLM作为主判官，规则引擎做预筛选，LLM做最终判决",
        "enhance": "规则引擎做主判，LLM对边界/待核实问题做增强判断",
        "off": "关闭LLM判决，纯规则引擎模式",
    },
    "confidence_threshold": "low",
    "max_tokens_per_call": 4000,
    "models": {
        "default": "glm-4-flash",
        "provider": "zhipu",
    },
    "check_targets": {
        "step2_compliance": {
            "enabled": True,
            "method": "llm_primary_review",
            "description": "Step2强制条文合规：LLM对91条规则做独立语义审查",
            "max_rules_per_batch": 10,
        },
        "step3_defect": {
            "enabled": True,
            "method": "llm_collision_analysis",
            "description": "Step3错漏排查：LLM对碰撞检测结果做语义风险分析",
            "max_collisions_per_batch": 20,
        },
        "step4_cross": {
            "enabled": True,
            "method": "llm_cross_discipline",
            "description": "Step4跨专业校验：LLM判断跨专业发现的真实性",
            "max_items_per_batch": 15,
        },
        "severity_assessment": {
            "enabled": True,
            "method": "llm_context_assessment",
            "description": "严重度评估：LLM综合建筑类型、区域、问题类别判断严重度",
            "use_cache": True,
        },
        "suggestion_generation": {
            "enabled": True,
            "method": "llm_suggestion",
            "description": "整改建议生成：LLM基于上下文生成可操作整改方案",
            "use_cache": True,
            "fallback_to_template": True,
        },
    },
    "cache": {
        "enabled": True,
        "ttl_seconds": 3600,
        "max_entries": 500,
    },
    "budget_control": {
        "max_llm_calls_per_run": 200,
        "priority_order": ["step2_compliance", "severity_assessment", "suggestion_generation", "step4_cross", "step3_defect"],
    },
}

PROBLEM_CATEGORIES = {
    "强制条文违反": {
        "description": "违反国家强制性标准条文",
        "severity": "严重",
        "is_mandatory": True,
    },
    "规范条款不符": {
        "description": "不符合设计规范要求",
        "severity": "重要",
        "is_mandatory": False,
    },
    "专项图纸不合规": {
        "description": "消防/人防/无障碍等专项图纸不符合要求",
        "severity": "重要",
        "is_mandatory": False,
    },
    "专业图纸缺项": {
        "description": "缺失必要的专业图纸",
        "severity": "重要",
        "is_mandatory": False,
    },
    "前后打架": {
        "description": "跨专业图纸之间存在矛盾",
        "severity": "重要",
        "is_mandatory": False,
    },
    "显性错误": {
        "description": "标注错误、尺寸矛盾等明显错误",
        "severity": "一般",
        "is_mandatory": False,
    },
    "落地类问题": {
        "description": "施工可行性、成本合理性问题",
        "severity": "一般",
        "is_mandatory": False,
    },
    "隐患类问题": {
        "description": "安全隐患、运维风险",
        "severity": "重要",
        "is_mandatory": False,
    },
}
