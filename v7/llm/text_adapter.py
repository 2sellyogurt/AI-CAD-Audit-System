# -*- coding: utf-8 -*-
"""OpenAI兼容文本LLM适配器

支持所有OpenAI兼容API：智谱/DeepSeek/通义千问/Moonshot/文心/Ollama
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .base_adapter import LLMBaseAdapter, LLMConfig

logger = logging.getLogger("v7.llm.text")


class TextAdapter(LLMBaseAdapter):

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=self.config.base_url,
                    api_key=self.config.api_key or "ollama",
                    timeout=self.config.timeout,
                )
            except ImportError:
                raise ImportError("需要安装 openai>=1.0: pip install openai")
        return self._client

    def ask_text(
        self,
        prompt: str,
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
        )

        content = response.choices[0].message.content or ""

        try:
            usage = response.usage
            if usage:
                self._stats.total_tokens += usage.total_tokens
        except Exception:
            pass

        return content

    def ask_vision(
        self,
        prompt: str,
        image_paths: List[str],
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        raise NotImplementedError(f"{self.config.provider}的{self.config.model}不支持视觉调用，请使用VisionAdapter")
