# AI-CAD-Audit-System 代码改进TODO文档

> 基于 CODE_IMPROVEMENT_ANALYSIS.md + 「几个模型的审核意见.txt」生成
> 生成日期：2026-06-11
> 总问题数：193个（代码问题187个 + 架构改进6个）

---

## 目录

1. [执行拆解清单（193个独立子任务）](#执行拆解清单)
2. [Critical级问题（12个）](#critical级问题)
3. [High级问题（38个）](#high级问题)
4. [Medium级问题（72个）](#medium级问题)
5. [Low级问题（65个）](#low级问题)
6. [架构层面改进（6个）](#架构层面改进)
7. [修复优先级路线图](#修复优先级路线图)

---

## 执行拆解清单（193个独立子任务）

### 【模型安全执行粒度说明】
每个子任务遵循**单一文件+单一修改+可验证**原则，确保模型执行时不会因上下文过载产生幻觉。

---

### 第一阶段：Critical级修复（12个独立子任务）

| 序号 | 子任务 | 修改文件 | 具体操作 |
|------|--------|----------|----------|
| ① | 修复正则表达式错误 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L99) | 将`\|`替换为`|` |
| ② | 修复图框裁剪参数 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py#L121-133) | 调用`render_dxf_pil`时传入x_min/x_max/y_min/y_max |
| ③ | 修复空间分析bounds | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L182-184) | 将`src_idx.bounds`改为`src_idx.bounds(src_eid)` |
| ④ | 修复DXF标记坐标 | [dxf_marker.py](file:///f:/AI-CAD-Audit-System/v7/dxf_marker.py#L77) | 从冲突数据提取实际坐标，替换`cx,cy=0,0` |
| ⑤ | 修复Excel列数问题 | [excel_reporter.py](file:///f:/AI-CAD-Audit-System/v7/excel_reporter.py#L74) | 使用`openpyxl.utils.get_column_letter(i)`替代`chr(64+i)` |
| ⑥ | 修复pickle安全漏洞(1) | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L6) | 将pickle替换为json模块 |
| ⑦ | 修复pickle安全漏洞(2) | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py#L64-65) | 将pickle替换为json模块 |
| ⑧ | 修复API密钥安全 | [secure_config.py](file:///f:/AI-CAD-Audit-System/v7/secure_config.py#L28-29) | 无环境变量时拒绝运行并抛出异常 |
| ⑨ | 修复HTTP请求限制 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py#L231-232) | 添加`max_content_length = 10 * 1024 * 1024` |
| ⑩ | 修复硬编码路径 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py#L1182) | 使用`os.path.dirname(os.path.abspath(__file__))` |
| ⑪ | 修复加权计算逻辑 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py#L336) | 使用权重计算：`sum(s * w for (s,_), w in zip(scores, weights)) / total_weight` |
| ⑫ | 修复路径遍历漏洞 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py#L222-228) | 使用`os.path.realpath()`验证路径在允许范围内 |

---

### 第二阶段：High级修复（38个独立子任务）

| 序号 | 子任务 | 修改文件 | 具体操作 |
|------|--------|----------|----------|
| ⑬ | 修复字符类正则 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L48,68,74) | `[C\|c]`→`[Cc]` |
| ⑭ | 修复搜索范围 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L271-273) | 限定搜索范围为组件上下文 |
| ⑮ | 修复关键字冲突 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L63-88) | 添加优先级机制 |
| ⑯ | 修复楼层提取 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L362) | 返回`match.group(0)` |
| ⑰ | 修复detector初始化 | [drawing_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_pipeline.py#L246) | 统一初始化为None |
| ⑱ | 修复pop修改 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py#L451,491) | `pop()`→`get()` |
| ⑲ | 修复ELLIPSE bbox | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py#L105-108) | 使用模长计算 |
| ⑳ | 修复rtree实现 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py#L76-83) | 实现或移除未使用功能 |
| ㉑ | 修复ARC坐标转换 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L258-260) | 实现完整角度坐标系转换 |
| ㉒ | 修复professional字段 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py#L183) | `severity`→`discipline` |
| ㉓ | 修复risk_level默认值 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L148-151) | `medium`→`high` |
| ㉔ | 修复轴网检查 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L204) | 添加Y方向检查 |
| ㉕ | 修复标高过滤 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L291-292) | 使用`try/except float()` |
| ㉖ | 修复运算符优先级 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L119-121) | 拆分为多行 |
| ㉗ | 修复verdict字段 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L165-169) | 添加或检查正确字段 |
| ㉘ | 修复pickle安全(3) | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py#L94) | pickle→json |
| ㉙ | 修复空间索引 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L635-638) | 建立分类索引 |
| ㉚ | 修复CORS设置 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py#L115) | 限制为特定域名 |
| ㉛ | 修复server变量 | [launcher.py](file:///f:/AI-CAD-Audit-System/v7/launcher.py#L98) | 初始化为None并检查 |
| ㉜ | 修复性能问题 | [conflict_state_manager.py](file:///f:/AI-CAD-Audit-System/v7/conflict_state_manager.py#L176-177) | 循环外计算cur_keys |
| ㉝ | 修复MTEXT换行 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L291) | 移除`.replace("\\p", "\n")` |
| ㉞ | 修复MTEXT提取 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L289) | `e.plain_text()` |
| ㉟ | 修复A0匹配 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py#L90) | 使用精确匹配 |
| ㊱ | 修复分类器排序 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L209) | 添加确定性排序 |
| ㊲ | 修复缓存限制 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L111) | 使用`lru_cache` |
| ㊳ | 修复缓存exists | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L126) | 添加`os.path.exists()`检查 |
| ㊴ | 修复openpyxl导入 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py#L483) | 添加导入检查 |
| ㊵ | 修复columns空列表 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py#L479) | 添加空列表检查 |
| ㊶ | 修复deepcopy | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py#L232,298) | 使用ezdxf复制方法 |
| ㊷ | 修复IMAGE bbox | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py#L130-131) | 使用`get_bbox()` |
| ㊸ | 修复scanner缓存 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L91) | 使用`lru_cache` |
| ㊹ | 修复report_translator硬编码 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py#L518) | 使用正常多行代码 |
| ㊺ | 修复secure_config存储 | [secure_config.py](file:///f:/AI-CAD-Audit-System/v7/secure_config.py#L92-94) | 无加密库时拒绝存储 |
| ㊻ | 提取重复代码(1) | unified_pipeline.py vs spatial_reasoning.py | 提取到共享模块 |
| ㊼ | 提取重复代码(2) | generate_three_scene_reports.py vs llm_full_review.py | 统一到独立模块 |
| ㊽ | 提取重复代码(3) | dwg_converter.py vs cad_printer.py | 合并find_autocad到共享模块 |
| ㊾ | 修复spatial_reasoning加权 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L336) | 使用权重计算 |
| ㊿ | 修复report_translator动态计算 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py#L540-577) | 从实际数据动态计算 |

