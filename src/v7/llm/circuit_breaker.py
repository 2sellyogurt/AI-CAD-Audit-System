# -*- coding: utf-8 -*-
"""LLM API 熔断器（Circuit Breaker）

混沌工程韧性加固 P0-1：为 LLM 适配器添加熔断器模式。
状态机：CLOSED → OPEN → HALF_OPEN → CLOSED

设计原则：
- CLOSED: 正常调用，累计连续失败次数
- OPEN: 熔断，拒绝所有请求，等待冷却期
- HALF_OPEN: 冷却期后允许一次探测请求，成功则恢复 CLOSED，失败则重新 OPEN
"""

from __future__ import annotations

import time
import logging
import threading
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("v7.llm.cb")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """线程安全的 LLM API 熔断器。

    Args:
        name: 熔断器名称（用于日志）
        failure_threshold: 连续失败 N 次后熔断
        recovery_timeout: 熔断后冷却秒数，到期后进入半开状态
        half_open_max: 半开状态最多允许的探测请求数
        exclude_status_codes: 不触发熔断的 HTTP 状态码（如 400 参数错误不应熔断）
    """

    def __init__(
        self,
        name: str = "llm",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 1,
        exclude_status_codes: tuple = (400, 401, 403, 422),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.exclude_status_codes = exclude_status_codes

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_count = 0
        self._lock = threading.Lock()

        # 统计
        self.total_calls = 0
        self.total_rejected = 0
        self.total_success = 0
        self.total_failures = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    def _should_trip(self, status_code: Optional[int] = None) -> bool:
        """判断是否应该触发熔断（排除不可重试错误）。"""
        if status_code is not None and status_code in self.exclude_status_codes:
            return False
        return True

    def call(self, func: Callable, *args, **kwargs):
        """通过熔断器执行调用。

        Raises:
            CircuitBreakerOpenError: 熔断器打开时抛出
            RuntimeError: 半开状态探测失败时抛出
        """
        self.total_calls += 1

        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_count = 0
                    logger.info(f"[{self.name}] 熔断器进入半开状态，尝试探测")
                else:
                    self.total_rejected += 1
                    remaining = self.recovery_timeout - (time.time() - self._last_failure_time)
                    logger.warning(f"[{self.name}] 熔断器打开，拒绝请求 (剩余冷却 {remaining:.1f}s)")
                    raise CircuitBreakerOpenError(
                        f"熔断器 [{self.name}] 已打开，{remaining:.0f}秒后重试"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_count >= self.half_open_max:
                    self.total_rejected += 1
                    raise CircuitBreakerOpenError(
                        f"熔断器 [{self.name}] 半开状态已达探测上限"
                    )
                self._half_open_count += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            status_code = None
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                status_code = e.response.status_code
            elif hasattr(e, 'status_code'):
                status_code = e.status_code

            if self._should_trip(status_code):
                self._on_failure(status_code)
            raise

    def _on_success(self):
        with self._lock:
            self.total_success += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(f"[{self.name}] 半开探测成功，熔断器恢复关闭")
            else:
                self._failure_count = 0

    def _on_failure(self, status_code: Optional[int] = None):
        with self._lock:
            self.total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"[{self.name}] 半开探测失败，重新熔断 (status={status_code})")
            elif self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[{self.name}] 连续失败 {self._failure_count} 次，熔断器打开 "
                    f"(冷却 {self.recovery_timeout}s, status={status_code})"
                )

    def reset(self):
        """手动重置熔断器。"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_count = 0
            self._last_failure_time = 0.0
            logger.info(f"[{self.name}] 熔断器已手动重置")

    def get_stats(self) -> dict:
        """获取统计数据。"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "total_calls": self.total_calls,
                "total_rejected": self.total_rejected,
                "total_success": self.total_success,
                "total_failures": self.total_failures,
                "last_failure_time": self._last_failure_time,
            }


class CircuitBreakerOpenError(Exception):
    """熔断器打开时抛出的异常。"""
    pass