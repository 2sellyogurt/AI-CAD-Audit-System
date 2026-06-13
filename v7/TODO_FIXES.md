# TODO 修复清单 —— 基于全域感知审计 (2026-06-13)

## 🔴 P0 — 必须立即修复（阻塞交付/数据安全）

### 1. 硬编码个人路径 ✅ 已修复
- **文件**: `v7/preprocessor/drawing_pipeline.py` 第43-45行
- **修复**: 默认值改为 `None`，添加缺失参数校验和 `sys.exit(1)` 提示
- **提交**: `2af3b1e`

### 2. Agent定义双重维护（必断点） ✅ 已修复
- **文件**: `v7/db/migrate.py` → 改为从 `AGENT_REGISTRY` 动态读取
- **修复**: `migrate_agents()` 实例化每个Agent类，调用 `build_system_prompt()` 获取内容
- **提交**: `3c8f2d4`

### 3. Agent注册三处同步 ✅ 已修复
- **修复**: 建立统一注册中心 `v7/agents/__init__.py` → `AGENT_REGISTRY` 字典
- **影响文件**: `master_v7.py`, `orchestrator.py`, `migrate.py` 三处统一消费 `AGENT_REGISTRY`
- **新增Agent现在只需改1处**: `v7/agents/__init__.py` + YAML文件
- **提交**: `4e9a3f5`

---

## 🟡 P1 — 本周修复

### 4. 旧管线耦合清理 ✅ 已修复
- **文件**: `v7/admin/server.py` 和 `v7/admin/api_routes.py`
- **修复**: `_run_review()` 从 `llm_full_review` 旧管线切换到 v7 Agent集群管线（CheckpointEngine + AgentOrchestrator）

### 5. 数据库自动迁移无验证 ✅ 已修复
- **文件**: `v7/db/migrate.py`
- **修复**: 新增 `_validate_sources()` 函数：校验YAML语法、Agent可实例化、API Key文件存在性
- **增强**: `auto_migrate()` 分步执行+错误收集，单步失败不影响其他步骤

### 6. 旧API Server仍可启动
- **文件**: `v7/server.py` 
- **问题**: 存在两个HTTP Server（server.py + admin/server.py），旧server.py直接调用 `llm_full_review`
- **当前状态**: 已归档到 `legacy/v7/`
- **修复**: 移除旧server.py，统一所有HTTP入口到 admin/server.py

---

## 🟢 P2 — 本月修复（测试覆盖）

### 7. 核心数据结构无单元测试 ✅ 已修复 (v7/tests/test_smoke.py)
新增 `v7/tests/test_smoke.py` — **43个测试用例**，覆盖6个模块:

| 模块 | 测试数 | 覆盖内容 |
|------|:---:|------|
| `config/building_classification.py` | 8 | 祖先计算、后代计算、层级匹配（精确/向上/向下/空值） |
| `v7/rationality_engine.py` | 8 | R0-R3等级映射、疏散评估、管综评估、合理性标注 |
| `v7/cross_drawing/cross_context.py` | 7 | 楼层/耐火/尺寸正则、空间型图纸判定、完整分析流程 |
| `v7/checkpoints/engine.py` | 11 | 加载/排序/查询/路由(A/B强制dual)/统计/reload |
| `v7/agents/discipline_agents.py` | 4 | 关键词存在性、Agent全部可实例化、图纸过滤、自由审查 |
| `v7/problem_pool/pool.py` | 5 | 添加/统计/专业筛选/合规记录/stats |

### 8. CheckpointDefinition.from_yaml() 容错不足 ✅ 已修复
- **文件**: `v7/checkpoints/checkpoint_schema.py` 
- **修复**: 未知discipline时输出 `logging.warning`，注明检查点ID和回退行为

### 9. CheckpointEngine 加载无错误明细 ✅ 已修复
- **文件**: `v7/checkpoints/engine.py` `_load_all()` 方法
- **修复**: 异常日志添加 `exc_info=True`，输出完整堆栈追溯

---

## 🔵 P3 — 技术债务

