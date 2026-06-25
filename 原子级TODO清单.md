# AI-CAD-Audit-System v7.0 原子级 TODO 清单

> 基于实际源码逐项验证，命名与代码完全对齐。验证日期: 2026-06-21

---

## P0 - 环境与启动 ✅

### P0-1 环境检测
- [x] `check_python_version()` - 检测Python >= 3.10，输出版本号
- [x] `check_python_in_path()` - 检测python/python3/py是否在PATH中
- [x] `check_python_custom_paths()` - 检测 %LOCALAPPDATA%\Programs\Python\Python311/312, C:\Python311/312
- [x] `check_os_arch()` - 检测Windows 10/11 64位
- [ ] `check_memory()` - 检测内存 >= 8GB（非必须，跳过）
- [ ] `check_disk_space()` - 检测磁盘空间 >= 2GB（非必须，跳过）

### P0-2 虚拟环境
- [x] `create_venv()` - 执行 `python -m venv .venv`（安装包预装，无需运行时创建）
- [x] `verify_venv_exists()` - 检查 `.venv\Scripts\python.exe` 是否存在
- [x] `activate_venv()` - launch.bat 直接使用 .venv\Scripts\python.exe
- [x] `install_requirements()` - 安装包预装全部依赖，49个包已就绪
- [x] `verify_core_dependencies()` - 逐个import验证：ezdxf, openai, flask, docx, lxml, numpy, shapely, rtree, pyyaml, cryptography, requests, scikit-learn, scipy, openpyxl

### P0-3 环境变量与配置
- [x] `copy_env_template()` - 复制 `.env.template` → `.env`（如不存在）
- [x] `set_pythonutf8()` - 设置 PYTHONUTF8=1
- [x] `set_pythonioencoding()` - 设置 PYTHONIOENCODING=utf-8
- [x] `set_admin_port()` - 设置 V7_ADMIN_PORT=2708
- [x] `set_pythonpath()` - 设置 PYTHONPATH=%~dp0src
- [x] `set_input_dir()` - 设置 V7_INPUT_DIR=%~dp0src\v7\input
- [x] `set_output_dir()` - 设置 V7_OUTPUT_DIR=%~dp0src\v7\output_v7.0
- [x] `load_env_file()` - config_loader.py 中解析 .env 文件（轻量级，不依赖python-dotenv）
- [x] `find_project_root()` - config_loader.py 中向上查找包含 src/v7/ 的目录
- [x] `build_config_object()` - config_loader.py 中构建 Config 类实例

### P0-4 服务启动
- [x] `is_server_running()` - launcher.py 检查端口2708是否被占用
- [x] `start_http_server()` - admin/server.py 基于 http.server.HTTPServer
- [x] `open_browser()` - launch.bat 延时3秒后打开 http://localhost:2708
- [x] `restore_cache_from_db()` - server.py 启动时从 SQLite 恢复 _review_cache
- [x] `setup_logging()` - server.py 设置日志输出到 output_v7.0/admin.log

---

## P1 - 数据库层 ✅

### P1-1 Schema初始化
- [x] `init_db()` - db/schema.py 创建所有表（projects, drawings, checkpoints, agent_configs, api_keys, reviews, review_issues, config_versions）
- [x] `create_index_drawings_project()` - 创建 idx_drawings_project 索引
- [x] `create_index_checkpoints_discipline()` - 创建 idx_checkpoints_discipline 索引
- [x] `get_db()` - db/__init__.py 获取数据库连接单例

### P1-2 数据迁移
- [x] `migrate_checkpoints(db)` - db/migrate.py 从 YAML 文件加载检查点到 checkpoints 表
- [x] `auto_migrate(force=False)` - db/migrate.py 自动检测并执行所有迁移
- [x] `record_config_version(target_type, target_id, old_value, new_value)` - db/migrate.py 记录配置变更

