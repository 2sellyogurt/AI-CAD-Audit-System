# -*- coding: utf-8 -*-
"""SQLite 数据库 schema — 建表 + 连接管理

表结构:
  projects         项目定义
  drawings         图纸文件记录
  checkpoints      检查点规则（从 YAML 迁移）
  agent_configs    Agent 配置（Prompt/LLM绑定）
  api_keys         LLM API 密钥（加密存储）
  reviews          审查会话
  review_issues    审查问题明细
  config_versions  配置变更版本历史
"""

import os
import sqlite3
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
DB_PATH = os.environ.get("V7_DB_PATH", os.path.join(PARENT, "v7_data.db"))

SCHEMA_VERSION = 1

_local = threading.local()

SQL_CREATE_TABLES = """

-- 项目
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    dxf_dir         TEXT NOT NULL DEFAULT '',
    output_dir      TEXT NOT NULL DEFAULT '',
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 图纸
CREATE TABLE IF NOT EXISTS drawings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    discipline      TEXT NOT NULL DEFAULT 'unknown',
    text_content    TEXT DEFAULT '',
    file_size_kb    INTEGER DEFAULT 0,
    text_entities   INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    review_id       INTEGER REFERENCES reviews(id),
    uploaded_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_drawings_project ON drawings(project_id);

-- 检查点规则
CREATE TABLE IF NOT EXISTS checkpoints (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    discipline      TEXT NOT NULL DEFAULT 'building',
    check_type      TEXT NOT NULL DEFAULT 'free_review',
    route           TEXT NOT NULL DEFAULT 'text',
    severity        TEXT NOT NULL DEFAULT 'B',
    priority        INTEGER NOT NULL DEFAULT 0,
    standard_code   TEXT DEFAULT '',
    standard_clause TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 1,
    config_json     TEXT DEFAULT '{}',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_discipline ON checkpoints(discipline);

-- Agent 配置
CREATE TABLE IF NOT EXISTS agent_configs (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    discipline      TEXT NOT NULL DEFAULT 'building',
    role_title      TEXT DEFAULT '',
    experience_years INTEGER DEFAULT 15,
    persona         TEXT DEFAULT '',
    system_prompt   TEXT DEFAULT '',
    llm_provider    TEXT DEFAULT '',
    llm_model       TEXT DEFAULT '',
    max_concurrent  INTEGER DEFAULT 3,
    enabled         INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_agents_discipline ON agent_configs(discipline);

-- LLM API 密钥
CREATE TABLE IF NOT EXISTS api_keys (
    provider        TEXT PRIMARY KEY,
    api_key         TEXT NOT NULL DEFAULT '',
    base_url        TEXT DEFAULT '',
    text_model      TEXT DEFAULT '',
    vision_model    TEXT DEFAULT '',
    is_default      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 审查会话
CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    mode            TEXT NOT NULL DEFAULT 'cached',
    status          TEXT NOT NULL DEFAULT 'pending',
    total_issues    INTEGER DEFAULT 0,
    severity_a      INTEGER DEFAULT 0,
    severity_b      INTEGER DEFAULT 0,
    severity_c      INTEGER DEFAULT 0,
    severity_d      INTEGER DEFAULT 0,
    total_conflicts INTEGER DEFAULT 0,
    elapsed_ms      INTEGER DEFAULT 0,
    started_at      TEXT,
    finished_at     TEXT,
    result_json     TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_project ON reviews(project_id);

-- 审查问题明细
CREATE TABLE IF NOT EXISTS review_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id       INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    issue_id        TEXT NOT NULL,
    checkpoint_id   TEXT DEFAULT '',
    discipline      TEXT DEFAULT '',
    severity        TEXT NOT NULL DEFAULT 'C',
    standard_code   TEXT DEFAULT '',
    finding         TEXT DEFAULT '',
    fix             TEXT DEFAULT '',
    drawing_name    TEXT DEFAULT '',
    location        TEXT DEFAULT '',
    confidence      TEXT DEFAULT 'high',
    route_used      TEXT DEFAULT 'text',
    rationality     TEXT DEFAULT 'R2',
    rationality_score INTEGER DEFAULT 60,
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_issues_review ON review_issues(review_id);
CREATE INDEX IF NOT EXISTS idx_issues_severity ON review_issues(severity);

-- 配置版本历史（规则/Agent 变更追踪）
CREATE TABLE IF NOT EXISTS config_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    field_name      TEXT DEFAULT '',
    old_value       TEXT DEFAULT '',
    new_value       TEXT DEFAULT '',
    diff_json       TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_versions_target ON config_versions(target_type, target_id);

-- 系统设置（键值对）
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Schema 版本
CREATE TABLE IF NOT EXISTS schema_version (
    version         INTEGER PRIMARY KEY,
    applied_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def get_db() -> sqlite3.Connection:
    """获取线程安全的数据库连接。"""
    conn = getattr(_local, "connection", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.connection = conn
    return conn


def init_db():
    """初始化数据库表结构。"""
    conn = get_db()
    conn.executescript(SQL_CREATE_TABLES)
    conn.execute(
        "INSERT OR IGNORE INTO schema_version(version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
    return conn


def close_db():
    """关闭数据库连接。"""
    conn = getattr(_local, "connection", None)
    if conn:
        conn.close()
        _local.connection = None
