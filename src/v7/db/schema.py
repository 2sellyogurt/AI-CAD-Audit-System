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

import logging

logger = logging.getLogger("v7.db.schema")

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
    review_id       INTEGER REFERENCES reviews(id) ON DELETE SET NULL,
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

-- LLM API 密钥（按用途存储：text/vision）
CREATE TABLE IF NOT EXISTS llm_configs (
    purpose         TEXT PRIMARY KEY,           -- 'text' 或 'vision'
    provider        TEXT NOT NULL DEFAULT '',   -- 厂商标识
    api_key         TEXT NOT NULL DEFAULT '',   -- 加密存储
    base_url        TEXT DEFAULT '',
    model           TEXT DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 兼容旧表（保留，迁移时读取）
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
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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

-- 增量迁移历史（记录每次迁移的名称和时间）
CREATE TABLE IF NOT EXISTS migration_history (
    migration_name  TEXT PRIMARY KEY,
    applied_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def _current_schema_version() -> int:
    """查询当前数据库的 schema 版本号。"""
    try:
        conn = get_db()
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] if row and row[0] else 0
    except Exception as e:
        logger.debug(f"查询schema版本失败: {e}")
        return 0


def _is_migration_applied(name: str) -> bool:
    """检查指定迁移是否已执行过。"""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT 1 FROM migration_history WHERE migration_name = ?", (name,)
        ).fetchone()
        return row is not None
    except Exception as e:
        logger.debug(f"查询迁移记录失败: {e}")
        return False


def _mark_migration_applied(name: str) -> None:
    """标记一次迁移为已执行。"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO migration_history(migration_name) VALUES (?)",
        (name,),
    )
    conn.commit()


def apply_migrations() -> list:
    """按顺序执行所有待应用的增量迁移，返回已执行的迁移名列表。"""
    # 迁移定义列表：每个元组为 (迁移名, 目标schema版本, 迁移SQL或回调函数)
    MIGRATIONS = [
        # ("add_column_xxx", 2, "ALTER TABLE ... ADD COLUMN ..."),
    ]

    applied = []
    for name, target_version, sql_or_fn in MIGRATIONS:
        if _is_migration_applied(name):
            continue
        conn = get_db()
        if callable(sql_or_fn):
            sql_or_fn(conn)
        else:
            conn.executescript(sql_or_fn)
        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version) VALUES (?)",
            (target_version,),
        )
        _mark_migration_applied(name)
        applied.append(name)

    if applied:
        import logging
        logging.getLogger("v7.db").info(f"应用了 {len(applied)} 个迁移: {applied}")
    return applied


def get_db() -> sqlite3.Connection:
    """获取线程安全的数据库连接，支持自动重连。
    
    混沌工程韧性加固: 启用 WAL 模式 + busy_timeout。
    WAL 模式允许并发读写，减少 "database is locked" 错误。
    """
    conn = getattr(_local, "connection", None)
    
    # 检查连接是否有效
    if conn is not None:
        try:
            conn.execute("SELECT 1")
        except sqlite3.Error:
            # 连接已断开，关闭并重新创建
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            _local.connection = None
    
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 混沌工程韧性加固: WAL 模式 + 忙等待超时
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        logger.info(f"数据库连接已建立 (WAL模式, busy_timeout=5000ms): {DB_PATH}")
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


def backup_database(backup_path: str = None) -> str:
    """备份数据库文件到指定路径。

    Args:
        backup_path: 备份目标路径，默认自动生成时间戳文件名

    Returns:
        备份文件的绝对路径
    """
    import shutil
    from datetime import datetime

    if not os.path.isfile(DB_PATH):
        raise FileNotFoundError(f"数据库文件不存在: {DB_PATH}")

    if backup_path is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.path.dirname(DB_PATH), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"v7_data_{date_str}.db")

    # 使用 SQLite 内置备份 API 确保一致性
    src_conn = get_db()
    dst_conn = sqlite3.connect(backup_path)
    src_conn.backup(dst_conn)
    dst_conn.close()

    return backup_path


def restore_database(backup_path: str) -> None:
    """从备份文件恢复数据库。

    Args:
        backup_path: 备份文件路径

    Raises:
        FileNotFoundError: 备份文件不存在
    """
    if not os.path.isfile(backup_path):
        raise FileNotFoundError(f"备份文件不存在: {backup_path}")

    # 关闭当前连接
    close_db()

    # 用备份覆盖当前数据库
    import shutil
    shutil.copy2(backup_path, DB_PATH)

    # 重新打开连接
    get_db()


def list_backups() -> list:
    """列出所有可用的数据库备份文件。"""
    from datetime import datetime
    backup_dir = os.path.join(os.path.dirname(DB_PATH), "backups")
    if not os.path.isdir(backup_dir):
        return []

    backups = []
    for fn in sorted(os.listdir(backup_dir), reverse=True):
        if not fn.endswith(".db"):
            continue
        fp = os.path.join(backup_dir, fn)
        try:
            stat = os.stat(fp)
            backups.append({
                "filename": fn,
                "path": fp,
                "size": stat.st_size,
                "size_formatted": f"{stat.st_size / 1024:.1f} KB" if stat.st_size < 1024 * 1024 else f"{stat.st_size / (1024 * 1024):.2f} MB",
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except OSError:
            pass
    return backups
