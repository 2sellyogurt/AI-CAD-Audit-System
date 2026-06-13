# -*- coding: utf-8 -*-
"""数据迁移 — 现有 JSON/YAML/Python 配置 → SQLite

迁移来源:
  1. checkpoints/definitions/*.yaml    → checkpoints 表
  2. agents/discipline_agents.py        → agent_configs 表
  3. .encrypted_keys.json (secure_config) → api_keys 表
  4. project_config.yaml                → settings 表
  5. config.yaml (楼层/冲突/分类规则)   → settings 表
"""

import os
import sys
import json
import logging

logger = logging.getLogger("v7.db.migrate")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migrate_checkpoints(conn) -> int:
    """从 YAML 检查点定义迁移到 checkpoints 表。"""
    import yaml
    import glob

    definitions_dir = os.path.join(HERE, "checkpoints", "definitions")
    yaml_files = sorted(glob.glob(os.path.join(definitions_dir, "*.yaml")))

    count = 0
    for yf in yaml_files:
        try:
            with open(yf, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"读取 YAML 失败: {yf}: {e}")
            continue

        if not data:
            continue

        items = data.get("checkpoints", [data] if isinstance(data, dict) else data)
        if isinstance(items, dict):
            items = [items]

        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            cid = item["id"]
            conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (id, name, discipline, check_type, route, severity, priority,
                    standard_code, standard_clause, description, enabled, config_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cid,
                    item.get("name", ""),
                    item.get("discipline", "building"),
                    item.get("check_type", "free_review"),
                    item.get("route", "text"),
                    item.get("severity", "B"),
                    item.get("priority", 0),
                    item.get("standard_code", ""),
                    item.get("standard_clause", ""),
                    item.get("description", ""),
                    1,
                    json.dumps(item, ensure_ascii=False),
                ),
            )
            count += 1

    conn.commit()
    logger.info(f"迁移检查点: {count} 条")
    return count


def migrate_agents(conn) -> int:
    """从 AGENT_REGISTRY 动态加载 Agent 配置 → agent_configs 表。"""
    from v7.agents import AGENT_REGISTRY

    agent_defs = []
    for Cls in AGENT_REGISTRY.values():
        instance = Cls()
        agent_defs.append({
            "id": instance.config.agent_id,
            "name": instance.config.name,
            "discipline": instance.config.discipline,
            "role_title": instance.config.role_title,
            "experience_years": instance.config.experience_years,
            "system_prompt": instance.build_system_prompt(),
        })

    count = 0
    for a in agent_defs:
        conn.execute(
            """INSERT OR REPLACE INTO agent_configs
               (id, name, discipline, role_title, experience_years, system_prompt, enabled)
               VALUES (?,?,?,?,?,?,1)""",
            (a["id"], a["name"], a["discipline"], a["role_title"],
             a["experience_years"], a["system_prompt"]),
        )
        count += 1

    conn.commit()
    logger.info(f"迁移 Agent 配置: {count} 条")
    return count


def migrate_api_keys(conn) -> int:
    """从 .encrypted_keys.json 迁移 API 密钥。"""
    encrypted_path = os.path.join(HERE, ".encrypted_keys.json")
    if not os.path.exists(encrypted_path):
        logger.info("无 .encrypted_keys.json，跳过 API Key 迁移")
        return 0

    with open(encrypted_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for provider, key in data.get("keys", {}).items():
        conn.execute(
            """INSERT OR REPLACE INTO api_keys
               (provider, api_key, is_default) VALUES (?,?,?)""",
            (provider, key, 1 if provider == data.get("provider", "") else 0),
        )
        count += 1

    conn.commit()
    logger.info(f"迁移 API 密钥: {count} 条 (已加密存储)")
    return count


def migrate_settings(conn) -> int:
    """从 project_config.yaml + config.yaml 迁移基础设置。"""
    import yaml

    count = 0

    # project_config.yaml
    proj_cfg_path = os.path.join(HERE, "config", "project_config.yaml")
    if os.path.exists(proj_cfg_path):
        with open(proj_cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        settings_data = {
            "project_id": cfg.get("project", {}).get("id", ""),
            "project_version": cfg.get("project", {}).get("version", ""),
            "llm_timeout": str(cfg.get("llm", {}).get("api_timeout_seconds", 120)),
            "llm_max_retries": str(cfg.get("llm", {}).get("api_max_retries", 2)),
            "llm_concurrent": str(cfg.get("llm", {}).get("global_max_concurrent", 10)),
            "default_provider": cfg.get("llm", {}).get("routing", {}).get("default_text_provider", "doubao"),
            "cad_dpi": str(cfg.get("cad", {}).get("print_dpi", 300)),
            "cad_format": cfg.get("cad", {}).get("print_format", "A3"),
            "review_a_route": cfg.get("review", {}).get("dual_path", {}).get("severity_a", "mandatory"),
            "audit_sample_rate": str(cfg.get("review", {}).get("false_negative_audit", {}).get("sample_rate", 0.1)),
            "project_config_full": json.dumps(cfg, ensure_ascii=False),
        }
        for k, v in settings_data.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, v)
            )
            count += 1

    # config.yaml (楼层/冲突/分类规则)
    config_yaml_path = os.path.join(HERE, "config.yaml")
    if os.path.exists(config_yaml_path):
        with open(config_yaml_path, "r", encoding="utf-8") as f:
            sp_cfg = yaml.safe_load(f)
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            ("spatial_config_full", json.dumps(sp_cfg, ensure_ascii=False)),
        )
        count += 1

    conn.commit()
    logger.info(f"迁移系统设置: {count} 条")
    return count


