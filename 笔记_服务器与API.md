# 笔记：服务器与API路由分析

## 一、v7.admin.server (HTTP服务器)
```
类型: 基于 http.server.HTTPServer 的自定义服务器
端口: 2708 (从配置或环境变量读取)

关键组件:
- _review_cache: 共享审查缓存 (issues, stats, conflicts, ready, taskId)
- _restore_cache_from_db(): 启动时从SQLite恢复最近审查结果
- 日志: 输出到 output_v7.0/admin.log

启动流程:
1. 加载配置 (config_loader.get_config())
2. 设置日志
3. 从数据库恢复缓存
4. 启动HTTP服务
```

## 二、v7.admin.api_routes (Flask Blueprint)
```
端点列表:
├── GET  /api/health        → 健康检查
├── GET  /api/stats         → 审查统计
├── GET  /api/issues        → 问题列表(支持过滤)
├── GET  /api/issues/<id>   → 单条问题详情
├── GET  /api/conflicts     → 空间冲突数据
├── GET  /api/reports/<scene> → 报告下载
├── GET  /api/config        → 配置信息(脱敏)
├── POST /api/review/start  → 启动审查
└── POST /api/review/progress → 审查进度

审查管线 (_run_review):
1. 加载检查点 (CheckpointEngine)
2. 提取图纸 (DrawingExtractor.find_dxf_files())
3. 处理图纸 (最多20份)
4. 创建Agent集群 (AgentOrchestrator)
5. 扫描图纸确定相关专业
6. 各专业Agent执行审查
7. 收集问题到 ProblemPool
8. 合理性标注 (annotate_all_rationality)
9. 统计分级 (A/B/C/D, R0/R1/R2/R3)
```

## 三、调试关键点
| 问题 | 排查方向 |
|------|----------|
| 服务启动失败 | 检查端口占用、config_loader导入 |
| API返回空数据 | 检查 _review_cache 是否恢复成功 |
| 审查不执行 | 检查图纸目录、DXF文件是否存在 |
| Agent执行异常 | 查看日志中 [API] [aid] 异常信息 |
| 数据库恢复失败 | 检查 v7_data.db 是否存在、表结构 |

## 四、数据流
```
输入图纸 → DrawingExtractor → drawings[]
                                ↓
检查点 ← CheckpointEngine ← Agent执行
                                ↓
                         ProblemPool
                                ↓
                    annotate_all_rationality
                                ↓
                         _review_cache
                                ↓
                         SQLite (reviews表)
```
