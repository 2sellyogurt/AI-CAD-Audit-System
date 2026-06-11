# -*- coding: utf-8 -*-
"""多模态视觉LLM适配器

支持图片+文本混合输入，适配 OpenAI Vision API 兼容接口。
支持: GLM-4V / GPT-4o / Qwen2.5-VL / Doubao-Vision
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, List, Optional

from .base_adapter import LLMBaseAdapter, LLMConfig

logger = logging.getLogger("v7.llm.vision")


class VisionAdapter(LLMBaseAdapter):

    SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

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
        """VisionAdapter同时支持纯文本调用，统一接口。"""
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
        self._update_token_stats(response)
        return content

    def ask_vision(
        self,
        prompt: str,
        image_paths: List[str],
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """多模态视觉调用。"""
        content_parts = self._build_vision_content(prompt, image_paths)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content_parts})

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
        )
        content = response.choices[0].message.content or ""
        self._update_token_stats(response)
        return content

    def _build_vision_content(self, prompt: str, image_paths: List[str]) -> List[Dict[str, Any]]:
        """构建多模态content数组：图片(base64)+文本。"""
        content_parts = []

        for img_path in image_paths:
            if not os.path.exists(img_path):
                logger.warning(f"图片不存在，跳过: {img_path}")
                continue
            ext = os.path.splitext(img_path)[1].lower()
            if ext not in self.SUPPORTED_IMAGE_FORMATS:
                logger.warning(f"不支持的图片格式: {ext}，跳过: {img_path}")
                continue

            mime_type = f"image/{ext[1:]}" if ext != ".jpg" else "image/jpeg"
            try:
                with open(img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{img_b64}",
                        "detail": self.config.image_detail
                    }
                })
            except Exception as e:
                logger.error(f"图片编码失败: {img_path}: {e}")

        content_parts.append({"type": "text", "text": prompt})
        return content_parts

    def _update_token_stats(self, response: Any) -> None:
        try:
            usage = response.usage
            if usage:
                self._stats.total_tokens += usage.total_tokens
        except Exception:
            pass