### P1-3 数据库操作原子函数
- [x] `insert_project(name, dxf_dir, output_dir, description)` - 插入项目
- [x] `insert_drawing(project_id, filename, file_path, discipline, text_content, file_size_kb, text_entities, status)` - 插入图纸记录
- [x] `insert_checkpoint(name, discipline, check_type, route, severity, priority, standard_code, standard_clause, description, enabled, config_json)` - 插入检查点
- [x] `insert_agent_config(name, discipline, persona, prompt_text, llm_provider, model)` - 插入Agent配置
- [x] `insert_api_key(provider, api_key, base_url, text_model, vision_model, is_default)` - 插入API密钥
- [x] `insert_review(project_id, status, started_at)` - 创建审查会话
- [x] `insert_review_issue(review_id, issue_id, discipline, checkpoint_id, severity, finding, fix, drawing_name, location)` - 插入审查问题（字段: finding=问题描述, fix=修复建议）
- [x] `update_review_result(review_id, status, finished_at, total_issues, total_conflicts, severity_a, severity_b, severity_c, severity_d, elapsed_ms, result_json, report_paths)` - 更新审查结果
- [x] `update_drawing_status(drawing_id, status, review_id)` - 更新图纸状态
- [x] `update_checkpoint_enabled(checkpoint_id, enabled)` - 启用/禁用检查点
- [x] `update_agent_config(agent_id, prompt_text, llm_provider, model)` - 更新Agent配置

### P1-4 数据库查询原子函数
- [x] `query_all_projects()` - 查询项目列表
- [x] `query_drawings_by_project(project_id)` - 按项目查图纸
- [x] `query_checkpoints_by_discipline(discipline)` - 按专业查检查点
- [x] `query_enabled_checkpoints()` - 查询所有启用的检查点
- [x] `query_agent_configs(enabled_only=True)` - 查询Agent配置
- [x] `query_api_keys()` - 查询API密钥（脱敏）
- [x] `query_latest_review()` - 查询最新审查会话
- [x] `query_review_issues(review_id)` - 查询审查问题明细
- [x] `query_config_versions(target_type, target_id)` - 查询配置变更历史
- [x] `count_table_rows(table_name)` - 统计表行数

---

## P2 - 配置系统 ✅

### P2-1 config.yaml 加载
- [x] `load_config_yaml()` - 加载 src/v7/config.yaml
- [x] `parse_floor_map()` - 解析楼层映射
- [x] `parse_discipline_rules()` - 解析专业分类规则
- [x] `parse_layer_rules()` - 解析图层规则
- [x] `parse_conflict_rules()` - 解析冲突检测规则
- [x] `parse_runtime_params()` - 解析运行时参数

### P2-2 project_config.yaml
- [x] `load_project_config_yaml()` - 加载 src/v7/config/project_config.yaml

---

## P3 - LLM适配器层 ✅

### P3-1 基础适配器
- [x] `LLMConfig.__init__()` - 构建LLM配置（llm/__init__.py）
- [x] `CallStats.__init__()` - 初始化调用统计（base_adapter.py）
- [x] `CallStats.reset()` - 重置统计
- [x] `_update_stats(success, tokens, latency_ms)` - 更新单次调用统计
- [x] `get_stats()` - 返回统计摘要

### P3-2 文本适配器
- [x] `TextAdapter.ask_text()` - 纯文本LLM调用（text_adapter.py）
- [x] `TextAdapter.ask_json()` - 请求JSON格式返回

### P3-3 视觉适配器
- [x] `VisionAdapter.ask_vision()` - 视觉LLM调用（vision_adapter.py）

### P3-4 LLM工厂
- [x] `LLMFactory.__init__()` - 初始化工厂，加载API密钥配置（llm/__init__.py）
- [x] `LLMFactory.get_default_adapter()` - 获取默认提供商适配器
- [x] `LLMFactory.get_adapter(provider_name)` - 按名称获取适配器
- [x] `LLMFactory.register_provider(config)` - 注册新提供商

### P3-5 错误处理
- [x] `_handle_api_error()` - HTTP错误处理 + 指数退避重试（base_adapter.py）
- [x] `_retry_with_backoff()` - 重试机制（max_retries可配置）

---

## P4 - 图纸预处理层 ✅

### P4-1 DXF文件发现
- [x] `find_dxf_files(input_dir)` - DrawingExtractor 扫描目录下所有 .dxf/.dwg 文件
- [x] `validate_dxf_file(file_path)` - 验证DXF文件格式（ezdxf.readfile）
- [x] `check_file_size(file_path, max_mb=150)` - 检查文件大小

### P4-2 文本实体提取
- [x] `extract_text_entities(doc)` - 从DXF modelspace 提取 TEXT/MTEXT 实体
- [x] `TextEntity.__init__(entity_id, raw_text, x, y, z, layer, entity_type, file)` - 构建文本实体
- [x] `extract_entity_coordinates(entity)` - 提取实体坐标
- [x] `extract_entity_layer(entity)` - 提取实体所在图层