### 10. 前端专业ID与后端枚举不一致 ✅ 已修复
- **修复**: `index.html` 中 `architecture→building`, `water_supply→plumbing`, `foundation→foundation_pit`, `signage→sign`
- **保留**: `outdoor_pipe`, `solar` 无对应后端枚举，作为展示标签保留

### 11. 硬编码项目名 ✅ 已修复
- `v7/llm_full_review.py:46`: `PROJECT = os.environ.get("PROJECT_NAME", "")`
- 环境变量 `PROJECT_NAME` 现已生效

### 12. 旧测试文件依赖旧管线 ✅ 已修复
- `v7/tests/test_llm_full_review.py` — 文件头添加 `【LEGACY】` 标记
- `v7/tests/test_report_generation.py` — 文件头添加 `【LEGACY】` 标记
- 新测试请使用 `v7/tests/test_smoke.py`

### 13. 无Schema迁移版本管理 ✅ 已修复
- **文件**: `v7/db/schema.py`
- **修复**: 新增 `migration_history` 表 + `apply_migrations()` 函数
- **用法**: 在 `MIGRATIONS` 列表中添加 `(名称, 目标版本, SQL/回调)` 三元组即可增量迁移

---

## 🔴 P0-2 — 生产环境阻塞问题（第二轮审计 2026-06-13）

### 14. launcher.spec 缺失 ✅ 已修复
- **问题**: `launcher.py` 注释引用 `pyinstaller launcher.spec` 但文件不存在
- **修复**: 新建 `v7/launcher.spec`，含完整 hiddenimports/datas/excludes 配置
- **涉及文件**: `v7/launcher.spec` (新建)

### 15. README 启动命令错误 ✅ 已修复
- **问题**: 启动命令写的是旧入口 `python v7/admin/server.py`，应为 `python v7/launcher.py`
- **问题**: clone地址是占位符 `YOUR_USERNAME`
- **修复**: 启动命令改为 `python v7/launcher.py`，clone地址改为 `AI-CAD-Audit`
- **涉及文件**: `README.md`

### 16. 审查结果重启丢失 ✅ 已修复
- **问题**: `_review_cache` 在内存中，服务重启后审查结果全部丢失
- **修复**: 新增 `_persist_review_to_db()` 将结果写入 `reviews` + `review_issues` 表；新增 `_restore_cache_from_db()` 启动时从DB恢复；`launcher.py` 和 `main()` 均调用恢复
- **涉及文件**: `v7/admin/server.py`, `v7/launcher.py`

---

## 🟡 P1-2 — 生产环境阻碍问题（第二轮审计）

### 17. 无API Key时无引导提示 ✅ 已修复
- **问题**: 未配置LLM API Key时，用户不知道为何审查无法使用
- **修复**: 登录页检测 `api_keys` 表，无Key时显示黄色提示框引导前往API配置页
- **涉及文件**: `v7/admin/server.py`

### 18. 管理员密码无说明 ✅ 已修复
- **问题**: 首次无密码=任意密码可登录，但用户不知道这个行为
- **修复**: 首次登录返回 `firstLogin: true` + 提示文案，JS显示"请设置管理密码"提醒
- **涉及文件**: `v7/admin/server.py`

### 19. launcher不暴露REST API健康检查 ✅ 已修复
- **问题**: 旧server.py有 `/api/health` 但已归档，新入口无健康检查端点
- **修复**: 新增 `/api/health` 端点（无需认证），返回 `{"status":"ok","version":"7.0","port":2708}`
- **涉及文件**: `v7/admin/server.py`

### 20. 日志无轮转配置 ✅ 已修复
- **问题**: `FileHandler` 无大小限制，长期运行日志文件无限增长
- **修复**: 改为 `RotatingFileHandler`，10MB×5备份，自动轮转
- **涉及文件**: `v7/admin/server.py`

---

## 🔵 P2-2 — 生产环境改善项（第二轮审计）

### 21. opencv系统依赖未提醒 ✅ 已修复
- **问题**: Windows需VC++ Redistributable，Linux需libgl，安装失败无提示
- **修复**: `requirements.txt` 添加依赖注释；`README.md` Prerequisites新增说明
- **涉及文件**: `requirements.txt`, `README.md`

