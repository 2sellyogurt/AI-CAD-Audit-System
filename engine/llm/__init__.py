"""LLM通用适配层

使用方式：
    from engine.llm import create_llm

    # 通过环境变量配置
    llm = create_llm()

    # 显式指定provider
    llm = create_llm(provider="deepseek", model="deepseek-chat", api_key="sk-xxx")

    # 使用
    result = llm.ask("请分析这段文本...")
    result_json = llm.ask_json("请返回JSON格式...")
"""

import logging
import os
from typing import Optional

from .base_adapter import LLMAdapter, LLMConfig, LLMUsage
from .prompt_templates import (
    SYSTEM_BASE,
    prompt_step1_axis,
    prompt_step1_elevation,
    prompt_step2_compliance,
    prompt_step3_collision,
    prompt_step4_cross_discipline,
    prompt_step5_report,
    prompt_smart_verify,
)

logger = logging.getLogger("ai_audit.llm")


def create_llm(provider: Optional[str] = None, model: Optional[str] = None,
               api_key: Optional[str] = None, base_url: Optional[str] = None,
               **kwargs) -> LLMAdapter:
    if provider is None:
        provider = os.environ.get("LLM_PROVIDER", "openai")
    provider = provider.lower()

    config = LLMConfig(
        provider=provider,
        model=model or os.environ.get("LLM_MODEL", "gpt-4o"),
        api_key=api_key or os.environ.get("LLM_API_KEY", ""),
        base_url=base_url or os.environ.get("LLM_BASE_URL", ""),
        **kwargs,
    )

    if provider in ("openai", "deepseek", "qwen", "zhipu", "moonshot", "baidu"):
        from .openai_adapter import OpenAIAdapter
        return OpenAIAdapter(config)
    elif provider == "ollama":
        from .ollama_adapter import OllamaAdapter
        return OllamaAdapter(config)
    elif provider == "trae":
        from .trae_adapter import TraeAdapter
        return TraeAdapter(config)
    else:
        logger.warning("未知provider '%s'，使用OpenAI兼容接口", provider)
        from .openai_adapter import OpenAIAdapter
        return OpenAIAdapter(config)


__all__ = [
    "create_llm",
    "LLMAdapter",
    "LLMConfig",
    "LLMUsage",
    "SYSTEM_BASE",
    "prompt_step1_elevation",
    "prompt_step1_axis",
    "prompt_step2_compliance",
    "prompt_step3_collision",
    "prompt_step4_cross_discipline",
    "prompt_step5_report",
    "prompt_smart_verify",
]