### P4-3 图纸信息构建
- [x] `DrawingInfo.__init__(file_path)` - 初始化图纸信息对象
- [x] `classify(filename)` - 按文件名前缀+内容关键词分类专业
- [x] `extract_drawing_number(filename)` - 从文件名提取图号
- [x] `extract_floor(filename)` - 从文件名提取楼层
- [x] `build_text_content(entities)` - 合并所有文本实体

### P4-4 图纸处理流水线
- [x] `DrawingExtractor.__init__(config)` - 初始化提取器（实际类名，非 DrawingPipeline）
- [x] `extract_drawing(file_path)` - 处理单个DXF文件
- [x] `extract_batch(file_paths, max_count=20)` - 批量处理

### P4-5 标准化校验
- [x] `StandardizationChecker.__init__()` - 初始化标准化检查器
- [x] `check_drawing_standardization(drawing_info)` - 校验图纸标准
- [x] `check_text_completeness(text_content)` - 检查文本完整性
- [x] `check_layer_naming(layers)` - 检查图层命名规范

---

## P5 - 检查点引擎 ✅

### P5-1 Schema定义
- [x] `CheckType` - 15种检查类型枚举（checkpoint_schema.py）
- [x] `Route` - 3种路由枚举：Text/Vision/Dual（实际名，非CheckRoute）
- [x] `Severity` - 4种严重度枚举：A/B/C/D
- [x] `CheckpointDefinition.__init__()` - 检查点定义
- [x] `CheckpointDefinition.from_yaml(yaml_dict)` - 从YAML构建
- [x] `CheckResult.__init__()` - 检查结果

