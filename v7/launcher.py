# -*- coding: utf-8 -*-
"""AI智能审图系统 v7.0 — 统一 EXE 启动器

启动方式:
  python launcher.py                 # 默认: 管理后台 + 前端 + 复核UI 三合一
  python launcher.py --frontend      # 仅前端/复核UI
  python launcher.py --no-browser    # 不自动打开浏览器

构建 EXE:
  pyinstaller launcher.spec
"""

import os, sys, webbrowser, socket, time, threading, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PORT = int(os.environ.get("V7_PORT", 2708))
BROWSER_DELAY = 1.2


def check_port(port):
    """检查端口是否可用。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.bind(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def open_browser():
    """延迟打开默认浏览器到管理后台。"""
    time.sleep(BROWSER_DELAY)
    url = f"http://127.0.0.1:{PORT}/admin/dashboard"
    try:
        webbrowser.open(url)
    except Exception:
        pass


def print_banner():
    """控制台启动横幅。"""
    lines = [
        "=" * 52,
        "   AI 智 能 审 图 系 统   v7.0",
        "   个人定制版 · 一站式施工图审查平台",
        "=" * 52,
        "",
        f"   管理后台: http://localhost:{PORT}/admin/dashboard",
        f"   前端界面: http://localhost:{PORT}/index.html",
        f"   复核界面: http://localhost:{PORT}/review/",
        "",
        "   按 Ctrl+C 停止服务器",
        "=" * 52,
    ]
    for line in lines:
        print(line)


def main():
    parser = argparse.ArgumentParser(description="AI智能审图系统 v7.0")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--frontend", action="store_true", help="仅启动前端/复核UI(不启动管理后台)")
    parser.add_argument("--port", type=int, default=None, help="指定端口(默认2708)")
    args = parser.parse_args()

    port = args.port or PORT

    if not check_port(port):
        print(f"\n[错误] 端口 {port} 已被占用，请关闭其他程序后重试\n")
        input("按回车退出...")
        sys.exit(1)

    # 后台线程打开浏览器
    if not args.no_browser:
        threading.Thread(target=open_browser, daemon=True).start()

    print_banner()

    # 确保必要目录存在
    os.makedirs(os.path.join(os.path.dirname(HERE), "output_v7.0"), exist_ok=True)

    os.environ["V7_PORT"] = str(port)

    try:
        from v7.admin.server import AdminHandler
        from http.server import HTTPServer
        logger = __import__('logging').getLogger("v7.launcher")
        logger.info(f"启动服务器 port={port}")

        server = None
        server = HTTPServer(("0.0.0.0", port), AdminHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
        if server:
            server.server_close()
    except Exception as e:
        print(f"\n[错误] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按回车退出...")
        sys.exit(1)


if __name__ == "__main__":
    main()
