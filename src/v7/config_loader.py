# -*- coding: utf-8 -*-
"""
v7.0 统一配置加载器
- 自动加载 .env 文件
- 提供类型安全的配置访问接口
- 端口、路径、API Key 全部从环境变量读取，支持 .env 配置

使用:
    from v7.config_loader import get_config
    cfg = get_config()
    port = cfg.admin_port
    input_dir = cfg.input_dir
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def _load_dotenv(env_path: Path) -> None:
    """轻量级 .env 加载器（不依赖 python-dotenv）"""
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 去掉可选的引号
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                # 跳过已存在的环境变量（环境变量优先）
                if key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"[WARN] Failed to load .env: {e}", file=sys.stderr)


def _find_project_root() -> Path:
    """查找项目根目录（向上找包含 src/v7/ 的目录）"""
    cur = Path(__file__).parent  # src/v7/
    for _ in range(6):
        if (cur / "src" / "v7").is_dir():
            return cur
        cur = cur.parent
    # 兜底：向上看两层
    return Path(__file__).parent.parent.parent


class Config:
    """统一配置访问器"""

    def __init__(self):
        self.project_root = _find_project_root()
        # 自动加载 .env (从项目根目录)
        env_path = self.project_root / ".env"
        if env_path.exists():
            _load_dotenv(env_path)
        else:
            # 尝试 template
            tpl_path = self.project_root / ".env.template"
            if tpl_path.exists():
                _load_dotenv(tpl_path)

    @property
    def admin_port(self) -> int:
        return int(os.environ.get("V7_ADMIN_PORT", "2708"))

    @property
    def review_port(self) -> int:
        return int(os.environ.get("V7_REVIEW_PORT", "8080"))

    @property
    def secret_key(self) -> str:
        key = os.environ.get("V7_SECRET_KEY",
                              os.environ.get("FLASK_SECRET_KEY", ""))
        if not key:
            raise ValueError(
                "V7_SECRET_KEY 或 FLASK_SECRET_KEY 环境变量必须设置。"
                "请执行: set V7_SECRET_KEY=your-secret-key"
            )
        return key

    @property
    def flask_debug(self) -> bool:
        return os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")

    @property
    def input_dir(self) -> Path:
        path_str = os.environ.get("V7_INPUT_DIR", "input")
        path = Path(path_str)
        if not path.is_absolute():
            # project_root 已指向包含 v7/ 的目录，直接使用
            path = self.project_root / path_str
        return path

    @property
    def output_dir(self) -> Path:
        path_str = os.environ.get("V7_OUTPUT_DIR", "output")
        path = Path(path_str)
        if not path.is_absolute():
            path = self.project_root / path_str
        return path

    @property
    def cors_origins(self) -> list:
        raw = os.environ.get("V7_CORS_ORIGINS", "")
        if raw:
            return [o.strip() for o in raw.split(",") if o.strip()]
        return [
            f"http://localhost:{self.admin_port}",
            f"http://127.0.0.1:{self.admin_port}",
            f"http://localhost:{self.review_port}",
            f"http://127.0.0.1:{self.review_port}",
        ]

    def get_api_key(self) -> Optional[str]:
        """按优先级获取 LLM API Key"""
        for env_name in ("ZHIPU_API_KEY", "OPENAI_API_KEY",
                         "DEEPSEEK_API_KEY", "DOUBAO_API_KEY"):
            value = os.environ.get(env_name, "").strip()
            if value:
                return value
        return None


_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = Config()
    return _config
