# -*- coding: utf-8 -*-
"""
AI-CAD-Audit-System v7 桌面启动器
- 独立EXE打包，双击即用
- 内嵌浏览器查看审查结果
- 无需安装Python环境
"""

import os
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("v7.launcher")

# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output_v7.0")


def _safe_font(name, size, weight="normal"):
    """安全的字体创建：检测系统是否有指定字体，否则回退。"""
    try:
        available = set(tkfont.families())
    except (OSError, RuntimeError):
        available = set()
    if name in available:
        return (name, size, weight)
    for fallback in ("Microsoft YaHei", "SimHei", "TkDefaultFont"):
        if fallback in available:
            return (fallback, size, weight)
    return ("TkDefaultFont", size, weight)

# 端口配置 - 优先读 .env (V7_ADMIN_PORT)，默认 2708
try:
    from v7.config_loader import get_config
    _cfg = get_config()
    PORT = _cfg.admin_port
except (ImportError, ValueError):
    PORT = int(os.environ.get("V7_ADMIN_PORT", "2708"))

# 服务器进程
_server_process = None
_server_thread = None


def is_server_running():
    """检查服务是否已运行"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            result = sock.connect_ex(("127.0.0.1", PORT))
            return result == 0
    except (OSError, ConnectionError):
        return False


def start_server():
    """后台启动HTTP服务器"""
    global _server_process

    # 检查是否已运行
    if is_server_running():
        logger.info("服务器已在运行")
        return True

    try:
        # 导入并启动服务器
        # PYTHONPATH 由启动器 (start.py) 设置为 源代码/，所以这里不需要再插入路径
        # 保留 SCRIPT_DIR 仅用于确保 config_loader 可导入
        import sys as _sys
        _project_root = os.path.dirname(SCRIPT_DIR)
        if _project_root not in _sys.path:
            _sys.path.insert(0, _project_root)
        from v7.admin.server import main as server_main

        # 在后台线程运行
        thread = threading.Thread(target=server_main, daemon=True)
        thread.start()

        # 等待服务器启动
        for i in range(30):
            time.sleep(0.5)
            if is_server_running():
                logger.info(f"服务器已启动 (端口 {PORT})")
                return True

        logger.warning("服务器启动超时")
        return False

    except Exception as e:
        logger.error(f"启动服务器失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def open_browser():
    """打开浏览器"""
    url = f"http://localhost:{PORT}/admin/dashboard"
    try:
        webbrowser.open(url)
        logger.info(f"已打开浏览器: {url}")
    except Exception as e:
        logger.error(f"打开浏览器失败: {e}")


def create_gui():
    """创建GUI界面"""
    root = tk.Tk()
    root.title("AI智能审图系统 v7.0")
    root.geometry("600x400")
    root.resizable(True, True)

    # 窗口居中
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 600) // 2
    y = (root.winfo_screenheight() - 400) // 2
    root.geometry(f"600x400+{x}+{y}")

    # 主框架
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 标题
    title_label = ttk.Label(
        main_frame,
        text="AI智能审图系统 v7.0",
        font=_safe_font("Microsoft YaHei", 20, "bold")
    )
    title_label.pack(pady=20)

    # 副标题
    subtitle_label = ttk.Label(
        main_frame,
        text="建筑施工图AI审查工具",
        font=_safe_font("Microsoft YaHei", 10)
    )
    subtitle_label.pack(pady=(0, 30))

    # 状态显示区
    status_frame = ttk.LabelFrame(main_frame, text="运行状态", padding="10")
    status_frame.pack(fill=tk.X, pady=10)

    status_label = ttk.Label(status_frame, text="● 等待启动", foreground="gray")
    status_label.pack(anchor=tk.W)

    # 进度条
    progress = ttk.Progressbar(status_frame, mode="indeterminate", length=400)
    progress.pack(fill=tk.X, pady=(10, 0))
    progress.stop()

    # 日志区
    log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
    log_frame.pack(fill=tk.BOTH, expand=True, pady=10)

    log_text = tk.Text(log_frame, height=10, width=60, state=tk.DISABLED)
    log_text.pack(fill=tk.BOTH, expand=True)

    def append_log(msg):
        log_text.config(state=tk.NORMAL)
        log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        log_text.see(tk.END)
        log_text.config(state=tk.DISABLED)

    # 按钮区
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(fill=tk.X, pady=(10, 0))

    start_btn = ttk.Button(btn_frame, text="▶ 启动服务", style="Accent.TButton")
    open_btn = ttk.Button(btn_frame, text="🌐 打开界面", state=tk.DISABLED)
    stop_btn = ttk.Button(btn_frame, text="■ 停止服务")

    start_btn.pack(side=tk.LEFT, padx=5)
    open_btn.pack(side=tk.LEFT, padx=5)
    stop_btn.pack(side=tk.LEFT, padx=5)

    # 状态管理
    server_running = [False]

    def on_start():
        if server_running[0]:
            append_log("服务已在运行中...")
            return

        append_log("正在启动服务...")
        status_label.config(text="● 启动中...", foreground="orange")
        start_btn.config(state=tk.DISABLED)
        progress.pack(fill=tk.X, pady=(10, 0))
        progress.start(10)

        def do_start():
            global _server_thread
            success = start_server()
            if success:
                server_running[0] = True
                append_log("服务启动成功!")
                status_label.config(text="● 服务运行中", foreground="green")
                open_btn.config(state=tk.NORMAL)
                start_btn.config(state=tk.DISABLED)
                # 自动打开浏览器
                root.after(500, open_browser)
            else:
                append_log("服务启动失败!")
                status_label.config(text="● 启动失败", foreground="red")
                start_btn.config(state=tk.NORMAL)
            progress.stop()
            progress.pack_forget()

        threading.Thread(target=do_start, daemon=True).start()

    def on_open():
        append_log("正在打开浏览器...")
        open_browser()

    def on_stop():
        if not server_running[0]:
            append_log("服务未运行")
            return
        # 本启动器不真正停止服务器，只更新状态
        append_log("请手动关闭服务")
        server_running[0] = False
        status_label.config(text="● 已停止", foreground="gray")
        start_btn.config(state=tk.NORMAL)
        open_btn.config(state=tk.DISABLED)

    start_btn.config(command=on_start)
    open_btn.config(command=on_open)
    stop_btn.config(command=on_stop)

    # 检查服务是否已运行
    if is_server_running():
        server_running[0] = True
        status_label.config(text="● 服务运行中", foreground="green")
        open_btn.config(state=tk.NORMAL)
        start_btn.config(state=tk.DISABLED)
        append_log("检测到已有服务在运行")
    else:
        append_log("就绪，点击「启动服务」开始")

    # 菜单栏
    menubar = tk.Menu(root)
    root.config(menu=menubar)

    help_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="帮助", menu=help_menu)
    help_menu.add_command(label="使用说明", command=lambda: messagebox.showinfo("使用说明",
        "1. 点击「启动服务」启动AI审图服务\n"
        "2. 服务启动后自动打开浏览器\n"
        "3. 在Web界面中进行图纸审查操作\n"
        "4. 首次使用需配置LLM API密钥"))
    help_menu.add_command(label="关于", command=lambda: messagebox.showinfo("关于",
        "AI智能审图系统 v7.0\n\n"
        "基于第一性原理的建筑施工图AI审查工具\n"
        "支持10+专业Agent协同审查\n"
        "Copyright 2026"))

    return root


def main():
    logger.info("启动 AI-CAD-Audit-System v7.0 桌面端")

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 创建并运行GUI
    root = create_gui()
    root.mainloop()


if __name__ == "__main__":
    main()