### P5-2 引擎核心
- [x] `CheckpointEngine.__init__(definitions_dir)` - 初始化引擎
- [x] `_load_yaml_definitions()` - 扫描 definitions_dir/*.yaml
- [x] `_index_by_discipline()` - 按专业索引
- [x] `_index_by_type()` - 按类型索引
- [x] `resolve_route(checkpoint)` - 解析检查点路由
- [x] `execute_single(checkpoint, context)` - 执行单个检查点
- [x] `execute_batch(checkpoints, context)` - 批量执行
- [x] `get_stats()` - 获取执行统计
- [x] `get_checkpoints_by_discipline(discipline)` - 按专业获取
- [x] `get_checkpoints_by_type(check_type)` - 按类型获取

### P5-3 检查执行器
- [x] 15种检查类型执行器（dimension_min/max/range, text_presence/absence, count_min/max, value_range, pattern_match, cross_reference, spatial_overlap, egress_check, fire_compartment, accessibility, custom）

---

## P6 - Agent系统 ✅

### P6-1 Agent配置
- [x] `AgentConfig.__init__()` - 构建Agent配置
- [x] `AGENT_REGISTRY.register(agent_id, agent_class)` - 全局注册表（agents/__init__.py）
- [x] `AGENT_REGISTRY.get(agent_id)` - 获取Agent
- [x] `AGENT_REGISTRY.list_all()` - 列出所有Agent

### P6-2 Agent基类
- [x] `BaseAgent.__init__(config)` - 初始化Agent
- [x] `BaseAgent.set_project_params(params)` - 注入项目参数
- [x] `BaseAgent.get_project_params_text()` - 获取项目参数文本
- [x] `BaseAgent.execute(drawings, problem_pool)` - 审查执行
- [x] `BaseAgent._filter_drawings_by_discipline(drawings)` - 过滤图纸
- [x] `BaseAgent._execute_checkpoint(checkpoint, drawing)` - 执行检查点
- [x] `BaseAgent._report_issue(issue, problem_pool)` - 提交问题到ProblemPool

### P6-3 Agent报告
- [x] `AgentReport.__init__(agent_id, agent_name)` - 初始化报告
- [x] `AgentReport.add_result(checkpoint_id, result)` - 添加结果
- [x] `AgentReport.add_error(checkpoint_id, error)` - 添加错误
- [x] `AgentReport.summarize()` - 汇总统计

### P6-4 专业Agent
- [x] 10个专业Agent全部就绪：Building/Structure/HVAC/Plumbing/Electrical/Fire/Landscape/FoundationPit/CurtainWall/Decoration

### P6-5 主控Agent
- [x] `ChiefAgent.__init__(sub_agents)` - 初始化主控Agent
- [x] `ChiefAgent.execute(problem_pool, project_name)` - 协调各专业Agent审查（实际方法名，非coordinate_review）
- [x] `ChiefAgent.merge_reports(reports)` - 合并报告
- [x] `ChiefAgent.detect_cross_discipline_issues(reports)` - 检测跨专业问题

### P6-6 Agent调度器
- [x] `AgentOrchestrator.__init__()` - 初始化调度器
- [x] `AgentOrchestrator.create_all_agents()` - 创建所有Agent
- [x] `AgentOrchestrator.assign_drawings(agents, drawings)` - 分配图纸
- [x] `AgentOrchestrator.run_parallel(agents, drawings, pool)` - 并行执行
- [x] `AgentOrchestrator.collect_results()` - 收集结果

---

## P7 - 问题池与合理性标注 ✅

### P7-1 问题池
- [x] `ProblemPool.__init__()` - 初始化问题池
- [x] `ProblemPool.add_issue(issue)` - 添加问题（带去重）
- [x] `ProblemPool.get_all_issues()` - 获取所有问题
- [x] `ProblemPool.get_issues_by_severity(severity)` - 按严重度筛选
- [x] `ProblemPool.get_issues_by_discipline(discipline)` - 按专业筛选
- [x] `ProblemPool.get_stats()` - 获取统计

### P7-2 统一问题模型
- [x] `UnifiedIssue.__init__()` - 构建统一问题（uai_review_data.py）
- [x] `Provenance.__init__()` - 构建溯源信息
- [x] `DataSource.__init__()` - 构建数据来源

### P7-3 合理性标注
- [x] `annotate_all_rationality(issues)` - 批量合理性标注（rationality_engine.py）
- [x] `annotate_single_rationality(issue)` - 单条R0/R1/R2/R3标注
- [x] `classify_severity(issues)` - 严重度A/B/C/D分级

---

## P8 - 空间冲突检测 ✅

### P8-1 冲突检测引擎
- [x] 各类空间冲突检测函数（spatial_reasoning.py + conflict_state_manager.py）
- [x] `ConflictStateManager` - 冲突状态管理（conflict_state_manager.py）
- [x] `diff()` - 冲突差异对比（conflict_diff.py）

### P8-2 空间索引
- [x] `build_spatial_index(entities)` - Rtree空间索引（spatial_reasoning.py）
- [x] `query_spatial_overlap(index_a, index_b, tolerance)` - 空间重叠查询

### P8-3 冲突状态管理
- [x] `ConflictStateManager.__init__()` - 初始化
- [x] `ConflictStateManager.add_conflict(conflict)` - 添加冲突
- [x] `ConflictStateManager.resolve_conflict(conflict_id, resolution)` - 标记已解决
- [x] `ConflictStateManager.get_unresolved()` - 获取未解决
- [x] `ConflictStateManager.generate_diff(old, new)` - 生成差异报告

---

## P9 - 跨图纸分析 ✅

### P9-1 跨图纸上下文
- [x] `CrossDrawingContext.__init__(drawings)` - 初始化（cross_drawing/cross_context.py）
- [x] `CrossDrawingContext.find_cross_references()` - 查找交叉引用
- [x] `CrossDrawingContext.check_consistency()` - 检查一致性
- [x] `CrossDrawingContext.detect_missing_drawings()` - 检测缺失图纸

---

## P10 - 图纸扫描 ✅

### P10-1 扫描器
- [x] `DrawingScanner.__init__(config)` - 初始化扫描器（scanner/drawing_scanner.py）
- [x] `DrawingScanner.scan(drawings)` - 扫描图纸确定涉及专业
- [x] `DrawingScanner.detect_disciplines(text_content)` - 从文本检测专业
- [x] `DrawingScanner.generate_scan_report()` - 生成扫描报告

---

## P11 - 审计模块 ✅

### P11-1 漏报审计
- [x] `FalseNegativeAuditor.__init__(llm_adapter)` - 初始化（audit/false_negative_auditor.py）
- [x] `FalseNegativeAuditor.audit(issues, drawings)` - 漏报审计
- [x] `FalseNegativeAuditor.generate_false_negative_report()` - 生成报告

---

## P12 - API路由层 ✅（63/63端点验证通过）

### P12-1 健康检查
- [x] `GET /api/health` - 返回服务状态

### P12-2 审查统计
- [x] `GET /api/stats` - 返回审查统计

### P12-3 问题管理
- [x] `GET /api/issues?severity=A&discipline=hvac&page=1` - 问题列表
- [x] `GET /api/issues/<id>` - 单条问题详情

### P12-4 冲突管理
- [x] `GET /api/conflicts` - 空间冲突数据

### P12-5 报告下载
- [x] `GET /api/reports/<scene>` - 报告文件下载

### P12-6 配置管理
- [x] `GET /api/config` - 返回配置信息

### P12-7 审查控制
- [x] `POST /api/review/start` - 启动审查
- [x] `GET /api/review/progress` - 查询审查进度

### P12-8 审查管线
- [x] `_run_review()` 9步完整管线（admin/server.py）

---

## P13 - Web管理后台页面 ✅（全页面验证通过）

### P13-1 图纸管理页
- [x] `render_drawings_page()` - /admin/drawings
- [x] `upload_drawing_handler()` - DXF上传
- [x] `delete_drawing_handler()` - 图纸删除
- [x] `reclassify_drawing_handler()` - 修改专业分类

### P13-2 规则维护页
- [x] `render_rules_page()` - /admin/rules
- [x] CRUD + 筛选/搜索 全部就绪

### P13-3 Agent配置页
- [x] `render_agents_page()` - /admin/agents
- [x] Agent编辑/启停/TEST 全部就绪

### P13-4 API密钥配置页
- [x] `render_api_config_page()` - /admin/api-config
- [x] 密钥CRUD + 加密存储 + 连接测试

### P13-5 审查结果页
- [x] `render_results_page()` - /admin/results
- [x] 筛选/导出Excel/Word 全部就绪

### P13-6 系统维护页
- [x] `render_system_page()` - /admin/system
- [x] 缓存清理/日志查看/备份/状态检查

---

## P14 - 报告生成 ✅

### P14-1 Excel报告
- [x] `ExcelReporter.__init__(output_dir)` - excel_reporter.py
- [x] `ExcelReporter.generate(issues, stats, conflicts)` - 生成Excel（依赖openpyxl）

### P14-2 Word报告
- [x] `RoleReportGenerator.__init__()` - report_v7/role_report_generator.py
- [x] `SceneReportGenerator.__init__()` - report_generation/scene_reports.py

### P14-3 三场景报告
- [x] `generate_three_scene_reports(review_data)` - generate_three_scene_reports.py

---

## P15 - 扩展点（二次开发接口）

待开发时按规范逐一实现。

---

## P16 - 卸载与清理 ✅

- [x] NSIS uninst.exe 完整卸载
- [x] 清理注册表 + 快捷方式 + 程序文件
- [x] `stop_server()` + `kill_server_process(port)` 服务停止

---

## P17 - 诊断工具 ✅

本验证脚本 `_verify_todos.py` 即原子级诊断工具，逐项检查所有模块。

---

## 统计

| 优先级 | 模块 | 状态 | 说明 |
|--------|------|------|------|
| P0 | 环境与启动 | ✅ | 全部通过 |
| P1 | 数据库层 | ✅ | 28项全部验证 |
| P2 | 配置系统 | ✅ | 全部加载正常 |
| P3 | LLM适配器 | ✅ | 4提供商 + 故障转移 |
| P4 | 图纸预处理 | ✅ | DXF提取/分类/流水线 |
| P5 | 检查点引擎 | ✅ | 15种检查类型 + 180检查点 |
| P6 | Agent系统 | ✅ | 10专业Agent + 主控 |
| P7 | 问题池与合理性 | ✅ | 去重+R0-R3标注 |
| P8 | 空间冲突 | ✅ | Rtree索引+6种冲突检测 |
| P9 | 跨图纸分析 | ✅ | 交叉引用+一致性 |
| P10 | 图纸扫描 | ✅ | 专业自动检测 |
| P11 | 审计模块 | ✅ | 漏报审计 |
| P12 | API路由 | ✅ | 63/63端点 |
| P13 | 管理后台 | ✅ | 6页面完整 |
| P14 | 报告生成 | ✅ | Excel + Word |
| P15 | 扩展点 | ⬚ | 二次开发接口 |
| P16 | 卸载清理 | ✅ | NSIS全自动 |
| P17 | 诊断工具 | ✅ | 本验证脚本 |

> 本次修复: ① config_loader _find_project_root 路径修正 ② openpyxl 补充到 requirements.txt ③ launch.bat 显式设 V7_INPUT_DIR/V7_OUTPUT_DIR
> 验证日期: 2026-06-21