---

### 第三阶段：Medium级修复（72个独立子任务）

| 序号 | 子任务 | 修改文件 | 具体操作 |
|------|--------|----------|----------|
| 51 | 修复ask_json异常 | [base_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/base_adapter.py#L92) | 缩小异常捕获范围 |
| 52 | 修复avg_latency_ms | [base_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/base_adapter.py#L118) | 缓存计算结果 |
| 53 | 修复response.usage | [text_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/text_adapter.py#L63) | 添加异常日志 |
| 54 | 修复detail参数 | [vision_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/vision_adapter.py#L112) | 配置化处理 |
| 55 | 修复fallback_chain | [llm/__init__.py](file:///f:/AI-CAD-Audit-System/v7/llm/__init__.py#L114-157) | 添加成本感知 |
| 56 | 添加注释 | [base_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/base_agent.py#L133) | 为`_TEXT_BATCH_CHARS`添加注释 |
| 57 | 修复score阈值 | [discipline_agents.py](file:///f:/AI-CAD-Audit-System/v7/agents/discipline_agents.py#L36-83) | 配置化阈值 |
| 58 | 添加异常日志 | [discipline_agents.py](file:///f:/AI-CAD-Audit-System/v7/agents/discipline_agents.py#L302) | 添加日志记录 |
| 59 | 修复截断长度 | [discipline_agents.py](file:///f:/AI-CAD-Audit-System/v7/agents/discipline_agents.py#L338) | 使用统一常量 |
| 60 | 移除未使用变量 | [chief_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/chief_agent.py#L44) | 移除`_merge_distance` |
| 61 | 修复重复检查 | [chief_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/chief_agent.py#L77-89) | 增加检查维度 |
| 62 | 添加文档 | [chief_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/chief_agent.py#L114) | 为`_SEVERITY_DOWNGRADE`添加文档 |
| 63 | 修复关键字级别 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L236-237) | 使用内容级关键字 |
| 64 | 修复参数设计 | [drawing_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_pipeline.py#L51-53) | 重命名参数 |
| 65 | 修复A0惩罚 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py#L90) | 缩小惩罚范围 |
| 66 | 修复图片读取 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py#L44) | 只读取一次 |
| 67 | 修复gc频率 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py#L119) | 降低调用频率 |
| 68 | 添加临时目录清理 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py#L80-81) | 使用`tempfile.TemporaryDirectory` |
| 69 | 修复锐化强度 | [image_enhancer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/image_enhancer.py#L21) | 降低锐化核强度 |
| 70 | 修复标签关联 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py#L226-231) | 添加X坐标约束 |
| 71 | 修复空字符串正则 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L60) | 添加空值检查 |
| 72 | 修复AutoCAD路径 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py#L17-24) | 动态获取路径 |
| 73 | 修复字体支持 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py#L187) | 使用支持中文的字体 |
| 74 | 修复python命令 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py#L254-256) | 使用`sys.executable` |
| 75 | 修复ODA路径 | [dwg_converter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_converter.py#L22-26) | 动态检测版本 |
| 76 | 修复输出版本 | [dwg_converter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_converter.py#L73-78) | 配置化处理 |
| 77 | 提取重复函数 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py#L176-250) | 提取通用方法 |
| 78 | 修复多布局复制 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py#L393-403) | 按布局复制 |
| 79 | 修复重复定义 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py#L23-34) | 移除重复定义 |
| 80 | 修复INSERT展开 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L123-158) | 完善递归逻辑 |
| 81 | 移除未使用字典 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py#L166-170) | 移除未使用索引字典 |
| 82 | 添加类型安全 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py#L228) | 添加类型检查 |
| 83 | 修复截断长度 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L111) | 使用配置常量 |
| 84 | 修复私有方法调用 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L121-126) | 改为公共接口 |
| 85 | 修复JSON异常 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L125-126) | 添加异常日志 |
| 86 | 缓存正则编译 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L138-140) | 预编译正则 |
| 87 | 修复返回数量限制 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L214) | 配置化处理 |
| 88 | 修复标高基准面 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L296-297) | 完善判断逻辑 |
| 89 | 修复时区 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L91) | 使用统一时区 |
| 90 | 设置随机种子 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L103) | 固定随机种子 |
| 91 | 添加复核日志 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L133-134) | 添加日志记录 |
| 92 | 修复缓存线程安全 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L13) | 添加锁保护 |
| 93 | 修复YAML异常 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L50-51) | 添加异常日志 |
| 94 | 移除未使用常量 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L11) | 移除`SYSTEM_BASE` |
| 95 | 修复截断长度 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L97) | 使用配置常量 |
| 96 | 提取重复函数 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L80-95) | 提取通用方法 |
| 97 | 修复时区 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py#L15) | 使用统一时区 |
| 98 | 修复评分权重 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py#L296-306) | 配置化权重 |
| 99 | 修复成本系数 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py#L340-344) | 配置化系数 |
| 100 | 修复sys.path | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py#L14) | 局部修改而非全局 |
| 101 | 修复编码回退 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py#L104) | 完善回退逻辑 |
| 102 | 移除硬编码缓存 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | 外部化缓存数据 |
| 103 | 修复margin计算 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py#L78) | 改进occupants=0时的处理 |
| 104 | 修复参数修改 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py#L428) | 返回新对象而非修改入参 |
| 105 | 修复配置加载 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L21-27) | 添加异常日志 |
| 106 | 修复hash不确定 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L257) | 使用稳定哈希 |
| 107 | 修复缓存路径 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L296) | 添加路径验证 |
| 108 | 修复print输出 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L597) | 使用logging |
| 109 | 提取重复代码 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py#L797-833) | 提取到共享模块 |
| 110 | 修复私有属性访问 | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py#L41) | 使用公共接口 |
| 111 | 修复Namespace | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py#L187-191) | 使用正确方式构造 |
| 112 | 修复私有属性访问 | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py#L206) | 使用公共接口 |
| 113 | 提取重复函数 | [conflict_diff.py](file:///f:/AI-CAD-Audit-System/v7/conflict_diff.py#L88-127) | 提取通用方法 |
| 114 | 修复竞态条件 | [conflict_state_manager.py](file:///f:/AI-CAD-Audit-System/v7/conflict_state_manager.py#L51-61) | 使用原子操作 |
| 115 | 修复回退文件名 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py#L25) | 使用动态文件名 |
| 116 | 修复报告编号 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py#L155) | 使用动态生成 |
| 117 | 修复统计数据 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py#L86-94) | 使用动态计算 |
| 118 | 修复绑定地址 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py#L278) | 配置化地址 |
| 119 | 移除未使用导入 | [launcher.py](file:///f:/AI-CAD-Audit-System/v7/launcher.py#L89) | 移除`admin_main` |
| 120 | 提取重复代码 | [generate_three_scene_reports.py](file:///f:/AI-CAD-Audit-System/v7/generate_three_scene_reports.py) | 统一到独立模块 |
| 121 | 外部化审查数据 | [uai_review_data.py](file:///f:/AI-CAD-Audit-System/v7/uai_review_data.py#L6-102) | 移到配置文件 |
| 122 | 修复JSON读取 | [secure_config.py](file:///f:/AI-CAD-Audit-System/v7/secure_config.py#L39-44) | 缓存读取结果 |

---

### 第四阶段：Low级修复（65个独立子任务）

| 序号 | 子任务 | 修改文件 | 具体操作 |
|------|--------|----------|----------|
| 123 | 移除未使用导入 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py#L13) | 移除`BoundingBox2d` |
| 124 | 移除未使用导入 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py#L19) | 移除`BoundingBox2d` |
| 125 | 移除未使用函数 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py#L124-133) | 移除`_get_frame_from_insert_bbox` |
| 126 | 移除未使用函数 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py#L348-360) | 移除`_apply_text_verification` |
| 127 | 移除未使用变量 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py#L171) | 移除`_merge_distance` |
| 128 | 移除未使用常量 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L60-62) | 移除三个正则常量 |
| 129 | 移除未使用常量 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L11) | 移除`SYSTEM_BASE` |
| 130 | 移除未使用常量 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L19-21) | 移除`RENDER_DPI`等 |
| 131 | 修复未使用参数 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L24) | 移除或使用`blocks` |
| 132 | 移除未使用变量 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py#L254) | 移除`_drawing_number_cache` |
| 133 | 修复未使用参数 | [dwg_converter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_converter.py#L157) | 移除或使用`max_workers` |
| 134 | 移除未使用导入 | [launcher.py](file:///f:/AI-CAD-Audit-System/v7/launcher.py#L89) | 移除`admin_main` |
| 135 | 修复三元表达式 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L146) | 拆分为多行 |
| 136 | 修复导入路径 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py#L338) | 使用相对导入 |
| 137 | 修复dir检查 | [base_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/base_adapter.py#L94) | 使用`hasattr()` |
| 138 | 修复类型注解 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py#L74) | `callable`→`Callable` |
| 139 | 修复导入位置 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py#L1306) | 移到文件顶部 |
| 140 | 修复单行代码 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py#L518) | 拆分为多行 |
| 141 | 修复变量名 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py#L111-113) | 使用有意义的变量名 |
| 142 | 修复f-string空格 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py#L234) | 移除多余空格 |
| 143 | 提取正则常量 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L119) | 定义`DN_PATTERN`常量 |
| 144 | 修复冗余判断 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L170) | `len(val) > 0`→`val` |
| 145 | 修复导入位置 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L56) | 移到文件顶部 |
| 146 | 修复导入位置 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L218) | 移到文件顶部 |
| 147 | 修复日志emoji | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py#L156) | 移除emoji |
| 148 | 优化排序字典 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py#L263-266) | 复用字典 |
| 149 | 优化重复调用 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py#L312-313) | 缓存结果 |
| 150 | 优化图片读取 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py#L30) | 使用`PIL.Image.open().size` |
| 151 | 优化字典创建 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py#L194) | 复用字典 |
| 152 | 优化字典创建 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py#L179-189) | 复用字典 |
| 153 | 优化MD5计算 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L101) | 分块计算 |
| 154 | 提取魔法数字 | [base_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/base_agent.py#L133) | `_TEXT_BATCH_CHARS=90000` |
| 155 | 提取魔法数字 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L111) | `TRUNCATE_LENGTH=6000` |
| 156 | 提取魔法数字 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py#L117) | `RESPONSE_TRUNCATE=500` |
| 157 | 提取魔法数字 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py#L124) | 定义常量 |
| 158 | 提取魔法数字 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py#L285) | `PASS_RATE=0.85` |
| 159 | 提取魔法数字 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py#L88) | `SAFETY_FACTOR=1.15` |
| 160 | 提取魔法数字 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py#L233) | `MAX_TEXT_ENTITIES=200` |
| 161 | 提取魔法数字 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L206) | `FONT_SIZE=14` |
| 162 | 提取魔法数字 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py#L165) | `MAX_FILE_SIZE=80*1024*1024` |
| 163 | 修复路径硬编码 | llm_full_review.py | 使用动态路径 |
| 164 | 修复路径硬编码 | spatial_reasoning.py | 使用动态路径 |
| 165 | 修复路径硬编码 | generate_three_scene_reports.py | 使用动态路径 |
| 166 | 修复路径硬编码 | drawing_pipeline.py | 使用动态路径 |
| 167 | 修复路径硬编码 | dwg_converter.py | 使用动态路径 |
| 168 | 修复路径硬编码 | cad_printer.py | 使用动态路径 |
| 169 | 修复代码重复 | unified_pipeline.py vs spatial_reasoning.py | 提取共享模块 |
| 170 | 修复代码重复 | generate_three_scene_reports.py vs llm_full_review.py | 统一模块 |
| 171 | 修复代码重复 | dwg_converter.py vs cad_printer.py | 合并函数 |
| 172 | 修复代码重复 | prompt_templates.py | 提取通用方法 |
| 173 | 移除pickle使用 | spatial_reasoning.py | 使用json |
| 174 | 移除pickle使用 | unified_pipeline.py | 使用json |
| 175 | 修复异常吞没 | base_adapter.py | 添加日志 |
| 176 | 修复异常吞没 | text_adapter.py | 添加日志 |
| 177 | 修复异常吞没 | drawing_scanner.py | 添加日志 |
| 178 | 修复异常吞没 | prompt_templates.py | 添加日志 |
| 179 | 修复异常吞没 | spatial_reasoning.py | 添加日志 |
| 180 | 修复异常吞没 | false_negative_auditor.py | 添加日志 |
| 181 | 修复异常吞没 | discipline_agents.py | 添加日志 |
| 182 | 修复异常吞没 | conflict_state_manager.py | 添加日志 |
| 183 | 修复时区不一致 | false_negative_auditor.py | 统一时区 |
| 184 | 修复时区不一致 | role_report_generator.py | 统一时区 |
| 185 | 修复时区不一致 | llm_full_review.py | 统一时区 |
| 186 | 修复硬编码统计 | report_translator.py | 动态计算 |
| 187 | 修复硬编码统计 | server.py | 动态计算 |
| 188 | 修复硬编码统计 | role_report_generator.py | 动态计算 |
| 189 | 修复sys.path修改 | llm_full_review.py | 局部修改 |
| 190 | 修复sys.path修改 | base_adapter.py | 局部修改 |
| 191 | 修复sys.path修改 | launcher.py | 局部修改 |
| 192 | 添加缓存限制 | drawing_extractor.py | 使用lru_cache |
| 193 | 添加缓存限制 | drawing_scanner.py | 使用lru_cache |

