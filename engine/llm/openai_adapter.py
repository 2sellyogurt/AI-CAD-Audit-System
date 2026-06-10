"""OpenAI兼容适配器

支持所有OpenAI兼容API：
- OpenAI (GPT-4o, GPT-4o-mini)
- DeepSeek (deepseek-chat, deepseek-reasoner)
- 通义千问 (qwen-plus, qwen-turbo) via DashScope OpenAI兼容接口
- 智谱 (glm-4) via OpenAI兼容接口
- 月之暗面 (moonshot-v1-8k)
- 百度文心 (ernie-4.0) via OpenAI兼容接口
"""

import logging
from typing import Optional

from .base_adapter import LLMAdapter, LLMConfig

logger = logging.getLogger("ai_audit.llm.openai")

_PRICE_MAP = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "deepseek-chat": {"input": 1.0, "output": 2.0},
    "deepseek-reasoner": {"input": 4.0, "output": 16.0},
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "qwen-turbo": {"input": 0.3, "output": 0.6},
    "qwen-max": {"input": 20.0, "output": 60.0},
    "glm-4": {"input": 100.0, "output": 100.0},
    "moonshot-v1-8k": {"input": 12.0, "output": 12.0},
    "ernie-4.0-8k": {"input": 30.0, "output": 60.0},
}

_DEFAULT_PRICE = {"input": 1.0, "output": 2.0}

_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "baidu": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop",
}


class OpenAIAdapter(LLMAdapter):
    """OpenAI兼容API适配器"""

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config)
        self._ensure_base_url()
        self._price = _PRICE_MAP.get(self.config.model, _DEFAULT_PRICE)

    def _ensure_base_url(self):
        if not self.config.base_url:
            provider = self.config.provider.lower()
            if provider in _DEFAULT_BASE_URLS:
                self.config.base_url = _DEFAULT_BASE_URLS[provider]
            else:
                self.config.base_url = _DEFAULT_BASE_URLS["openai"]

    def _call_api(self, prompt: str, system: str, temperature: float,
                  max_tokens: int) -> str:
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装httpx: pip install httpx")

        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + self.config.api_key,
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=self.config.timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        self.usage.prompt_tokens += prompt_tokens
        self.usage.completion_tokens += completion_tokens
        self.usage.total_tokens += prompt_tokens + completion_tokens
        self.usage.call_count += 1

        cost = (prompt_tokens * self._price["input"] +
                completion_tokens * self._price["output"]) / 1_000_000
        self.usage.cost_yuan += cost

        content = data["choices"][0]["message"]["content"]
        if content is None:
            content = ""
        return content.strip()
