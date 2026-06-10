# -*- coding: utf-8 -*-
"""LLM文本适配器单元测试

测试 TextAdapter 和 LLMBaseAdapter 的核心功能。
使用 mock 避免真实API调用。
"""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# 确保 v7 包在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLLMConfig:
    """LLMConfig 数据类测试。"""

    def test_default_values(self):
        from v7.llm.base_adapter import LLMConfig
        cfg = LLMConfig()
        assert cfg.timeout == 30
        assert cfg.max_retries == 2
        assert cfg.temperature == 0.1
        assert cfg.max_tokens == 4096
        assert cfg.provider == ""
        assert cfg.model == ""

    def test_custom_values(self):
        from v7.llm.base_adapter import LLMConfig
        cfg = LLMConfig(
            provider="zhipu",
            model="glm-4.5-air",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key="test-key",
            timeout=60,
            max_retries=3,
            temperature=0.3,
            max_tokens=8192,
        )
        assert cfg.provider == "zhipu"
        assert cfg.model == "glm-4.5-air"
        assert cfg.timeout == 60
        assert cfg.max_retries == 3
        assert cfg.temperature == 0.3
        assert cfg.max_tokens == 8192


class TestCallStats:
    """CallStats 数据类测试。"""

    def test_default_values(self):
        from v7.llm.base_adapter import CallStats
        stats = CallStats()
        assert stats.total_calls == 0
        assert stats.success_calls == 0
        assert stats.failed_calls == 0
        assert stats.total_tokens == 0
        assert stats.total_cost == 0.0


class TestLLMBaseAdapter:
    """LLMBaseAdapter 基类测试。"""

    def test_extract_json_plain(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        result = LLMBaseAdapter._extract_json('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_extract_json_with_markdown(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        text = '```json\n{"key": "value"}\n```'
        result = LLMBaseAdapter._extract_json(text)
        assert '"key": "value"' in result

    def test_extract_json_with_text_wrapping(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        text = '一些说明文字\n{"result": "ok"}\n更多说明'
        result = LLMBaseAdapter._extract_json(text)
        assert '"result": "ok"' in result

    def test_extract_json_array(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        text = '[{"id": 1}, {"id": 2}]'
        result = LLMBaseAdapter._extract_json(text)
        assert result == text

    def test_extract_json_empty(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        assert LLMBaseAdapter._extract_json("") == ""
        assert LLMBaseAdapter._extract_json(None) == ""

    def test_extract_json_no_braces(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        text = "纯文本，不含JSON结构"
        result = LLMBaseAdapter._extract_json(text)
        assert result == text

    def test_extract_json_nested(self):
        from v7.llm.base_adapter import LLMBaseAdapter
        text = '{"outer": {"inner": {"deep": "value"}}}'
        result = LLMBaseAdapter._extract_json(text)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"]["deep"] == "value"


class TestTextAdapter:
    """TextAdapter 测试（mock OpenAI client）。"""

    def test_client_lazy_init(self):
        """验证 client 是懒加载的。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(
            provider="test",
            model="test-model",
            base_url="https://test.api/v1",
            api_key="test-key",
        )
        adapter = TextAdapter(cfg)
        # 初始化时 _client 应为 None
        assert adapter._client is None

    def test_ask_text_mocked(self):
        """测试 ask_text（mock OpenAI client）。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(
            provider="test",
            model="test-model",
            base_url="https://test.api/v1",
            api_key="test-key",
        )

        adapter = TextAdapter(cfg)

        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "测试响应内容"
        mock_usage = MagicMock()
        mock_usage.total_tokens = 100
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice],
            usage=mock_usage,
        )
        adapter._client = mock_client

        response = adapter.ask_text("测试prompt", system="你是助手")
        assert response == "测试响应内容"
        assert adapter._stats.total_tokens == 100
        assert adapter._stats.total_calls >= 0

        # 验证调用参数
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"

    def test_ask_text_no_system_prompt(self):
        """测试不带系统提示的 ask_text。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(
            provider="test",
            model="test-model",
            base_url="https://test.api/v1",
            api_key="test-key",
        )

        adapter = TextAdapter(cfg)
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "无系统提示响应"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice],
            usage=None,
        )
        adapter._client = mock_client

        response = adapter.ask_text("纯用户prompt")
        assert response == "无系统提示响应"
        # 只有一条消息
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"

    def test_ask_text_custom_params(self):
        """测试自定义 temperature 和 max_tokens。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(
            provider="test",
            model="test-model",
            base_url="https://test.api/v1",
            api_key="test-key",
            temperature=0.1,
            max_tokens=4096,
        )

        adapter = TextAdapter(cfg)
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "自定义参数"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice],
            usage=MagicMock(total_tokens=50),
        )
        adapter._client = mock_client

        response = adapter.ask_text("prompt", temperature=0.7, max_tokens=1024)
        assert response == "自定义参数"

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 1024

    def test_ask_text_api_error(self):
        """测试 API 调用异常。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(
            provider="test",
            model="test-model",
            base_url="https://test.api/v1",
            api_key="test-key",
        )

        adapter = TextAdapter(cfg)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API不可用")
        adapter._client = mock_client

        with pytest.raises(Exception, match="API不可用"):
            adapter.ask_text("prompt")

    def test_ask_text_usage_none(self):
        """测试 usage 为 None 时不崩溃。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(provider="test", model="test", base_url="https://t.api/v1", api_key="k")
        adapter = TextAdapter(cfg)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))],
            usage=None,
        )
        adapter._client = mock_client
        response = adapter.ask_text("test")
        assert response == "ok"

    def test_import_error_handling(self):
        """openai 未安装时的错误处理。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(provider="test", model="test", base_url="https://t.api/v1", api_key="k")
        adapter = TextAdapter(cfg)

        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                _ = adapter.client


class TestLLMBaseAdapterRetry:
    """LLMBaseAdapter ask_with_retry 测试。"""

    def test_ask_with_retry_success_first_attempt(self):
        """首次尝试成功。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(provider="t", model="m", base_url="https://x/v1", api_key="k")
        adapter = TextAdapter(cfg)
        adapter.ask_text = MagicMock(return_value="success")
        result, attempts = adapter.ask_with_retry("p")
        assert result == "success"
        assert attempts == 1

    def test_ask_with_retry_fails_then_succeeds(self):
        """第一次失败，重试成功。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(provider="t", model="m", base_url="https://x/v1", api_key="k",
                        max_retries=2, retry_delay=[0.01, 0.01])
        adapter = TextAdapter(cfg)
        adapter.ask_text = MagicMock(side_effect=[Exception("失败1"), "success"])
        result, attempts = adapter.ask_with_retry("p")
        assert result == "success"
        assert attempts == 2
        assert adapter._stats.total_calls >= 1

    def test_ask_with_retry_all_attempts_fail(self):
        """所有尝试均失败。"""
        from v7.llm.base_adapter import LLMConfig
        from v7.llm.text_adapter import TextAdapter

        cfg = LLMConfig(provider="t", model="m", base_url="https://x/v1", api_key="k",
                        max_retries=1, retry_delay=[0.01])
        adapter = TextAdapter(cfg)
        adapter.ask_text = MagicMock(side_effect=Exception("持续失败"))
        with pytest.raises(RuntimeError, match="全部失败"):
            adapter.ask_with_retry("p")
        assert adapter._stats.failed_calls >= 1
