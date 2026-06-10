# -*- coding: utf-8 -*-
"""v7.0 管理后台 — 基于 http.server 的统一入口

架构:
  server.py   — HTTP 服务器 + 路由分发 + 密码认证
  pages/      — 6 个功能页面模块（图纸/规则/Agent/API/结果/系统）

启动: python -m v7.admin.server
"""