---

### 第五阶段：架构改进（6个独立子任务）

| 序号 | 子任务 | 关联模块 | 具体操作 |
|------|--------|----------|----------|
| 194 | 实现项目参数锚定 | [project_parameter_anchor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/project_parameter_anchor.py) | 完善参数提取规则库 |
| 195 | 完善空间索引 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | 建立五级空间索引 |
| 196 | 实现问题生命周期 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | 添加状态流转逻辑 |
| 197 | 建设验收知识库 | checkpoints/definitions/ | 创建验收标准YAML文件 |
| 198 | 实现整改建议数值化 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py) | 添加多方案比选 |
| 199 | 实现历史对比 | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py) | 添加版本差异分析 |

---

## Critical级问题（必须立即修复）

| ID | 问题描述 | 文件 | 行号 | 修复方案 |
|----|---------|------|------|---------|
| C-01 | 标准化检查器正则表达式错误：`\|`应为`|` | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L99 | 改为`r"抗震等级|抗震构造|抗震措施"` |
| C-02 | 图框拆分后渲染完整图纸而非子图 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py) | L121-133 | render_dxf_pil需传入裁剪参数 |
| C-03 | 空间分析使用全局bounds导致假阳性 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L182-184 | 改为`src_idx.bounds(src_eid)` |
| C-04 | DXF冲突标记绘制在坐标原点 | [dxf_marker.py](file:///f:/AI-CAD-Audit-System/v7/dxf_marker.py) | L77 | 从冲突数据提取坐标 |
| C-05 | Excel报告列数超过26时崩溃 | [excel_reporter.py](file:///f:/AI-CAD-Audit-System/v7/excel_reporter.py) | L74 | 使用`openpyxl.utils.get_column_letter()` |
| C-06 | pickle反序列化安全漏洞 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py), [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py) | L6, L64-65 | 替换为json/msgpack |
| C-07 | API密钥Linux上空字符串加密 | [secure_config.py](file:///f:/AI-CAD-Audit-System/v7/secure_config.py) | L28-29 | 无环境变量时拒绝运行 |
| C-08 | HTTP服务器无请求体大小限制 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py) | L231-232 | 添加10MB限制 |
| C-09 | 硬编码Windows个人路径 | llm_full_review.py, spatial_reasoning.py, generate_three_scene_reports.py, drawing_pipeline.py, dwg_converter.py | 多处 | 使用动态路径获取 |
| C-10 | 报告翻译器统计数字硬编码 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py) | L540-577 | 从实际数据动态计算 |
| C-11 | 合理性引擎加权计算未使用权重 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py) | L336 | 使用权重计算 |
| C-12 | HTTP服务器路径遍历漏洞 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py) | L222-228 | 使用`os.path.realpath()`验证 |

