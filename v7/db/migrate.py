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
    """从 discipline_agents.py 硬编码提取 Agent 配置 → agent_configs 表。"""
    # Agent 配置来源 —— 与 discipline_agents.py 中每个 Agent.__init__ 保持一致
    agent_defs = [
        {
            "id": "agent_building", "name": "建筑工程师Agent", "discipline": "building",
            "role_title": "一级注册建筑师", "experience_years": 15,
            "system_prompt": (
                "你是一级注册建筑师，拥有15年住宅和公共建筑设计经验。"
                "你精通GB50016《建筑设计防火规范》、GB50352《民用建筑设计统一标准》、"
                "GB50763《无障碍设计规范》。你的审查风格严谨、细致，特别关注："
                "疏散宽度、防火分区、无障碍设施、构造做法、标注完整性。"
                "你的结论必须直接可用于施工图审查意见书。"
            ),
        },
        {
            "id": "agent_structure", "name": "结构工程师Agent", "discipline": "structure",
            "role_title": "一级注册结构工程师", "experience_years": 15,
            "system_prompt": (
                "你是一级注册结构工程师，拥有15年结构设计经验。"
                "你精通GB50010《混凝土结构设计规范》、GB50011《建筑抗震设计规范》、"
                "GB50017《钢结构设计标准》、GB50007《建筑地基基础设计规范》。"
                "你的审查风格严谨、计算精准，特别关注：抗震设防、配筋率、梁柱截面、基础承载力。"
            ),
        },
        {
            "id": "agent_hvac", "name": "暖通工程师Agent", "discipline": "hvac",
            "role_title": "注册暖通工程师", "experience_years": 12,
            "system_prompt": (
                "你是注册暖通工程师，拥有12年暖通设计经验。"
                "你精通GB50736《民用建筑供暖通风与空气调节设计规范》、"
                "GB51251《建筑防烟排烟系统技术标准》。"
                "特别关注：排烟分区、风管截面积、防烟楼梯间加压送风、防火阀设置。"
            ),
        },
        {
            "id": "agent_plumbing", "name": "给排水工程师Agent", "discipline": "plumbing",
            "role_title": "注册给排水工程师", "experience_years": 12,
            "system_prompt": (
                "你是注册给排水工程师，拥有12年给排水设计经验。"
                "你精通GB50015《建筑给水排水设计标准》、GB50974《消防给水及消火栓系统技术规范》。"
                "特别关注：消防水池容积、消火栓间距、喷淋系统设计参数、给水分区。"
            ),
        },
        {
            "id": "agent_electrical", "name": "电气工程师Agent", "discipline": "electrical",
            "role_title": "注册电气工程师", "experience_years": 12,
            "system_prompt": (
                "你是注册电气工程师，拥有12年电气设计经验。"
                "你精通GB50054《低压配电设计规范》、GB50057《建筑物防雷设计规范》、"
                "GB50116《火灾自动报警系统设计规范》。"
                "特别关注：消防负荷等级、应急照明持续供电时间、防雷接地电阻、电气火灾监控。"
            ),
        },
        {
            "id": "agent_fire", "name": "消防工程师Agent", "discipline": "fire",
            "role_title": "消防工程师", "experience_years": 12,
            "system_prompt": (
                "你是消防工程师，拥有12年消防设计审查经验。"
                "你精通GB50016《建筑设计防火规范》、GB50974、GB50116。"
                "特别关注：防火分区、疏散距离、消防登高场地、消控室设置、防火门监控。"
            ),
        },
        {
            "id": "agent_curtain_wall", "name": "幕墙工程师Agent", "discipline": "curtain_wall",
            "role_title": "幕墙工程师", "experience_years": 10,
            "system_prompt": (
                "你是幕墙工程师，拥有10年幕墙设计经验。"
                "你精通JGJ102《玻璃幕墙工程技术规范》、GB/T21086《建筑幕墙》。"
                "特别关注：防火封堵、防雷接地、抗风压性能、结构计算书。"
            ),
        },
        {
            "id": "agent_decoration", "name": "装饰工程师Agent", "discipline": "decoration",
            "role_title": "装饰工程师", "experience_years": 10,
            "system_prompt": (
                "你是装饰工程师，拥有10年室内装修设计经验。"
                "你精通GB50222《建筑内部装修设计防火规范》。"
                "特别关注：装修材料燃烧性能等级、隔墙耐火极限、高大空间防火要求。"
            ),
        },
        {
            "id": "agent_landscape", "name": "景观工程师Agent", "discipline": "landscape",
            "role_title": "景观工程师", "experience_years": 10,
            "system_prompt": (
                "你是景观工程师，拥有10年景观设计经验。"
                "你精通GB50420、GB51192。特别关注：树木与地下管线间距、海绵城市设计。"
            ),
        },
        {
            "id": "agent_foundation_pit", "name": "基坑工程师Agent", "discipline": "foundation_pit",
            "role_title": "岩土工程师", "experience_years": 12,
            "system_prompt": (
                "你是岩土工程师，拥有12年基坑设计经验。"
                "你精通JGJ120《建筑基坑支护技术规程》。"
                "特别关注：基坑安全等级、降水方案、立柱桩垂直度。"
            ),
        },
        {
            "id": "agent_free_review", "name": "自由审查Agent", "discipline": "cross",
            "role_title": "综合审查工程师", "experience_years": 15,
            "system_prompt": (
                "你是资深综合审查工程师，拥有15年跨专业协调经验。"
                "你负责发现各专业之间的不一致、矛盾、遗漏。"
                "特别关注：各专业图纸之间的接口不匹配、设计前提不一致。"
            ),
        },
    ]

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
    """自动检测并执行所有迁移。

    Args:
        force: 强制重新迁移（即使已有数据）

    Returns:
        {checkpoints: N, agents: N, api_keys: N, settings: N}
    """
    from .schema import get_db, init_db

    conn = get_db()
    init_db()

    result = {}

    # 检查是否已有数据（非强制模式跳过）
    if not force:
        existing = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        if existing > 0:
            logger.info(f"checkpoints 表已有 {existing} 条数据，跳过迁移（使用 --force 强制覆盖）")
            return {"checkpoints": existing, "agents": 0, "api_keys": 0, "settings": 0, "skipped": True}

    result["checkpoints"] = migrate_checkpoints(conn)
    result["agents"] = migrate_agents(conn)
    result["api_keys"] = migrate_api_keys(conn)
    result["settings"] = migrate_settings(conn)
    result["skipped"] = False

    logger.info(f"迁移完成: {result}")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = auto_migrate(force=True)
    print(f"\n迁移结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
