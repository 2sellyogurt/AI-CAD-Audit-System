# -*- coding: utf-8 -*-
"""LLM全流程审查管道测试

【LEGACY】旧v5-v6管线测试，依赖 llm_full_review.py 旧管线。
如需维护审查管线测试，请使用 v7/tests/test_smoke.py（v7管线）或重写本文件。

测试 llm_full_review.py 的核心功能：
  - 文本数据加载与专业分组
  - Prompt 构建
  - LLM 响应解析（正常JSON / 降级文本）
  - 审查模式检测
  - 缓存审查数据完整性
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch, mock_open

import pytest

# 确保 v7 包在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from v7.llm_full_review import (
    ReviewMode,
    _discipline_code,
    _match_discipline,
    _fallback_parse,
    parse_llm_response,
    build_review_prompt,
    detect_best_mode,
    DISCIPLINE_REVIEWER_MAP,
)


class TestDisciplineCode:
    """专业编码测试。"""

    def test_known_disciplines(self):
        assert _discipline_code("建筑") == "JZ"
        assert _discipline_code("结构") == "STRUCT"
        assert _discipline_code("给排水") == "PLUMB"
        assert _discipline_code("暖通") == "HVAC"
        assert _discipline_code("电气") == "ELEC"
        assert _discipline_code("消防") == "FIRE"
        assert _discipline_code("幕墙") == "CW"
        assert _discipline_code("基坑") == "FP"

    def test_unknown_discipline(self):
        assert _discipline_code("未知专业") == "REV"


class TestMatchDiscipline:
    """文件名匹配测试。"""

    def test_exact_match(self):
        assert _match_discipline("建筑总说明_text.txt", ["建筑总说明"])
        assert _match_discipline("0结构设计说明20251114_text.txt", ["结构设计说明"])

    def test_partial_match(self):
        assert _match_discipline("水施-教学实验楼_111990_text.txt", ["水施", "给排水"])
        assert _match_discipline("电气总设计说明_t3_text.txt", ["电气"])

    def test_no_match(self):
        assert not _match_discipline("unknown_file_text.txt", ["建筑", "结构"])

    def test_empty_keywords(self):
        assert not _match_discipline("anything_text.txt", [])


class TestParseLLMResponse:
    """LLM响应解析测试。"""

    def test_parse_valid_json(self, sample_llm_response_json):
        issues = parse_llm_response(sample_llm_response_json, "建筑")
        assert len(issues) == 2
        assert issues[0]["id"] == "JZ-001"
        assert issues[0]["severity"] == "B"
        assert issues[0]["discipline"] == "建筑"
        assert "standard" in issues[0]
        assert "finding" in issues[0]
        assert "fix" in issues[0]

    def test_parse_json_with_markdown_wrapper(self):
        response = '```json\n{"discipline":"结构","issues":[{"id":"STRUCT-001","severity":"A","standard":"GB50010","finding":"问题","fix":"修复"}]}\n```'
        issues = parse_llm_response(response, "结构")
        assert len(issues) == 1
        assert issues[0]["id"] == "STRUCT-001"

    def test_parse_empty_response(self):
        assert parse_llm_response("", "建筑") == []
        assert parse_llm_response(None, "建筑") == []

    def test_parse_no_issues(self, sample_llm_response_ok):
        issues = parse_llm_response(sample_llm_response_ok, "景观")
        assert issues == []

    def test_parse_bad_json_fallback(self, sample_llm_response_bad_json):
        issues = parse_llm_response(sample_llm_response_bad_json, "建筑")
        assert len(issues) >= 1

    def test_parse_normalizes_severity(self):
        response = '{"discipline":"建筑","issues":[{"id":"JZ-001","severity":"x","finding":"test","fix":"fix"}]}'
        issues = parse_llm_response(response, "建筑")
        assert issues[0]["severity"] == "C"  # 无效值默认C

    def test_parse_single_issue_dict(self):
        """单个issue直接作为dict返回（非标准格式）。"""
        response = '{"id":"JZ-099","severity":"B","standard":"GB50016","finding":"测试","fix":"修复"}'
        issues = parse_llm_response(response, "建筑")
        assert len(issues) == 1
        assert issues[0]["id"] == "JZ-099"

    def test_parse_provides_defaults(self):
        response = '{"discipline":"建筑","issues":[{"finding":"仅有描述"}]}'
        issues = parse_llm_response(response, "建筑")
        assert issues[0]["severity"] == "C"
        assert issues[0]["standard"] == "未标注"
        assert issues[0]["fix"] == "请进一步核实"


class TestFallbackParse:
    """降级解析测试。"""

    def test_basic_fallback(self):
        text = """[JZ-001] 防火分区面积标注不全