---

## High级问题（应尽快修复）

| ID | 问题描述 | 文件 | 行号 | 修复方案 |
|----|---------|------|------|---------|
| H-01 | 标准化检查器字符类误用`\|` | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L48,68,74 | `[Cc]`替代`[C\|c]` |
| H-02 | 标准化检查器搜索范围为全文而非组件上下文 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L271-273 | 限定搜索范围 |
| H-03 | 图纸分类器关键字冲突 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L63-88 | 添加优先级机制 |
| H-04 | 楼层提取返回正则模式而非匹配内容 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L362 | 返回`match.group(0)` |
| H-05 | 楼层提取返回正则模式而非匹配内容(重复) | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L362 | 返回`match.group(0)` |
| H-06 | drawing_pipeline detector变量可能未定义 | [drawing_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_pipeline.py) | L246 | 统一初始化 |
| H-07 | title_block_extractor pop修改原始数据 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py) | L451,491 | 使用`get()`替代`pop()` |
| H-08 | ELLIPSE bbox计算使用错误短轴长度 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py) | L105-108 | 使用模长 |
| H-09 | rtree功能声明但未实现 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py) | L76-83 | 实现或移除 |
| H-10 | ARC角度坐标系转换不完整 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L258-260 | 实现完整转换 |
| H-11 | problem_pool professional字段被赋值为severity | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | L183 | 改为`discipline` |
| H-12 | 扫描失败时risk_level默认为medium | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L148-151 | 改为`high` |
| H-13 | 轴网一致性检查仅检查X方向 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L204 | 添加Y方向检查 |
| H-14 | 标高值过滤逻辑中正号未被处理 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L291-292 | 使用`try/except float()` |
| H-15 | 假阴性审计运算符优先级错误 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L119-121 | 拆分为多行 |
| H-16 | 假阴性审计verdict字段不存在 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L165-169 | 添加或检查其他字段 |
| H-17 | pickle反序列化安全风险 | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py) | L64-65,94 | 替换为json |
| H-18 | 空间分析全量扫描实体列表 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L635-638 | 建立分类索引 |
| H-19 | 合理性引擎加权计算未使用权重(重复) | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py) | L336 | 使用权重计算 |
| H-20 | 代码大量重复 | unified_pipeline.py vs spatial_reasoning.py | 多处 | 提取到共享模块 |
| H-21 | 报告翻译器统计数字硬编码(重复) | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py) | L540-577 | 动态计算 |
| H-22 | 报告翻译器极度压缩的单行代码 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py) | L518 | 使用正常多行代码 |
| H-23 | API密钥无加密库时明文存储 | [secure_config.py](file:///f:/AI-CAD-Audit-System/v7/secure_config.py) | L92-94,113-114 | 拒绝存储或警告 |
| H-24 | HTTP服务器CORS允许所有来源 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py) | L115 | 限制为特定域名 |
| H-25 | launcher中server变量可能未定义 | [launcher.py](file:///f:/AI-CAD-Audit-System/v7/launcher.py) | L98 | 初始化为None并检查 |
| H-26 | 场景报告生成逻辑重复 | generate_three_scene_reports.py vs llm_full_review.py | 多处 | 统一到独立模块 |
| H-27 | 冲突状态管理器O(N*M)性能问题 | [conflict_state_manager.py](file:///f:/AI-CAD-Audit-System/v7/conflict_state_manager.py) | L176-177 | 循环外计算cur_keys |
| H-28 | MTEXT换行符处理错误 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L291 | 移除`.replace("\\p", "\n")` |
| H-29 | MTEXT文本提取使用错误属性 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L289 | 改为`e.plain_text()` |
| H-30 | find_autocad函数重复 | dwg_converter.py vs cad_printer.py | 多处 | 合并到共享模块 |
| H-31 | 框架检测器A0前缀匹配过于宽泛 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py) | L90 | 使用精确匹配 |
| H-32 | 图纸分类器max结果不确定 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L209 | 添加确定性排序 |
| H-33 | 缓存字典无大小限制导致内存泄漏 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py), [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L111, L91 | 使用`lru_cache` |
| H-34 | 缓存键中os.path.getsize未处理文件不存在 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L126 | 添加exists检查 |
| H-35 | openpyxl引擎硬编码且无异常处理 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py) | L483 | 添加导入检查 |
| H-36 | columns过滤后可能为空列表 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py) | L479 | 添加空列表检查 |
| H-37 | deepcopy对ezdxf实体可能不完整 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py) | L232,298 | 使用ezdxf复制方法 |
| H-38 | IMAGE实体bbox计算不完整 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py) | L130-131 | 使用`get_bbox()` |

