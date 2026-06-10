"""本地Ollama适配器

支持Ollama部署的本地模型：
- qwen2.5:7b / qwen2.5:14b / qwen2.5:32b
- llama3:8b / llama3:70b
- deepseek-coder-v2:16b
- glm4:9b
- llava:7b / llava:13b (视觉模型)
"""

import logging
from typing import Optional

from .base_adapter import LLMAdapter, LLMConfig

logger = logging.getLogger("ai_audit.llm.ollama")


class OllamaAdapter(LLMAdapter):
    """Ollama本地模型适配器"""

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config)
        if not self.config.base_url:
            self.config.base_url = "http://localhost:11434"

    def _call_api(self, prompt: str, system: str, temperature: float,
                  max_tokens: int) -> str:
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装httpx: pip install httpx")

        url = self.config.base_url.rstrip("/") + "/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        with httpx.Client(timeout=self.config.timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        self.usage.call_count += 1

        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)
        self.usage.total_tokens += eval_count + prompt_eval_count
        self.usage.prompt_tokens += prompt_eval_count
        self.usage.completion_tokens += eval_count

        content = data.get("message", {}).get("content", "")
        return content.strip()

    def _call_api_with_image(self, prompt: str, image_base64: str, mime_type: str,
                              system: str, temperature: float, max_tokens: int) -> str:
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装httpx: pip install httpx")

        url = self.config.base_url.rstrip("/") + "/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        user_message = {
            "role": "user",
            "content": prompt,
            "images": [image_base64],
        }
        messages.append(user_message)

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        timeout = max(self.config.timeout, 120)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        self.usage.call_count += 1

        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)
        self.usage.total_tokens += eval_count + prompt_eval_count
        self.usage.prompt_tokens += prompt_eval_count
        self.usage.completion_tokens += eval_count

        content = data.get("message", {}).get("content", "")
        return content.strip()

    def list_models(self) -> list:
        try:
            import httpx
            url = self.config.base_url.rstrip("/") + "/api/tags"
            with httpx.Client(timeout=10) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error("获取Ollama模型列表失败: %s", e)
            return []
