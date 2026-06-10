"""LLM通用适配层 - 抽象基类

设计原则：
- 统一接口：ask(prompt, system="", temperature=0.1) -> str
- 自动重试：API失败自动重试，超时降级到规则引擎
- 成本控制：token计数 + 费用累计 + 预算上限
- 缓存机制：相同输入缓存结果，避免重复调用
"""

import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_audit.llm")


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_yuan: float = 0.0
    call_count: int = 0
    error_count: int = 0
    cache_hit_count: int = 0


@dataclass
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.1
    max_tokens: int = 2000
    timeout: int = 120
    max_retries: int = 3
    budget_yuan: float = 100.0
    enable_cache: bool = True
    cache_dir: str = ""


class LLMAdapter(ABC):
    """LLM适配器抽象基类"""

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = self._load_config_from_env()
        self.config = config
        self.usage = LLMUsage()
        self._cache: Dict[str, str] = {}
        self._cache_dir = config.cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", "llm_cache"
        )
        if config.enable_cache:
            self._load_disk_cache()

    def _load_config_from_env(self) -> LLMConfig:
        return LLMConfig(
            provider=os.environ.get("LLM_PROVIDER", "openai"),
            model=os.environ.get("LLM_MODEL", "gpt-4o"),
            api_key=os.environ.get("LLM_API_KEY", ""),
            base_url=os.environ.get("LLM_BASE_URL", ""),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000")),
            timeout=int(os.environ.get("LLM_TIMEOUT", "30")),
            max_retries=int(os.environ.get("LLM_MAX_RETRIES", "3")),
            budget_yuan=float(os.environ.get("LLM_BUDGET_YUAN", "100.0")),
            enable_cache=os.environ.get("LLM_ENABLE_CACHE", "true").lower() == "true",
        )

    def _cache_key(self, prompt: str, system: str, temperature: float) -> str:
        raw = json.dumps({"p": prompt, "s": system, "t": temperature}, ensure_ascii=False)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _load_disk_cache(self):
        cache_file = os.path.join(self._cache_dir, "llm_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {}

    def _save_disk_cache(self):
        os.makedirs(self._cache_dir, exist_ok=True)
        cache_file = os.path.join(self._cache_dir, "llm_cache.json")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def _check_budget(self) -> bool:
        if self.config.budget_yuan > 0 and self.usage.cost_yuan >= self.config.budget_yuan:
            logger.warning("LLM预算已耗尽: %.2f/%.2f 元", self.usage.cost_yuan, self.config.budget_yuan)
            return False
        return True

    def ask(self, prompt: str, system: str = "", temperature: Optional[float] = None,
            max_tokens: Optional[int] = None) -> str:
        if temperature is None:
            temperature = self.config.temperature
        if max_tokens is None:
            max_tokens = self.config.max_tokens

        if self.config.enable_cache:
            key = self._cache_key(prompt, system, temperature)
            if key in self._cache:
                self.usage.cache_hit_count += 1
                return self._cache[key]

        if not self._check_budget():
            return "[LLM_ERROR] 预算已耗尽，请增加LLM_BUDGET_YUAN或充值"

        result = ""
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                start = time.time()
                result = self._call_api(prompt, system, temperature, max_tokens)
                elapsed = time.time() - start
                logger.info("LLM调用成功 [%.1fs]: %s", elapsed, self.config.model)
                break
            except Exception as e:
                last_error = e
                self.usage.error_count += 1
                logger.warning("LLM调用失败 (第%d次): %s", attempt + 1, str(e))
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)

        if not result and last_error:
            result = "[LLM_ERROR] " + str(last_error)

        if self.config.enable_cache and result and not result.startswith("[LLM_ERROR]"):
            key = self._cache_key(prompt, system, temperature)
            self._cache[key] = result
            if len(self._cache) % 10 == 0:
                self._save_disk_cache()

        return result

    @abstractmethod
    def _call_api(self, prompt: str, system: str, temperature: float,
                  max_tokens: int) -> str:
        ...

    def ask_with_image(self, prompt: str, image_base64: str, mime_type: str = "image/png",
                       system: str = "", temperature: Optional[float] = None,
                       max_tokens: Optional[int] = None) -> str:
        if temperature is None:
            temperature = self.config.temperature
        if max_tokens is None:
            max_tokens = self.config.max_tokens

        if not self._check_budget():
            return "[LLM_ERROR] 预算已耗尽，请增加LLM_BUDGET_YUAN或充值"

        result = ""
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                start = time.time()
                result = self._call_api_with_image(prompt, image_base64, mime_type,
                                                    system, temperature, max_tokens)
                elapsed = time.time() - start
                logger.info("LLM图片识别成功 [%.1fs]: %s", elapsed, self.config.model)
                break
            except Exception as e:
                last_error = e
                self.usage.error_count += 1
                logger.warning("LLM图片识别失败 (第%d次): %s", attempt + 1, str(e))
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)

        if not result and last_error:
            result = "[LLM_ERROR] " + str(last_error)

        return result

    def _call_api_with_image(self, prompt: str, image_base64: str, mime_type: str,
                              system: str, temperature: float, max_tokens: int) -> str:
        raise NotImplementedError("此适配器不支持图片识别")

    def ask_json(self, prompt: str, system: str = "", temperature: Optional[float] = None) -> Any:
        json_system = (system or "") + "\n请严格返回JSON格式，不要包含任何其他文本。"
        raw = self.ask(prompt, json_system, temperature)
        if raw.startswith("[LLM_ERROR]"):
            return {"error": raw}
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            try:
                start = raw.index("[")
                end = raw.rindex("]") + 1
                return json.loads(raw[start:end])
            except (ValueError, json.JSONDecodeError):
                return {"raw_response": raw}

    def get_usage_summary(self) -> Dict[str, Any]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "call_count": self.usage.call_count,
            "total_tokens": self.usage.total_tokens,
            "cost_yuan": round(self.usage.cost_yuan, 4),
            "error_count": self.usage.error_count,
            "cache_hit_count": self.usage.cache_hit_count,
            "budget_remaining": round(self.config.budget_yuan - self.usage.cost_yuan, 2),
        }

    def flush_cache(self):
        if self.config.enable_cache:
            self._save_disk_cache()
