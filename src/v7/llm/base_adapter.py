# -*- coding: utf-8 -*-
"""LLM适配器抽象基类

v7.0统一适配器接口，支持文本和多模态（图文混合）两种调用模式。
所有适配器（API/本地）必须实现此接口。
"""

from __future__ import annotations

import time
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("v7.llm")

# 混沌工程韧性加固: 熔断器导入（延迟导入以避免循环依赖）
try:
    from v7.llm.circuit_breaker import CircuitBreakerOpenError, CircuitBreaker
except ImportError:
    CircuitBreakerOpenError = RuntimeError
    CircuitBreaker = None


@dataclass
class LLMConfig:
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout: int = 30
    image_detail: str = "high"
    max_retries: int = 2
    retry_delay: List[float] = field(default_factory=lambda: [1.0, 2.0, 4.0, 8.0, 16.0])
    temperature: float = 0.1
    max_tokens: int = 4096
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # 混沌工程韧性加固: 熔断器配置
    circuit_breaker_enabled: bool = True
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 30.0


@dataclass
class CallStats:
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    avg_latency_ms: float = 0.0


class LLMBaseAdapter(ABC):

    def __init__(self, config: LLMConfig):
        self.config = config
        self._stats = CallStats()
        self._call_latencies: List[float] = []
        # 混沌工程韧性加固: 熔断器
        self._circuit_breaker = None
        if config.circuit_breaker_enabled:
            from v7.llm.circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker(
                name=f"llm.{config.provider}",
                failure_threshold=config.circuit_failure_threshold,
                recovery_timeout=config.circuit_recovery_timeout,
            )

    @property
    def stats(self) -> CallStats:
        return self._stats

    @property
    def circuit_breaker(self):
        """混沌工程韧性加固: 获取熔断器实例。"""
        return self._circuit_breaker

    @abstractmethod
    def ask_text(
        self,
        prompt: str,
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """纯文本调用。"""

    @abstractmethod
    def ask_vision(
        self,
        prompt: str,
        image_paths: List[str],
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """多模态视觉调用。传入图片路径列表+文本prompt。"""

    def ask_json(
        self,
        prompt: str,
        system: str = "",
        mode: str = "text",
        image_paths: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """调用LLM并尝试解析为JSON。"""
        try:
            if mode == "vision" and image_paths:
                raw = self.ask_vision(prompt, image_paths, system)
            else:
                raw = self.ask_text(prompt, system)

            raw = self._extract_json(raw)
            return json.loads(raw) if raw else None
        except json.JSONDecodeError:
            logger.warning("LLM返回非JSON格式，返回原始文本")
            return {"raw_text": raw if 'raw' in dir() else ""}
        except (RuntimeError, IOError, ValueError) as e:
            logger.error(f"LLM调用失败: {str(e)}")
            return {"error": str(e)}

    def ask_with_retry(
        self,
        prompt: str,
        system: str = "",
        mode: str = "text",
        image_paths: Optional[List[str]] = None,
    ) -> Tuple[str, int]:
        """带重试的调用。返回(结果, 尝试次数)。指数退避 + 随机抖动 + 熔断器。"""
        max_attempts = 1 + self.config.max_retries
        last_error = None
        base_delay = self.config.retry_delay[0] if self.config.retry_delay else 2.0

        for attempt in range(max_attempts):
            try:
                # 混沌工程韧性加固: 熔断器包装调用
                def _call():
                    start = time.time()
                    if mode == "vision" and image_paths:
                        result = self.ask_vision(prompt, image_paths or [], system)
                    else:
                        result = self.ask_text(prompt, system)
                    elapsed_ms = (time.time() - start) * 1000
                    self._call_latencies.append(elapsed_ms)
                    self._stats.success_calls += 1
                    self._stats.total_calls += 1
                    if self._call_latencies:
                        self._stats.avg_latency_ms = sum(self._call_latencies) / len(self._call_latencies)
                    return result

                if self._circuit_breaker:
                    result = self._circuit_breaker.call(_call)
                else:
                    result = _call()
                return result, attempt + 1

            except ImportError:
                # circuit_breaker 模块延迟导入失败，回退到无熔断模式
                result = _call()
                return result, attempt + 1
            except CircuitBreakerOpenError as cb_err:
                logger.warning(f"熔断器拒绝调用: {cb_err}")
                raise RuntimeError(f"LLM调用被熔断: {cb_err}")
            except Exception as e:
                last_error = e
                self._stats.total_calls += 1

                # 区分可重试错误 vs 不可重试错误
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "rate limit" in error_str or "too many requests" in error_str
                is_network = any(k in error_str for k in ("timeout", "connection", "connect", "reset", "refused"))
                is_auth = any(k in error_str for k in ("401", "403", "unauthorized", "forbidden", "invalid api key"))

                # 不可重试错误: 立即抛出
                if is_auth:
                    logger.error(f"LLM鉴权失败(不可重试): {e}")
                    self._stats.failed_calls += 1
                    raise RuntimeError(f"LLM鉴权失败: {e}")

                if attempt < max_attempts - 1:
                    # 指数退避: 1s, 2s, 4s, 8s, 16s + 随机抖动 ±25%
                    if is_rate_limit:
                        delay = 60.0 + (base_delay * (2 ** attempt))
                        logger.warning(f"触发API限流(attempt {attempt+1}/{max_attempts}): {e}，{delay:.0f}秒后重试")
                    elif is_network:
                        delay = base_delay * (2 ** attempt)
                        import random
                        jitter = delay * 0.25 * (random.random() * 2 - 1)  # ±25% 抖动
                        delay += jitter
                        logger.warning(f"LLM网络错误(attempt {attempt+1}/{max_attempts}): {e}，{delay:.1f}秒后重试")
                    else:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"LLM调用失败(attempt {attempt+1}/{max_attempts}): {e}，{delay:.0f}秒后重试")
                    time.sleep(delay)

        self._stats.failed_calls += 1
        raise RuntimeError(f"LLM调用{max_attempts}次全部失败: {last_error}")

    def ask_json_with_retry(
        self,
        prompt: str,
        system: str = "",
        mode: str = "text",
        image_paths: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """带重试的JSON调用。"""
        raw, _ = self.ask_with_retry(prompt, system, mode, image_paths)
        try:
            raw = self._extract_json(raw)
            return json.loads(raw) if raw else None
        except (json.JSONDecodeError, Exception):
            return {"raw_text": raw}

    @staticmethod
    def extract_json(text: str) -> str:
        """从LLM输出中提取JSON部分。公开接口。"""
        return LLMBaseAdapter._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> str:
        """从LLM输出中提取JSON部分。"""
        if not text:
            return ""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        brace_start = text.find("{")
        bracket_start = text.find("[")
        if brace_start == -1 and bracket_start == -1:
            return text
        if brace_start == -1:
            start = bracket_start
            opener, closer = "[", "]"
        elif bracket_start == -1:
            start = brace_start
            opener, closer = "{", "}"
        else:
            start = min(brace_start, bracket_start)
            opener, closer = ("{", "}") if start == brace_start else ("[", "]")

        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text

    def is_multimodal_capable(self) -> bool:
        """是否支持多模态视觉调用。"""
        return hasattr(self, 'ask_vision') and callable(getattr(self, 'ask_vision'))
