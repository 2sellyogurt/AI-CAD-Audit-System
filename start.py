#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台启动脚本

支持 Windows / macOS / Linux
功能：
1. 检测 Python 3.10+
2. 创建虚拟环境（如果不存在）
3. 安装依赖
4. 复制 .env.template → .env（如果不存在）
5. 启动服务
"""

import os
import sys
import subprocess
import venv
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
ENV_TEMPLATE = PROJECT_ROOT / ".env.template"
ENV_FILE = PROJECT_ROOT / ".env"


def check_python() -> bool:
    """检查Python版本是否>=3.10。"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"[错误] 需要 Python 3.10+，当前 {version.major}.{version.minor}.{version.micro}")
        print("请访问 https://www.python.org/downloads/ 下载安装")
        return False
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
    return True


def create_venv() -> bool:
    """创建虚拟环境。"""
    if VENV_DIR.exists():
        print("[OK] 虚拟环境已存在")
        return True
    
    print("[...] 创建虚拟环境...")
    try:
        venv.create(VENV_DIR, with_pip=True)
        print("[OK] 虚拟环境创建成功")
        return True
    except Exception as e:
        print(f"[错误] 创建虚拟环境失败: {e}")
        return False


def get_python_executable() -> Path:
    """获取虚拟环境中的Python可执行文件路径。"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    else:
        return VENV_DIR / "bin" / "python"


def install_dependencies() -> bool:
    """安装依赖。"""
    if not REQUIREMENTS.exists():
        print(f"[警告] 未找到 {REQUIREMENTS}")
        return True
    
    pip = get_python_executable().parent / ("pip.exe" if sys.platform == "win32" else "pip")
    
    # 检查是否已安装关键依赖
    result = subprocess.run(
        [str(get_python_executable()), "-c", "import flask"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("[OK] 依赖已安装")
        return True
    
    print("[...] 安装依赖（可能需要几分钟）...")
    # 使用清华镜像加速
    result = subprocess.run(
        [str(pip), "install", "-r", str(REQUIREMENTS), 
         "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
        capture_output=False,
    )
    if result.returncode != 0:
        print("[警告] 清华镜像安装失败，尝试默认源...")
        result = subprocess.run(
            [str(pip), "install", "-r", str(REQUIREMENTS)],
            capture_output=False,
        )
    
    if result.returncode == 0:
        print("[OK] 依赖安装成功")
        return True
    else:
        print("[错误] 依赖安装失败")
        return False


def setup_env() -> bool:
    """设置环境变量文件。"""
    if ENV_FILE.exists():
        print("[OK] 环境变量文件已存在")
        return True
    
    if ENV_TEMPLATE.exists():
        print("[...] 复制环境变量模板...")
        import shutil
        shutil.copy2(ENV_TEMPLATE, ENV_FILE)
        print(f"[OK] 已创建 {ENV_FILE}，请编辑配置API密钥")
    else:
        print("[警告] 未找到 .env.template")
    return True


def start_server() -> bool:
    """启动服务器。"""
    print("[...] 启动 AI审图服务...")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        subprocess.run(
            [str(get_python_executable()), "-m", "v7.admin.server"],
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        return True
    except KeyboardInterrupt:
        print("\n[OK] 服务已停止")
        return True
    except Exception as e:
        print(f"[错误] 启动失败: {e}")
        return False


def main():
    """主入口。"""
    print("=" * 50)
    print("  AI审图 v7.0 启动器")
    print("=" * 50)
    
    if not check_python():
        sys.exit(1)
    
    if not create_venv():
        sys.exit(1)
    
    if not install_dependencies():
        sys.exit(1)
    
    if not setup_env():
        sys.exit(1)
    
    print("=" * 50)
    start_server()


if __name__ == "__main__":
    main()
