# -*- coding: utf-8 -*-
"""Pytest 公共配置与 fixtures"""

import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def sample_issue():
    """标准格式审查问题样本。"""
    return {
        "id": "JZ-001",
        "severity": "B",
        "standard": "GB50352-2019 民用建筑设计统一标准",
        "finding": "测试问题描述",
        "fix": "测试整改建议",
        "discipline": "建筑",
    }


@pytest.fixture
def sample_issues():
    """多专业审查问题列表。"""
    return [
        {"id": "JZ-001", "severity": "A", "standard": "GB50016-2014", "finding": "A级问题", "fix": "紧急修复", "discipline": "建筑"},
        {"id": "JZ-002", "severity": "B", "standard": "GB50352-2019", "finding": "B级问题", "fix": "尽快修复", "discipline": "建筑"},
        {"id": "STRUCT-001", "severity": "B", "standard": "GB50010-2010", "finding": "结构问题", "fix": "修复", "discipline": "结构"},
        {"id": "PLUMB-001", "severity": "C", "standard": "GB50015-2019", "finding": "给排水问题", "fix": "建议修复", "discipline": "给排水"},
        {"id": "ELEC-001", "severity": "D", "standard": "GB50034-2013", "finding": "提示", "fix": "可选", "discipline": "电气"},
    ]


@pytest.fixture
def sample_llm_response_json():
    """模拟LLM JSON响应。"""
    return json.dumps({
        "discipline": "建筑",
        "issues": [
            {
                "id": "JZ-001",
                "severity": "B",
                "standard": "GB50352-2019 民用建筑设计统一标准",
                "finding": "防火分区面积标注不全",
                "fix": "补充各层防火分区面积标注",
            },
            {
                "id": "JZ-002",
                "severity": "A",
                "standard": "GB50016-2014 5.1.1",
                "finding": "建筑分类未明确标注",
                "fix": "在总说明中明确建筑分类",
            },
        ],
    }, ensure_ascii=False)


@pytest.fixture
def sample_llm_response_ok():
    """模拟LLM无问题响应。"""
    return json.dumps({
        "discipline": "景观",
        "issues": [],
    }, ensure_ascii=False)


@pytest.fixture
def sample_llm_response_bad_json():
    """模拟LLM非JSON响应（降级解析测试用）。"""
    return """[JZ-001] 防火分区面积标注不全
B级：GB50352-2019第5.1.1条
整改建议：补充防火分区面积标注图

[JZ-002] 疏散距离超标
A级：GB50016-2014第5.5.17条
需重新核算疏散距离"""


@pytest.fixture
def sample_text_content():
    """模拟图纸文本提取内容。"""
    return """
建筑总说明
项目名称：施工图审查项目
建筑分类：公建甲类
耐火等级：一级
抗震设防烈度：6度（0.05g）
防火分区：首层1500m² 二层1200m²
外窗：6Low-E+12氩气+6透明中空玻璃(29mm)
屋面防水：涂料+卷材复合体系
"""


@pytest.fixture
def mock_llm_factory():
    """Mock LLMFactory for testing. Returns a tuple of (mock_response_fn, mock)."""
    mock = MagicMock()
    # 配置 call_with_failover 返回值
    mock.call_with_failover.return_value = (
        json.dumps({
            "discipline": "建筑",
            "issues": [{
                "id": "JZ-001",
                "severity": "B",
                "standard": "GB50352-2019",
                "finding": "测试发现",
                "fix": "测试修复",
            }],
        }, ensure_ascii=False),
        "mock_provider",
    )
    return mock
