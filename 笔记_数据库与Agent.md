# 笔记：数据库与Agent系统分析

## 一、数据库 Schema (v7/db/schema.py)
```
数据库路径: v7_data.db (环境变量 V7_DB_PATH 可覆盖)
Schema版本: 1

表结构:
├── projects          项目定义
│   ├── id, name, dxf_dir, output_dir, description
│   └── created_at, updated_at
├── drawings          图纸文件记录
│   ├── id, project_id(FK), filename, file_path
│   ├── discipline, text_content, file_size_kb
│   ├── text_entities, status, review_id(FK)
│   └── uploaded_at
├── checkpoints       检查点规则 (从YAML迁移)
│   ├── id(PK), name, discipline, check_type
│   ├── route, severity, priority, standard_code
│   ├── standard_clause, description, enabled
│   └── config_json, updated_at
├── agent_configs     Agent配置 (Prompt/LLM绑定)
│   ├── id(PK), name, discipline, persona
│   ├── prompt_text, llm_provider, model
│   └── created_at, updated_at
├── api_keys          LLM API密钥 (加密存储)
│   ├── provider(PK), api_key, base_url
│   ├── text_model, vision_model, is_default
│   └── created_at, updated_at
├── reviews           审查会话
│   ├── id, project_id, status, started_at
│   ├── finished_at, total_issues, total_conflicts
│   ├── severity_a/b/c/d, elapsed_ms, result_json
│   └── report_paths
├── review_issues     审查问题明细
│   ├── id, review_id(FK), issue_id, discipline
│   ├── checkpoint_id, severity, rationality_level
│   ├── description, location, suggestion
│   └── standard_code, standard_clause
└── config_versions   配置变更版本历史
    ├── id, target_type, target_id
    ├── old_value, new_value, created_at

索引:
- idx_drawings_project (project_id)
- idx_checkpoints_discipline (discipline)
```

## 二、Agent基类 (v7/agents/base_agent.py)
```
核心类:
├── AgentConfig (配置)
│   ├── agent_id, name, discipline
│   ├── persona, role_title, experience_years
│   ├── standards, checkpoints
│   └── text_provider, vision_provider, max_concurrent
├── AgentReport (报告)
│   ├── agent_id, agent_name
│   ├── total_checkpoints, executed, issues_found
│   ├── errors, total_time_ms, results
│   └── self_assessment, cross_discipline_notes, error
└── BaseAgent (抽象基类)
    ├── set_project_params(): 注入项目参数
    ├── get_project_params_text(): 获取项目参数文本
    ├── execute(): 抽象方法，子类实现
    └── _report: AgentReport实例

Agent执行流程:
1. master_v7 创建Agent并注入项目参数
2. 调用 agent.execute(drawings, problem_pool)
3. Agent过滤相关专业图纸
4. 执行检查点审查
5. 发现问题加入 ProblemPool
6. 返回 AgentReport
```

## 三、调试关键点
| 问题 | 排查方向 |
|------|----------|
| 数据库连接失败 | 检查 v7_data.db 文件权限 |
| 表不存在 | 运行 db/schema.py 初始化 |
| Agent不执行 | 检查 agent_configs 表是否有配置 |
| 检查点加载失败 | 检查 checkpoints 表数据 |
| API密钥错误 | 检查 api_keys 表 |
| 审查结果不保存 | 检查 reviews/review_issues 表 |

## 四、常用SQL调试
```sql
-- 查看项目列表
SELECT * FROM projects;

-- 查看图纸列表
SELECT id, filename, discipline, status FROM drawings;

-- 查看检查点统计
SELECT discipline, COUNT(*) FROM checkpoints WHERE enabled=1 GROUP BY discipline;

-- 查看最新审查结果
SELECT * FROM reviews ORDER BY id DESC LIMIT 1;

-- 查看问题明细
SELECT * FROM review_issues WHERE review_id = ?;

-- 查看Agent配置
SELECT id, name, discipline, llm_provider FROM agent_configs;
```