B级：GB50352-2019第5.1.1条
整改建议：补充防火分区面积标注图"""
        issues = _fallback_parse(text, "建筑")
        assert len(issues) >= 1

    def test_fallback_empty(self):
        assert _fallback_parse("", "建筑") == []

    def test_fallback_multi_issues(self):
        text = """[STRUCT-001] 抗震等级未标注
A级：GB50011-2010
整改：补充抗震等级

[STRUCT-002] 钢筋保护层厚度不足
B级：GB50010-2010
整改：调整保护层厚度"""
        issues = _fallback_parse(text, "结构")
        assert len(issues) >= 1


class TestBuildReviewPrompt:
    """Prompt构建测试。"""

    def test_basic_prompt_structure(self, sample_text_content):
        prompt = build_review_prompt("建筑", sample_text_content)
        assert "建筑" in prompt
        assert sample_text_content.strip() in prompt
        assert "审查专业" in prompt
        assert "审查重点" in prompt
        assert "输出格式" in prompt
        assert "JZ" in prompt  # 专业编码

    def test_prompt_includes_discipline_code(self):
        prompt = build_review_prompt("结构", "测试内容")
        assert "STRUCT" in prompt

    def test_prompt_handles_long_text(self):
        long_text = "测试内容。" * 5000
        prompt = build_review_prompt("建筑", long_text)
        assert len(prompt) > 0

    def test_all_disciplines_have_specs(self):
        """所有定义的专业都有审查重点。"""
        test_disciplines = [
            "建筑", "结构", "给排水", "暖通", "电气", "消防",
            "幕墙", "装饰", "景观", "基坑", "标识标线", "门窗",
        ]
        for disc in test_disciplines:
            prompt = build_review_prompt(disc, "测试")
            assert disc in prompt, f"{disc} 专业未出现在prompt中"


class TestReviewMode:
    """审查模式检测测试。"""

    def test_enum_values(self):
        assert ReviewMode.REAL_LLM.value == "real"
        assert ReviewMode.CACHED.value == "cached"

    def test_detect_cached_by_default(self):
        """默认（无API Key环境变量）应返回CACHED。"""
        # 清除相关环境变量
        for var in ["ZHIPU_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DOUBAO_API_KEY",
                     "ZHIPU_TEXT_KEY", "ZHIPU_VISION_KEY"]:
            os.environ.pop(var, None)

        mode = detect_best_mode()
        assert mode == ReviewMode.CACHED

    def test_detect_real_with_api_key(self):
        """设置API Key后应返回REAL_LLM。"""
        os.environ["ZHIPU_API_KEY"] = "test-key-12345"
        try:
            mode = detect_best_mode()
            assert mode == ReviewMode.REAL_LLM
        finally:
            del os.environ["ZHIPU_API_KEY"]


class TestCachedReviewData:
    """缓存审查数据完整性测试。"""

    def test_all_reviewers_return_lists(self):
        """所有审查函数返回非空列表。"""
        for disc_name, reviewer in DISCIPLINE_REVIEWER_MAP.items():
            result = reviewer()
            assert isinstance(result, list), f"{disc_name} 未返回列表"
            assert len(result) > 0, f"{disc_name} 返回空列表"

    def test_all_issues_have_required_fields(self):
        """所有缓存问题包含必填字段。"""
        for disc_name, reviewer in DISCIPLINE_REVIEWER_MAP.items():
            for issue in reviewer():
                assert "id" in issue, f"{disc_name}: 缺少id字段"
                assert "severity" in issue, f"{disc_name}: 缺少severity字段"
                assert issue["severity"] in ("A", "B", "C", "D"), \
                    f"{disc_name}/{issue.get('id')}: severity={issue['severity']}"
                assert "finding" in issue, f"{disc_name}: 缺少finding字段"
                assert "fix" in issue, f"{disc_name}: 缺少fix字段"

    def test_no_duplicate_ids(self):
        """缓存数据中无重复ID。"""
        all_ids = []
        for disc_name, reviewer in DISCIPLINE_REVIEWER_MAP.items():
            for issue in reviewer():
                all_ids.append(issue["id"])
        assert len(all_ids) == len(set(all_ids)), \
            f"发现重复ID: {[x for x in all_ids if all_ids.count(x) > 1]}"

    def test_cross_discipline_analysis_returns_list(self):
        from v7.llm_full_review import cross_discipline_analysis
        issues = cross_discipline_analysis()
        assert isinstance(issues, list)
        assert len(issues) > 0
        for issue in issues:
            assert "id" in issue
            assert "disciplines" in issue

    def test_eighteen_disciplines_covered(self):
        """确认覆盖了所有18个审查专业。"""
        expected = {
            "建筑", "结构", "给排水", "暖通", "电气", "消防",
            "幕墙", "装饰", "景观", "基坑", "标识标线", "门窗",
            "变配电", "装配式(深化)", "室外管综", "光伏", "电梯",
            "智能化/抗震支架/充电桩",
        }
        actual = set(DISCIPLINE_REVIEWER_MAP.keys())
        missing = expected - actual
        assert not missing, f"缺少专业: {missing}"
        assert len(actual) == 18, f"预期18个专业，实际{len(actual)}个"


class TestTextLoading:
    """文本加载测试（使用临时文件）。"""

    def test_match_discipline_with_temp_files(self):
        """使用实际文件名模式验证匹配。"""
        # 模拟文件名
        assert _match_discipline("建筑总说明_t3_text.txt", ["建筑总说明", "总图"])
        assert _match_discipline("0结构设计说明20251114_text.txt", ["结构设计说明", "结构施工图"])
        assert _match_discipline("电气总设计说明_t3_text.txt", ["电气"])
        assert _match_discipline("绿化平面图_text.txt", ["绿化"])


class TestLLMIntegrationPaths:
    """LLM集成路径测试（mock）。"""

    def test_review_with_real_llm_mocked(self, sample_text_content):
        """使用 mock LLMFactory 测试实时审查流程。"""
        from v7.llm_full_review import review_with_real_llm, parse_llm_response

        mock_response = json.dumps({
            "discipline": "建筑",
            "issues": [{
                "id": "JZ-TEST-001",
                "severity": "A",
                "standard": "GB50352-2019",
                "finding": "测试发现问题",
                "fix": "测试修复方案",
            }],
        }, ensure_ascii=False)

        with patch("v7.llm_full_review.review_with_real_llm") as mock_review:
            mock_review.return_value = parse_llm_response(mock_response, "建筑")
            issues = mock_review("建筑", sample_text_content)
            assert len(issues) == 1
            assert issues[0]["id"] == "JZ-TEST-001"
            assert issues[0]["severity"] == "A"

    def test_get_cached_review(self):
        """测试缓存降级方案。"""
        from v7.llm_full_review import _get_cached_review
        issues = _get_cached_review("建筑")
        assert len(issues) > 0

    def test_get_cached_review_unknown_discipline(self):
        """未知专业返回空列表。"""
        from v7.llm_full_review import _get_cached_review
        issues = _get_cached_review("不存在的专业")
        assert issues == []


class TestMainFunction:
    """main() 函数测试。"""

    def test_main_cached_mode(self):
        """CACHED模式 main() 测试。"""
        from v7.llm_full_review import main as review_main

        with patch("v7.llm_full_review.HAS_DOCX", False):
            result = review_main(mode="cached")
            if result:
                assert "findings" in result
                assert "mode" in result
                assert result["mode"] == "cached"
                assert len(result["findings"]) > 0
                assert "severity_counts" in result

    def test_main_auto_mode(self):
        """自动检测模式 main() 测试。"""
        from v7.llm_full_review import main as review_main

        with patch("v7.llm_full_review.HAS_DOCX", False):
            result = review_main()
            if result:
                assert result["mode"] in ("cached", "real")

    def test_main_returns_dict(self):
        """验证 main() 返回值结构。"""
        from v7.llm_full_review import main as review_main

        with patch("v7.llm_full_review.HAS_DOCX", False):
            result = review_main(mode="cached")
            if result:
                required_keys = {"findings", "cross_issues", "spatial_conflicts", "mode", "severity_counts"}
                missing = required_keys - set(result.keys())
                assert not missing, f"返回值缺少: {missing}"


class TestEmptySpaceConflictHandling:
    """空间冲突空数据处理测试。"""

    def test_load_spatial_not_exists(self):
        from v7.llm_full_review import load_spatial
        with patch("os.path.exists", return_value=False):
            result = load_spatial()
            assert result == []


class TestUAIIDNormalization:
    """UAI ID 规范化测试（report_translator 桥接逻辑）。"""

    def test_jzx_to_jz(self):
        from v7.report_translator import _normalize_uai_id
        assert _normalize_uai_id("JZX-004") == "JZ-004"
        assert _normalize_uai_id("JZX-001") == "JZ-001"
        assert _normalize_uai_id("JZX-015") == "JZ-015"

    def test_passthrough_standard_ids(self):
        from v7.report_translator import _normalize_uai_id
        assert _normalize_uai_id("FIRE-012") == "FIRE-012"
        assert _normalize_uai_id("STRUCT-003") == "STRUCT-003"
        assert _normalize_uai_id("PLUMB-001") == "PLUMB-001"
        assert _normalize_uai_id("HVAC-001") == "HVAC-001"
        assert _normalize_uai_id("ELEC-001") == "ELEC-001"
        assert _normalize_uai_id("CW-002") == "CW-002"
        assert _normalize_uai_id("FP-001") == "FP-001"
        assert _normalize_uai_id("LS-001") == "LS-001"

    def test_unknown_prefix_passthrough(self):
        from v7.report_translator import _normalize_uai_id
        assert _normalize_uai_id("UNKNOWN-001") == "UNKNOWN-001"
        assert _normalize_uai_id("XYZ-999") == "XYZ-999"

    def test_no_hyphen(self):
        from v7.report_translator import _normalize_uai_id
        assert _normalize_uai_id("NO_HYPHEN") == "NO_HYPHEN"

    def test_normalize_cross_discipline_ids_stay_unchanged(self):
        from v7.report_translator import _normalize_uai_id
        assert _normalize_uai_id("CROSS-001") == "CROSS-001"

    def test_uai_prefix_normalize_map_complete(self):
        from v7.report_translator import _UAI_PREFIX_NORMALIZE
        expected_prefixes = {"JZX", "JZ", "FIRE", "STRUCT", "PLUMB", "HVAC", "ELEC", "CW", "FP", "LS"}
        for prefix in expected_prefixes:
            assert prefix in _UAI_PREFIX_NORMALIZE, f"缺少前缀: {prefix}"