---

## Medium级问题（应计划修复）

### v7/llm/模块
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-01 | `ask_json`异常处理过于宽泛 | [base_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/base_adapter.py) | L92 |
| M-02 | `avg_latency_ms`每次调用重新计算 | [base_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/base_adapter.py) | L118 |
| M-03 | `response.usage`异常被静默吞掉 | [text_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/text_adapter.py) | L63 |
| M-04 | 图片detail硬编码为`"high"` | [vision_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/vision_adapter.py) | L112 |
| M-05 | fallback_chain顺序遍历无成本感知 | [__init__.py](file:///f:/AI-CAD-Audit-System/v7/llm/__init__.py) | L114-157 |

### v7/agents/模块
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-06 | `_TEXT_BATCH_CHARS`无注释 | [base_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/base_agent.py) | L133 |
| M-07 | `score >= 2`阈值硬编码 | [discipline_agents.py](file:///f:/AI-CAD-Audit-System/v7/agents/discipline_agents.py) | L36-83 |
| M-08 | `except Exception`无日志 | [discipline_agents.py](file:///f:/AI-CAD-Audit-System/v7/agents/discipline_agents.py) | L302 |
| M-09 | `merged_text[:8000]`截断长度不一致 | [discipline_agents.py](file:///f:/AI-CAD-Audit-System/v7/agents/discipline_agents.py) | L338 |
| M-10 | `_merge_distance`声明未使用 | [chief_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/chief_agent.py) | L44 |
| M-11 | `_is_duplicate`仅检查`cad_coords` | [chief_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/chief_agent.py) | L77-89 |
| M-12 | `_SEVERITY_DOWNGRADE`无文档 | [chief_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/chief_agent.py) | L114 |

### v7/preprocessor/模块
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-13 | 使用文件名级关键字而非内容级关键字 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L236-237 |
| M-14 | `--text-verify`参数设计易混淆 | [drawing_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_pipeline.py) | L51-53 |
| M-15 | A0前缀惩罚逻辑过于宽泛 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py) | L90 |
| M-16 | 同一图片被读取两次 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py) | L44 |
| M-17 | `gc.collect()`频率过高 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py) | L119 |
| M-18 | 临时目录从未自动清理 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py) | L80-81 |
| M-19 | 锐化核强度过大 | [image_enhancer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/image_enhancer.py) | L21 |
| M-20 | 标签和值的关联仅基于Y坐标 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py) | L226-231 |
| M-21 | 空字符串正则匹配所有文本 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L60 |
| M-22 | AutoCAD路径硬编码 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py) | L17-24 |
| M-23 | 默认字体不支持中文 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py) | L187 |
| M-24 | 硬编码`python`命令 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py) | L254-256 |
| M-25 | ODA路径硬编码版本号 | [dwg_converter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_converter.py) | L22-26 |
| M-26 | 输出版本硬编码为ACAD2013 | [dwg_converter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_converter.py) | L73-78 |
| M-27 | 多个`_copy_*_defs`函数结构相同 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py) | L176-250 |
| M-28 | 多布局文件复制全部模型空间 | [dwg_subset_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_subset_splitter.py) | L393-403 |
| M-29 | `STANDARD_FRAMES`重复定义 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py) | L23-34 |
| M-30 | INSERT递归展开上限可能不完整 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L123-158 |

