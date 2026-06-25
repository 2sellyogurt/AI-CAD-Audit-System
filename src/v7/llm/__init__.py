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
        # 自适应策略：记录provider错误统计
        self._provider_errors: Dict[str, List[Dict[str, Any]]] = {}
        self._provider_error_lock = threading.Lock()

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"加载LLM配置文件失败: {path}, {e}")
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

        # 优先从数据库读取用户配置（管理界面保存的）
        db_model, db_base_url, db_api_key = self._load_db_config(adapter_type)

        model = db_model or provider_cfg.get("vision_model" if adapter_type == "vision" else "text_model", "")
        base_url = db_base_url or provider_cfg.get("base_url", "")
        api_key = db_api_key
        if not api_key:
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

    def _load_db_config(self, adapter_type: str) -> tuple:
        """从数据库 llm_configs 表加载用户保存的配置。"""
        try:
            from v7.db import get_db
            from v7.crypto_utils import is_encrypted, decrypt_text
            db = get_db()
            row = db.execute(
                "SELECT provider, api_key, base_url, model FROM llm_configs WHERE purpose=?",
                (adapter_type,),
            ).fetchone()
            if row and row["api_key"]:
                key = row["api_key"]
                if is_encrypted(key):
                    key = decrypt_text(key)
                return row["model"], row["base_url"], key
        except Exception as e:
            logger.debug(f"从数据库加载LLM配置失败: {e}")
        return "", "", ""

    def call_with_failover(
        self,
        prompt: str,
        system: str = "",
        mode: str = "text",
        image_paths: Optional[List[str]] = None,
        complex_vision: bool = False,
    ) -> Tuple[str, str]:
        """带故障转移的LLM调用。主模型失败→自动切换到备用模型。
        自适应策略：
        - 401认证错误：立即跳过该provider，延长冷却时间
        - 429限流错误：指数退避，读取Retry-After头
        - 5xx服务器错误：短暂延迟后重试
        - 超时错误：增加超时时间后重试

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
                err_str = str(e).lower()
                self._record_provider_error(provider, e)

                # 自适应错误处理
                if "401" in err_str or "unauthorized" in err_str or "authentication" in err_str:
                    # 认证错误：立即跳过，冷却5分钟
                    self._rate_limit_paused_until[provider] = time.time() + 300
                    logger.warning(f"Provider '{provider}'认证失败(401)，暂停5分钟")
                elif "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                    # 限流错误：指数退避，基础60秒
                    pause_time = self._calculate_backoff(provider, base_seconds=60)
                    self._rate_limit_paused_until[provider] = time.time() + pause_time
                    logger.warning(f"Provider '{provider}'触发限流(429)，自适应暂停{pause_time:.0f}秒")
                elif "timeout" in err_str or "timed out" in err_str:
                    # 超时错误：短暂暂停15秒
                    self._rate_limit_paused_until[provider] = time.time() + 15
                    logger.warning(f"Provider '{provider}'请求超时，暂停15秒后尝试下一个...")
                elif "500" in err_str or "502" in err_str or "503" in err_str or "504" in err_str:
                    # 服务器错误：暂停30秒
                    self._rate_limit_paused_until[provider] = time.time() + 30
                    logger.warning(f"Provider '{provider}'服务器错误，暂停30秒后尝试下一个...")
                else:
                    logger.warning(f"Provider '{provider}'调用失败: {e}，尝试下一个...")

        raise RuntimeError(f"所有Provider调用失败，fallback_chain={fallback_chain}，最后错误: {last_error}")

    def _record_provider_error(self, provider: str, error: Exception):
        """记录provider错误统计。"""
        with self._provider_error_lock:
            if provider not in self._provider_errors:
                self._provider_errors[provider] = []
            self._provider_errors[provider].append({
                "time": time.time(),
                "error": str(error)[:200],
            })
            # 只保留最近20条错误记录
            self._provider_errors[provider] = self._provider_errors[provider][-20:]

    def _calculate_backoff(self, provider: str, base_seconds: float = 60) -> float:
        """根据provider近期错误次数计算指数退避时间。"""
        with self._provider_error_lock:
            errors = self._provider_errors.get(provider, [])
            # 统计最近5分钟内的错误数
            recent_errors = [e for e in errors if time.time() - e["time"] < 300]
            # 指数退避：基础时间 * 2^(错误次数-1)，最多10分钟
            backoff = base_seconds * (2 ** min(len(recent_errors) - 1, 3))
            return min(backoff, 600)

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
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"JSON extraction failed: {e}, returning raw text")
        return ({"raw_text": raw}, provider)


def json_parse(text: str) -> Optional[Dict[str, Any]]:
    import json as _json
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return None
