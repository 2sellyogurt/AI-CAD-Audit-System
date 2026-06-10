"""Trae交互式适配器

通过控制台交互使用Trae IDE内置的AI模型：
1. 系统将prompt打印到控制台
2. 用户复制prompt到Trae AI对话框
3. 用户将AI回复粘贴回控制台
4. 系统继续执行

零配置、零成本、直接使用Trae已配置的模型。
"""

import json
import logging
import os
import time
from typing import Optional

from .base_adapter import LLMAdapter, LLMConfig

logger = logging.getLogger("ai_audit.llm.trae")


class TraeAdapter(LLMAdapter):
    """Trae IDE交互式适配器"""

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(provider="trae", model="trae-interactive")
        super().__init__(config)
        self._auto_mode = os.environ.get("TRAE_AUTO_MODE", "false").lower() == "true"

    def _call_api(self, prompt: str, system: str, temperature: float,
                  max_tokens: int) -> str:
        print()
        print("=" * 60)
        print("  [Trae LLM] 需要AI分析，请按以下步骤操作:")
        print("=" * 60)

        if system:
            print()
            print("【系统提示词】")
            print(system)

        print()
        print("【用户提示词】")
        print("-" * 40)
        print(prompt)
        print("-" * 40)

        print()
        print("  操作步骤:")
        print("  1. 复制上面的【用户提示词】")
        print("  2. 在Trae AI对话框中粘贴并发送")
        print("  3. 将AI的回复粘贴到下方（输入END单独一行结束）:")
        print()

        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            except EOFError:
                break

        result = "\n".join(lines).strip()

        if not result:
            result = '{"error": "用户未输入回复"}'

        self.usage.call_count += 1
        self.usage.total_tokens += len(result) // 2

        return result

    def ask_json(self, prompt: str, system: str = "", temperature: Optional[float] = None):
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