### v7/problem_pool/, scanner/, cross_drawing/, audit/
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-31 | 三个索引字典声明但从未使用 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | L166-170 |
| M-32 | 直接访问`text_entity.x/y/z`无类型安全 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | L228 |
| M-33 | 硬编码截断长度6000字符 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L111 |
| M-34 | 调用私有方法`_extract_json` | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L121-126 |
| M-35 | JSON解析异常被完全吞掉 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L125-126 |
| M-36 | 正则表达式每次调用重新编译 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L138-140 |
| M-37 | 所有检查方法硬编码最多返回5个问题 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L214,240,262,283,308,326 |
| M-38 | 标高基准面判断过于简单 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L296-297 |
| M-39 | 时区不一致 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L91 |
| M-40 | 随机抽样无种子 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L103 |
| M-41 | 复核异常仅记录无日志 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L133-134 |

### v7/checkpoints/templates/
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-42 | 模块级缓存多线程不安全 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L13 |
| M-43 | YAML加载失败异常被吞掉 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L50-51 |
| M-44 | `SYSTEM_BASE`常量未使用 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L11 |
| M-45 | 截断长度90000硬编码 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L97 |
| M-46 | `build_text_prompt`和`build_vision_prompt`重复 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L80-95 |

### v7/report_v7/
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-47 | 时区不一致 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py) | L15 |
| M-48 | 风险评分权重和阈值硬编码 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py) | L296-306 |
| M-49 | 成本估算系数硬编码 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py) | L340-344 |