def auto_migrate(force: bool = False) -> dict:
    """自动迁移所有配置到数据库。

    迁移顺序: checkpoints → agents → api_keys → settings
    每步失败不影响已成功的步骤（最终一致性）。

    Args:
        force: 强制执行覆盖已有数据，否则已有数据时跳过
    Returns:
        {checkpoints: N, agents: N, api_keys: N, settings: N, skipped: bool,
         errors: [str]}
    """
    from .schema import get_db, init_db

    conn = get_db()
    init_db()

    result = {"checkpoints": 0, "agents": 0, "api_keys": 0, "settings": 0,
              "skipped": False, "errors": []}

    # 检查是否已有数据（非强制模式跳过）
    if not force:
        existing = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        if existing > 0:
            logger.info(f"checkpoints 表已有 {existing} 条数据，跳过迁移（使用 --force 强制覆盖）")
            result["skipped"] = True
            return result

    # ---- 迁移前校验 ----
    logger.info("迁移前校验...")
    errors = _validate_sources()
    if errors:
        result["errors"] = errors
        logger.error(f"迁移终止: {len(errors)} 个校验失败:\n" + "\n".join(f"  - {e}" for e in errors))
        return result

    # ---- 增量 Schema 迁移 ----
    from .schema import apply_migrations
    applied = apply_migrations()
    if applied:
        logger.info(f"  应用增量迁移: {applied}")

    # ---- 分批迁移 ----
    steps = [
        ("checkpoints", migrate_checkpoints),
        ("agents", migrate_agents),
        ("api_keys", migrate_api_keys),
        ("settings", migrate_settings),
    ]
    for key, fn in steps:
        try:
            result[key] = fn(conn)
            logger.info(f"  ✓ {key}: {result[key]} 条")
        except Exception as e:
            msg = f"迁移 {key} 失败: {e}"
            logger.error(msg, exc_info=True)
            result["errors"].append(msg)

    logger.info(f"迁移完成: checkpoints={result['checkpoints']} "
                f"agents={result['agents']} api_keys={result['api_keys']} "
                f"settings={result['settings']} errors={len(result['errors'])}")
    return result


def _validate_sources() -> list:
    """迁移前校验数据源完整性，返回错误列表。"""
    errors = []

    # 1. 校验 YAML 检查点文件
    import yaml, glob
    yaml_dir = os.path.join(HERE, "checkpoints", "definitions")
    if not os.path.isdir(yaml_dir):
        errors.append(f"检查点目录不存在: {yaml_dir}")
    else:
        yaml_files = glob.glob(os.path.join(yaml_dir, "*.yaml"))
        if not yaml_files:
            errors.append(f"检查点目录无 YAML 文件: {yaml_dir}")
        for f in yaml_files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not data:
                    continue
                if "checkpoints" not in data:
                    # symbol_legend.yaml 等辅助文件无 checkpoints 键，正常
                    continue
            except Exception as e:
                errors.append(f"YAML 解析失败: {os.path.basename(f)}: {e}")

    # 2. 校验 Agent 注册中心
    try:
        from v7.agents import AGENT_REGISTRY
        if not AGENT_REGISTRY:
            errors.append("AGENT_REGISTRY 为空")
        else:
            for aid, cls in AGENT_REGISTRY.items():
                try:
                    inst = cls()
                    prompt = inst.build_system_prompt()
                    if not prompt:
                        errors.append(f"Agent {aid}: build_system_prompt() 返回空字符串")
                except Exception as e:
                    errors.append(f"Agent {aid} 实例化失败: {e}")
    except ImportError as e:
        errors.append(f"无法导入 AGENT_REGISTRY: {e}")

    # 3. 校验加密密钥存储（非阻塞，缺失时仅警告）
    key_file = os.path.join(HERE, ".encrypted_keys.json")
    if not os.path.exists(key_file):
        logger.info("提醒: .encrypted_keys.json 不存在，api_keys 迁移将跳过")

    return errors


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = auto_migrate(force=True)
    print(f"\n迁移结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
