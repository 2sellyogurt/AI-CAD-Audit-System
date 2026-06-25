# -*- coding: utf-8 -*-
"""
AI审图系统 v7.0 — EXE打包入口
双击运行后自动启动Web管理后台并打开浏览器。
不依赖tkinter，纯命令行+浏览器模式。
"""

import os
import sys
import time
import webbrowser
import threading

# 确保v7包可导入
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# 设置环境变量
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("V7_ADMIN_PORT", "2708")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("v7.entry")


def open_browser_delayed(port=2708, delay=3):
    """延迟打开浏览器，支持多种方式。"""
    time.sleep(delay)
    url = f"http://localhost:{port}/admin/dashboard"
    logger.info(f"正在打开浏览器: {url}")
    
    # 方式1: 使用webbrowser模块
    try:
        webbrowser.open(url)
        logger.info("浏览器已打开")
        return
    except Exception as e:
        logger.warning(f"webbrowser.open 失败: {e}")
    
    # 方式2: Windows下使用start命令
    import platform
    if platform.system() == "Windows":
        try:
            os.system(f'start "" "{url}"')
            logger.info("浏览器已通过 start 命令打开")
            return
        except Exception as e:
            logger.warning(f"start 命令失败: {e}")
    
    # 方式3: 使用os.startfile
    if platform.system() == "Windows":
        try:
            os.startfile(url)
            logger.info("浏览器已通过 os.startfile 打开")
            return
        except Exception as e:
            logger.warning(f"os.startfile 失败: {e}")
    
    logger.error("无法自动打开浏览器，请手动访问: " + url)


def main():
    print("=" * 50)
    print("  AI审图系统 v7.0")
    print("  双击即用，无需安装Python")
    print("=" * 50)
    
    port = int(os.environ.get("V7_ADMIN_PORT", "2708"))
    
    # 延迟打开浏览器
    t = threading.Thread(target=open_browser_delayed, args=(port, 3), daemon=True)
    t.start()
    
    # 导入并启动服务器
    try:
        from v7.admin.server import main as server_main
        server_main()
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        input("按回车键退出...")


if __name__ == "__main__":
    main()