### v7/根目录
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| M-50 | 模块级修改sys.path | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | L14 |
| M-51 | 文件编码回退逻辑不完整 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | L104 |
| M-52 | 缓存数据硬编码在源码中 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | 全文 |
| M-53 | `occupants=0`时`margin=0`可能误导 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py) | L78 |
| M-54 | `annotate_all_rationality`直接修改传入参数 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py) | L428 |
| M-55 | 配置文件加载异常被静默吞掉 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L21-27 |
| M-56 | Python`hash()`跨进程不确定 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L257 |
| M-57 | 缓存目录路径遍历风险 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L296 |
| M-58 | 使用`print`输出进度 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L597 |
| M-59 | rtree和非rtree版本重复代码 | [spatial_reasoning.py](file:///f:/AI-CAD-Audit-System/v7/spatial_reasoning.py) | L797-833 |
| M-60 | 直接访问私有属性`_cache_dir` | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py) | L41 |
| M-61 | 手动构造`argparse.Namespace` | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py) | L187-191 |
| M-62 | 访问私有属性`_issues` | [unified_pipeline.py](file:///f:/AI-CAD-Audit-System/v7/unified_pipeline.py) | L206 |
| M-63 | `mark_waived`和`mark_resolved`结构相同 | [conflict_diff.py](file:///f:/AI-CAD-Audit-System/v7/conflict_diff.py) | L88-127 |
| M-64 | TOCTOU竞态条件 | [conflict_state_manager.py](file:///f:/AI-CAD-Audit-System/v7/conflict_state_manager.py) | L51-61 |
| M-65 | 硬编码回退文件名包含日期 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py) | L25 |
| M-66 | 报告编号和日期硬编码 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py) | L155,168,519,526 |
| M-67 | 统计数据硬编码 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py) | L86-94 |
| M-68 | 绑定到所有网络接口 | [server.py](file:///f:/AI-CAD-Audit-System/v7/server.py) | L278 |
| M-69 | `admin_main`导入未使用 | [launcher.py](file:///f:/AI-CAD-Audit-System/v7/launcher.py) | L89 |
| M-70 | 与llm_full_review.py重复 | [generate_three_scene_reports.py](file:///f:/AI-CAD-Audit-System/v7/generate_three_scene_reports.py) | 全文 |
| M-71 | 145条审查数据硬编码 | [uai_review_data.py](file:///f:/AI-CAD-Audit-System/v7/uai_review_data.py) | L6-102 |
| M-72 | 每次调用重新读取JSON文件 | [secure_config.py](file:///f:/AI-CAD-Audit-System/v7/secure_config.py) | L39-44 |

---

## Low级问题（可择机修复）

### 死代码/未使用
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| L-01 | `BoundingBox2d`导入未使用 | [frame_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/frame_splitter.py) | L13 |
| L-02 | `BoundingBox2d`导入未使用 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py) | L19 |
| L-03 | `_get_frame_from_insert_bbox`定义未调用 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py) | L124-133 |
| L-04 | `_apply_text_verification`未被调用 | [enhanced_frame_detector.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/enhanced_frame_detector.py) | L348-360 |
| L-05 | `_merge_distance`声明未使用 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | L171 |
| L-06 | 三个正则常量定义未使用 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L60-62 |
| L-07 | `SYSTEM_BASE`常量未使用 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L11 |
| L-08 | `RENDER_DPI`等常量未使用 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L19-21 |
| L-09 | `blocks`参数未使用 | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L24 |
| L-10 | `_drawing_number_cache`声明未使用 | [title_block_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/title_block_extractor.py) | L254 |
| L-11 | `max_workers`参数声明未使用 | [dwg_converter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/dwg_converter.py) | L157 |
| L-12 | `admin_main`导入未使用 | [launcher.py](file:///f:/AI-CAD-Audit-System/v7/launcher.py) | L89 |

### 代码风格/可读性
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| L-13 | 嵌套三元表达式可读性差 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L146 |
| L-14 | 同一文件内使用绝对路径导入自身 | [drawing_extractor.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/drawing_extractor.py) | L338 |
| L-15 | `'raw' in dir()`检查不可靠 | [base_adapter.py](file:///f:/AI-CAD-Audit-System/v7/llm/base_adapter.py) | L94 |
| L-16 | 类型注解使用小写`callable` | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | L74 |
| L-17 | 函数内部导入标准库 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | L1306 |
| L-18 | 极度压缩的单行代码 | [report_translator.py](file:///f:/AI-CAD-Audit-System/v7/report_translator.py) | L518 |
| L-19 | 变量名`_`过于隐晦 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py) | L111-113 |
| L-20 | f-string中多余空格 | [cross_context.py](file:///f:/AI-CAD-Audit-System/v7/cross_drawing/cross_context.py) | L234 |
| L-21 | `DN\d+`重复出现 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L119 |
| L-22 | `len(val) > 0`与`val`冗余 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L170 |
| L-23 | 循环内部导入`math` | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L56,135 |
| L-24 | 函数内部导入`os` | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L218 |
| L-25 | 日志中使用emoji字符 | [false_negative_auditor.py](file:///f:/AI-CAD-Audit-System/v7/audit/false_negative_auditor.py) | L156 |

### 性能（轻微）
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| L-26 | 每次排序创建新字典字面量 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | L263-266 |
| L-27 | `count_dual_verified()`被调用两次 | [pool.py](file:///f:/AI-CAD-Audit-System/v7/problem_pool/pool.py) | L312-313 |
| L-28 | 读取图片后立即丢弃仅获取尺寸 | [grid_splitter.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/grid_splitter.py) | L30 |
| L-29 | 循环内每次创建固定字典 | [role_report_generator.py](file:///f:/AI-CAD-Audit-System/v7/report_v7/role_report_generator.py) | L194 |
| L-30 | 每次调用创建新字典 | [prompt_templates.py](file:///f:/AI-CAD-Audit-System/v7/checkpoints/templates/prompt_templates.py) | L179-189 |
| L-31 | MD5对超大文本消耗内存 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L101 |

### 魔法数字/硬编码
| ID | 问题描述 | 文件 | 行号 |
|----|---------|------|------|
| L-32 | `_TEXT_BATCH_CHARS = 90000` | [base_agent.py](file:///f:/AI-CAD-Audit-System/v7/agents/base_agent.py) | L133 |
| L-33 | 截断长度6000 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L111 |
| L-34 | 原始响应截断500字符 | [drawing_scanner.py](file:///f:/AI-CAD-Audit-System/v7/scanner/drawing_scanner.py) | L117 |
| L-35 | 截断长度80000/30000 | [llm_full_review.py](file:///f:/AI-CAD-Audit-System/v7/llm_full_review.py) | L124,156 |
| L-36 | 85%通过率阈值 | [standardization_checker.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/standardization_checker.py) | L285 |
| L-37 | 魔法数字1.15和100 | [rationality_engine.py](file:///f:/AI-CAD-Audit-System/v7/rationality_engine.py) | L88 |
| L-38 | 截取200个文本实体 | [cad_printer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/cad_printer.py) | L233 |
| L-39 | 字体大小硬编码14px | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L206 |
| L-40 | 文件大小阈值80MB | [pil_renderer.py](file:///f:/AI-CAD-Audit-System/v7/preprocessor/pil_renderer.py) | L165 |

### 跨文件系统性问题
| ID | 问题描述 | 涉及文件 |
|----|---------|---------|
| L-41 | Windows路径硬编码 | 6个文件 |
| L-42 | 代码重复 | 4组 |
| L-43 | pickle使用 | 2个文件 |
| L-44 | 异常吞没 | 8处 |
| L-45 | 时区不一致 | 3个文件 |
| L-46 | 硬编码统计数字 | 3个文件 |
| L-47 | sys.path全局修改 | 3个文件 |
| L-48 | 缓存无大小限制 | 3个文件 |
| L-49 | 配置分散 | 3个位置 |
| L-50 | 类型注解缺失 | 绝大多数文件 |

### 剩余Low级问题
| ID | 问题描述 |
|----|---------|
| L-51 | 代码风格统一 |
| L-52 | 魔法数字提取为常量 |
| L-53 | 性能微优化 |
| L-54 | 死代码清理 |
| L-55 | 异常处理规范化 |

---

## 架构层面改进（基于「几个模型的审核意见.txt」）

| ID | 优先级 | 改进项 | 预期收益 | 关联模块 |
|----|--------|--------|----------|---------|
| A-01 | **P0** | 新增项目参数锚定环节 | 消除大量误报，建立审查基准 | preprocessor/project_parameter_anchor.py |
| A-02 | **P0** | 完善空间索引（楼栋→楼层→专业→构件） | 问题精准定位到具体楼层/位置 | spatial_reasoning.py, problem_pool/pool.py |
| A-03 | **P1** | 问题生命周期管理（发现→整改→复核→关闭） | 形成完整工作闭环 | problem_pool/pool.py, conflict_state_manager.py |
| A-04 | **P1** | 验收测试知识库建设 | 填补L2-L3维度缺口（施工可行性、验收路径） | checkpoints/definitions/ |
| A-05 | **P2** | 整改建议数值化 | 从"发现问题"到"解决问题"，提供具体数值方案 | report_v7/role_report_generator.py |
| A-06 | **P2** | 历史项目对比功能 | 知识持续积累，支持版本差异分析 | unified_pipeline.py |

### 架构改进说明

**A-01 项目参数锚定环节**
- 从DXF图框自动提取关键建筑参数（高度、层数、耐火等级、抗震设防等）
- 建立参数交叉验证机制，确保数据一致性
- 为后续审查提供可靠的基准数据

**A-02 空间索引完善**
- 建立「项目→楼栋→楼层→专业→构件」五级空间索引
- 支持问题精准定位到具体楼层和轴线位置
- 提升碰撞检测的空间精度

**A-03 问题生命周期管理**
- 实现问题状态流转：发现→待整改→整改中→已复核→已关闭
- 支持整改依赖关系标注（如：建筑参数修改触发结构/机电联动修改）
- 提供整改优先级排序功能

**A-04 验收测试知识库**
- 建立施工工艺知识库（材料规格、加工能力、安装空间）
- 建立验收标准知识库（测试方法、合格标准）
- 建立运维要求知识库（检修空间、维护通道）

**A-05 整改建议数值化**
- 输出规范要求值、现状值对比
- 提供多方案比选（成本、工期影响评估）
- 给出推荐整改方案

**A-06 历史项目对比**
- 支持本次审查与历史版本的差异分析
- 识别新增问题和已解决问题
- 支持趋势分析和质量追踪

---

## 修复优先级路线图

### 第一阶段：Critical修复（1-2天）
1. C-01 ~ C-02: 标准化检查器正则修复 + 图框拆分渲染修复
2. C-03: 空间分析bounds修复
3. C-04: DXF标记坐标修复
4. C-06 ~ C-08: pickle替换 + 密钥安全 + HTTP安全
5. C-09: Windows路径清理
6. C-11 ~ C-12: 合理性引擎 + 路径遍历修复

### 第二阶段：High修复（3-5天）
1. H-01 ~ H-02: 标准化检查器剩余问题
2. H-11 ~ H-16: 问题池 + 扫描器 + 跨图纸分析修复
3. H-17 ~ H-20: 安全 + 性能修复
4. H-26 ~ H-30: 代码重复消除

### 第三阶段：Medium修复（1-2周）
1. 异常处理规范化
2. 缓存机制完善
3. 配置统一管理
4. 类型注解补全

### 第四阶段：Low修复（持续）
1. 死代码清理
2. 代码风格统一
3. 魔法数字提取为常量
4. 性能微优化

---

## 问题统计汇总

| 优先级 | 数量 | 占比 |
|--------|------|------|
| Critical | 12 | 6.2% |
| High | 38 | 19.7% |
| Medium | 72 | 37.3% |
| Low | 65 | 33.7% |
| **架构改进** | **6** | **3.1%** |
| **合计** | **193** | **100%** |

---

> **数据来源**：
> - CODE_IMPROVEMENT_ANALYSIS.md：187个代码级问题
> - 几个模型的审核意见.txt：6个架构层面改进项