### 22. DB无备份恢复机制 ✅ 已修复
- **问题**: 数据库损坏后无法恢复，无定期备份
- **修复**: `schema.py` 新增 `backup_database()`（SQLite内置备份API）、`restore_database()`、`list_backups()`；`system.py` 新增 `/admin/api/system/backups` 和 `/admin/api/system/restore-db` 端点
- **涉及文件**: `v7/db/schema.py`, `v7/admin/pages/system.py`

---

## 已完成（本会话）

- [x] 视觉路径变量重命名和注释补全 (`engine.py`)
- [x] 创建 `_TEMPLATE.yaml` 检查点字段说明模板
- [x] 新增智能化/抗震支架/充电桩3个专业YAML定义
- [x] Discipline枚举补充 `SEISMIC_BRACING`, `EV_CHARGING`
- [x] 前端 `index.html` 专业列表更新（smart标记为已交付）
- [x] 全量180条检查点规范条文号真实性交叉验证，修正15处幻觉
- [x] 旧管线归档至 `legacy/` 目录
- [x] 创建 `launcher.spec` PyInstaller打包配置
- [x] 修正 README.md 启动命令和clone地址
- [x] 审查结果持久化到SQLite（重启不丢失）
- [x] 登录页无API Key引导提示
- [x] 首次登录密码设置提醒
- [x] 新增 /api/health 健康检查端点
- [x] 日志轮转配置（10MB×5备份）
- [x] opencv系统依赖安装提示
- [x] SQLite数据库备份恢复机制

---

## 📊 代码质量审查未解决问题（2026-06-11 原始审计，112/193 已修复）

### 剩余 Medium 级（8个有效，6个待修复）

| ID | 问题 | 文件 | 说明 |
|----|------|------|------|
| M-05 | fallback_chain无成本感知 | llm/__init__.py | 设计选择：当前由配置文件控制顺序，运维层关注 |
| M-13 | 文件名级关键字 | drawing_extractor.py | 设计选择：classify()为快速分类，已有infer_discipline_from_entities() |
| M-27 | 多个_copy_*_defs函数重复 | dwg_subset_splitter.py | 约70行重复，提取可减少维护成本 |
| M-28 | 多布局复制全部模型空间 | dwg_subset_splitter.py | 影响多布局DWG的情况，对单布局无影响 |
| M-30 | INSERT递归展开上限 | pil_renderer.py | >10层嵌套极少见 |
| M-52 | 缓存数据硬编码在源码中 | llm_full_review.py | 预编写审查数据外部化，较大工程 |
| M-59 | rtree/非rtree重复代码 | spatial_reasoning.py | 优雅降级策略，约40行重复 |
| M-71 | 145条审查数据硬编码 | uai_review_data.py | 外部化到JSON/YAML增加部署复杂度 |

### 剩余 Low 级（65个，按类型分组）

| 类型 | 数量 | 典型问题 | 建议 |
|------|------|----------|------|
| 死代码清理 | 12 | 未使用的导入/函数/变量 | 日常迭代中逐步清理 |
| 代码风格 | 13 | 三元表达式、变量命名、f-string | 低优先级润色 |
| 性能微优化 | 6 | 循环内创建字典、重复调用 | 影响极小（<1μs） |
| 魔法数字 | 9 | 截断长度、阈值硬编码 | 已处理主要项，剩余为业务参数 |
| 跨文件系统 | 25 | 路径、异常、时区、配置 | Critical/High/Medium阶段已覆盖大部分 |

### 架构改进（6个，不进修复迭代）

| ID | 改进项 | 工作量 | 状态 |
|----|--------|--------|------|
| A-01 | 项目参数锚定 | 2-3天 | 新功能，待规划 |
| A-02 | 五级空间索引 | 3-5天 | 需重构核心数据结构 |
| A-03 | 问题生命周期管理 | 1-2天 | 已有基础，待完善 |
| A-04 | 验收测试知识库 | 1天+内容 | 需施工/监理专业知识 |
| A-05 | 整改建议数值化 | 0.5天 | 锦上添花 |
| A-06 | 历史项目对比 | 3-5天 | 过度设计，建议不做 |

> **结论**: 193个问题中112个已修复(58%)。剩余81个中仅约9个值得投入，其余为误报/设计选择/极低影响。
