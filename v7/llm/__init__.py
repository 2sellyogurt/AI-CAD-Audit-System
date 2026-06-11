# -*- coding: utf-8 -*-
"""v7.0 LLM适配器工厂

提供：
- 统一LLM工厂函数（文本/视觉/混合）
- 多Provider路由（智谱/DeepSeek/OpenAI/Ollama）
- 自动故障转移（主模型失效→备用模型）
- API限流控制（429/并发上限）
- 部署模式切换（本地/混合/云端）
"""

from __future__ import annotations

import os
import time
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .base_adapter import LLMConfig, LLMBaseAdapter
from .text_adapter import TextAdapter
from .vision_adapter import VisionAdapter

logger = logging.getLogger("v7.llm")


class LLMFactory:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: str = ""):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        if not config_path:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "project_config.yaml"
            )
        self._config = self._load_config(config_path)
        self._adapters: Dict[str, LLMBaseAdapter] = {}
        self._concurrent_calls = 0
        self._concurrent_lock = threading.Lock()
        self._rate_limit_paused_until: Dict[str, float] = {}

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def get_text_adapter(self, provider: str = "") -> TextAdapter:
        """获取文本LLM适配器。"""
        if not provider:
            deployment = self._config.get("llm", {}).get("deployment", {}).get("mode", "hybrid")
            mode = self._config.get("llm", {}).get("deployment", {}).get("modes", {}).get(deployment, {})
            provider = mode.get("text_provider", self._config.get("llm", {}).get("routing", {}).get("default_text_provider", "zhipu"))

        key = f"text_{provider}"
        if key not in self._adapters:
            cfg = self._build_config(provider, "text")
            self._adapters[key] = TextAdapter(cfg)
        return self._adapters[key]

    def get_vision_adapter(self, provider: str = "", complex_mode: bool = False) -> VisionAdapter:
        """获取视觉LLM适配器。"""
        if not provider:
            if complex_mode:
                provider = self._config.get("llm", {}).get("routing", {}).get("complex_vision_provider", "openai")
            else:
                deployment = self._config.get("llm", {}).get("deployment", {}).get("mode", "hybrid")
                mode = self._config.get("llm", {}).get("deployment", {}).get("modes", {}).get(deployment, {})
                provider = mode.get("vision_provider", self._config.get("llm", {}).get("routing", {}).get("default_vision_provider", "zhipu"))

        key = f"vision_{provider}{'_complex' if complex_mode else ''}"
        if key not in self._adapters:
            cfg = self._build_config(provider, "vision")
            self._adapters[key] = VisionAdapter(cfg)
        return self._adapters[key]

    def _build_config(self, provider: str, adapter_type: str) -> LLMConfig:
        llm_cfg = self._config.get("llm", {})
        providers = llm_cfg.get("providers", {})
        provider_cfg = providers.get(provider, {})

        model = provider_cfg.get("vision_model" if adapter_type == "vision" else "text_model", "")
        base_url = provider_cfg.get("base_url", "")
        adapter_key_env = provider_cfg.get(f"{adapter_type}_api_key_env", "")
        api_key_env = adapter_key_env or provider_cfg.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""

        return LLMConfig(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=llm_cfg.get("api_timeout_seconds", 30),
            max_retries=llm_cfg.get("api_max_retries", 2),
            retry_delay=llm_cfg.get("retry_delay_seconds", [2.0, 5.0]),
        )

    def call_with_failover(
        self,
        prompt: str,
        system: str = "",
        mode: str = "text",
        image_paths: Optional[List[str]] = None,
        complex_vision: bool = False,
    ) -> Tuple[str, str]:
        """带故障转移的LLM调用。主模型失败→自动切换到备用模型。

        Returns: (result_text, used_provider)
        """
        fallback_chain = self._config.get("llm", {}).get("routing", {}).get("fallback_chain", ["zhipu"])
        last_error = None

        for provider in fallback_chain:
            try:
                self._wait_for_concurrency()
                self._wait_for_rate_limit(provider)

                if mode == "vision":
                    adapter = self.get_vision_adapter(provider, complex_vision)
                else:
                    adapter = self.get_text_adapter(provider)

                with self._concurrent_lock:
                    self._concurrent_calls += 1

                try:
                    result, _ = adapter.ask_with_retry(prompt, system, mode, image_paths)
                    return result, provider
                finally:
                    with self._concurrent_lock:
                        self._concurrent_calls -= 1

            except Exception as e:
                last_error = e
                logger.warning(f"Provider '{provider}'调用失败: {e}，尝试下一个...")

                if "429" in str(e):
                    self._rate_limit_paused_until[provider] = time.time() + 60
                    logger.warning(f"Provider '{provider}'触发限流，暂停60秒")

        raise RuntimeError(f"所有Provider调用失败，fallback_chain={fallback_chain}，最后错误: {last_error}")

    def _wait_for_concurrency(self):
        """等待并发槽位释放。"""
        max_concurrent = self._config.get("llm", {}).get("global_max_concurrent", 10)
        waited = 0
        while True:
            with self._concurrent_lock:
                if self._concurrent_calls < max_concurrent:
                    return
            time.sleep(0.5)
            waited += 0.5
            if waited > 60:
                raise RuntimeError(f"等待并发槽位超时(>60s)，当前并发: {self._concurrent_calls}")

    def _wait_for_rate_limit(self, provider: str):
        """等待Provider限流恢复。"""
        if provider in self._rate_limit_paused_until:
            wait_until = self._rate_limit_paused_until[provider]
            if time.time() < wait_until:
                remaining = wait_until - time.time()
                logger.warning(f"Provider '{provider}'限流中，等待{remaining:.0f}秒")
                time.sleep(remaining)

    def get_stats(self) -> Dict[str, Any]:
        return {
            key: {
                "total_calls": adapter.stats.total_calls,
                "success_rate": (adapter.stats.success_calls / max(adapter.stats.total_calls, 1)),
                "avg_latency_ms": adapter.stats.avg_latency_ms,
            }
            for key, adapter in self._adapters.items()
        }


def create_text_llm(provider: str = "") -> TextAdapter:
    return LLMFactory().get_text_adapter(provider)


def create_vision_llm(provider: str = "", complex_mode: bool = False) -> VisionAdapter:
    return LLMFactory().get_vision_adapter(provider, complex_mode)


def llm_call(
    prompt: str,
    system: str = "",
    mode: str = "text",
    image_paths: Optional[List[str]] = None,
    complex_vision: bool = False,
) -> Tuple[str, str]:
    return LLMFactory().call_with_failover(prompt, system, mode, image_paths, complex_vision)


def llm_call_json(
    prompt: str,
    system: str = "",
    mode: str = "text",
    image_paths: Optional[List[str]] = None,
    complex_vision: bool = False,
) -> Tuple[Optional[Dict[str, Any]], str]:
    factory = LLMFactory()
    raw, provider = factory.call_with_failover(prompt, system, mode, image_paths, complex_vision)
    try:
        from .base_adapter import LLMBaseAdapter
        extracted = LLMBaseAdapter.extract_json(raw)
        return (json_parse(extracted), provider) if extracted else ({"raw_text": raw}, provider)
    except Exception:
        return ({"raw_text": raw}, provider)


def json_parse(text: str) -> Optional[Dict[str, Any]]:
    import json as _json
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return None
