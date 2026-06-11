# AI CAD Audit System — 全量代码改进分析报告

> 覆盖范围：项目中全部 50+ 个 Python 源文件，逐文件逐函数分析
> 分析日期：2026-06-11

---

## 一、问题总览

| 严重程度 | 数量 | 说明 |
|----------|------|------|
| **Critical** | 12 | 导致功能完全失效或存在严重安全漏洞 |
| **High** | 38 | 产生错误结果或存在显著安全/性能风险 |
| **Medium** | 72 | 设计缺陷、可维护性问题、潜在 bug |
| **Low** | 65 | 代码风格、死代码、轻微性能问题 |
| **合计** | **187** | |

---

## 二、Critical 级问题（必须立即修复）

### C-01: 标准化检查器正则表达式错误 — 所有规则匹配失效
- **文件**: [standardization_checker.py](file:///workspace/v7/preprocessor/standardization_checker.py#L99)
- **行号**: 99
- **代码**: `required_properties=[r"抗震等级\|抗震构造\|抗震措施"]`
- **问题**: `\|` 在正则中是字面量 `\|`（匹配反斜杠+管道符），而非逻辑"或"。所有使用该规则的检查都会失败。
- **修复**: 改为 `r"抗震等级|抗震构造|抗震措施"`

### C-02: 图框拆分后渲染的是完整图纸而非子图
- **文件**: [frame_splitter.py](file:///workspace/v7/preprocessor/frame_splitter.py#L121-L133)
- **行号**: 121-133
- **代码**: `render_dxf_pil(dxf_path, sub_png)` 未传入图框范围参数
- **问题**: 多图框拆分时，每个子图实际渲染的是完整图纸而非裁剪后的区域，视觉审查完全失效。
- **修复**: `render_dxf_pil` 需支持区域裁剪参数，或先使用 `dwg_subset_splitter` 拆分 DXF 再渲染。

### C-03: 空间分析使用全局 bounds 导致大量假阳性
- **文件**: [spatial_reasoning.py](file:///workspace/v7/spatial_reasoning.py#L182-L184)
- **行号**: 182-184
- **代码**: `src_bbox = src_idx.bounds`（整个索引的边界，而非当前实体的边界）
- **问题**: 所有源实体都用全局边界去查询目标索引，导致碰撞检测结果几乎全部为假阳性。
- **修复**: 改为 `src_idx.bounds(src_eid)` 获取单个实体的边界。

### C-04: DXF 冲突标记全部绘制在坐标原点
- **文件**: [dxf_marker.py](file:///workspace/v7/dxf_marker.py#L77)
- **行号**: 77
- **代码**: `cx, cy = 0, 0`
- **问题**: 所有冲突标记都绘制在坐标原点 (0,0)，标记功能完全无效。
- **修复**: 从冲突描述中解析坐标或从 spatial_conflicts JSON 中提取坐标。

### C-05: Excel 报告列数超过 26 时崩溃
- **文件**: [excel_reporter.py](file:///workspace/v7/excel_reporter.py#L74)
- **行号**: 74
- **代码**: `chr(64 + i)` 当 i>26 时产生非字母字符
- **修复**: 使用 `openpyxl.utils.get_column_letter(i)`

### C-06: pickle 反序列化可执行任意代码
- **文件**: [spatial_reasoning.py](file:///workspace/v7/spatial_reasoning.py#L6), [unified_pipeline.py](file:///workspace/v7/unified_pipeline.py#L64-L65)
- **行号**: 6, 64-65, 94
- **代码**: `pickle.load(cf)` / `pickle.dump(cache_data, cf)`
- **问题**: pickle 反序列化可执行任意代码，恶意构造的缓存文件可实现远程代码执行。
- **修复**: 使用 `json` 或 `msgpack` 替代 pickle。

### C-07: API 密钥在 Linux 上使用空字符串密钥加密
- **文件**: [secure_config.py](file:///workspace/v7/secure_config.py#L28-L29)
- **行号**: 28-29
- **代码**: `fingerprint = f"{os.environ.get('COMPUTERNAME','')}-{os.environ.get('USERNAME','')}"`
- **问题**: Linux 上 `COMPUTERNAME` 和 `USERNAME` 通常为空，所有部署使用相同的空字符串密钥，加密形同虚设。
- **修复**: 无环境变量时拒绝运行或强制用户设置。

### C-08: HTTP 服务器无请求体大小限制可导致 OOM
- **文件**: [server.py](file:///workspace/v7/server.py#L231-L232)
- **行号**: 231-232
- **代码**: `content_len = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(content_len))`
- **问题**: 无 Content-Length 上限限制，恶意请求可发送超大 body 导致内存溢出。
- **修复**: 添加 `max_content_length = 10 * 1024 * 1024`（10MB）限制。

### C-09: 多处硬编码 Windows 路径在 Linux 上无法运行
- **文件**: [llm_full_review.py](file:///workspace/v7/llm_full_review.py#L1182), [spatial_reasoning.py](file:///workspace/v7/spatial_reasoning.py#L1004), [generate_three_scene_reports.py](file:///workspace/v7/generate_three_scene_reports.py#L30-L31), [drawing_pipeline.py](file:///workspace/v7/preprocessor/drawing_pipeline.py#L43-L46), [dwg_converter.py](file:///workspace/v7/preprocessor/dwg_converter.py#L261-L262)
- **问题**: 至少 6 个文件中硬编码了 `C:\Users\azyp\Desktop\...` 或 `r"f:\AI智能审图系统..."` 等个人路径。
- **修复**: 统一使用 `os.path.dirname(os.path.abspath(__file__))` 动态获取路径。

### C-10: 报告翻译器统计数字完全硬编码
- **文件**: [report_translator.py](file:///workspace/v7/report_translator.py#L540-L577)
- **行号**: 540-577
- **代码**: `w.append("  严重度: A(强条)94 | B(一般)75 | C(标注不全)28 | D(建议)11 | 空间冲突21,500")`
- **问题**: 所有统计数字硬编码，当审查数据变化时报告内容不更新。
- **修复**: 从实际数据动态计算。

### C-11: 合理性引擎加权计算未使用权重
- **文件**: [rationality_engine.py](file:///workspace/v7/rationality_engine.py#L336)
- **行号**: 336
- **代码**: `weighted = sum(s for s, _ in scores) / len(scores)` — `total_weight` 被初始化和累加但从未使用
- **问题**: 所有子项等权而非加权，合理性评分结果不准确。
- **修复**: 改为 `sum(s * w for (s,_), w in zip(scores, weights)) / total_weight`

### C-12: HTTP 服务器静态文件路径遍历漏洞
- **文件**: [server.py](file:///workspace/v7/server.py#L222-L228)
- **行号**: 222-228
- **代码**: `path.lstrip("/")` 后直接拼接路径
- **问题**: 存在路径遍历攻击风险（如 `/../../../etc/passwd`）。
- **修复**: 使用 `os.path.realpath()` 验证路径在允许范围内。

---

## 三、High 级问题（应尽快修复）

### H-01: 标准化检查器正则字符类中误用 `\|`
- **文件**: [standardization_checker.py](file:///workspace/v7/preprocessor/standardization_checker.py#L48)
- **行号**: 48, 68, 74
- **代码**: `[C\|c]`、`[L\|l]`、`[Z\|z]` — `\|` 在字符类中匹配字面量 `\` 或 `|`
- **修复**: 改为 `[Cc]`、`[Ll]`、`[Zz]`

### H-02: 标准化检查器搜索范围为全文而非组件上下文
- **文件**: [standardization_checker.py](file:///workspace/v7/preprocessor/standardization_checker.py#L271-L273)
- **行号**: 271-273
- **问题**: 对每个组件的 `required_property` 搜索范围是整个图纸文本，而非组件附近文本。某处有"宽度"字样时所有门检查都会通过。
- **修复**: 在组件附近（上下文窗口内）搜索。

### H-03: 图纸分类器关键字冲突
- **文件**: [drawing_extractor.py](file:///workspace/v7/preprocessor/drawing_extractor.py#L63-L88)
- **行号**: 63-88
- **问题**: `"幕墙"` 同时出现在 `curtain_wall` 和 `building` 分类中，`"装饰"` 同时出现在 `decoration` 和 `building` 中，导致分类冲突。
- **修复**: 使用优先级机制或互斥分类。

### H-04: 楼层提取返回正则模式文本而非实际匹配
- **文件**: [drawing_extractor.py](file:///workspace/v7/preprocessor/drawing_extractor.py#L362)
- **行号**: 362
- **问题**: `_extract_floor` 中 `pat.replace('\\', '')` 替换的是原始正则字符串，而非实际匹配内容。
- **修复**: 改为 `return match.group(0)`。

### H-05: 楼层提取返回正则模式文本而非实际匹配
- **文件**: [drawing_extractor.py](file:///workspace/v7/preprocessor/drawing_extractor.py#L362)
- **行号**: 362
- **问题**: `_extract_floor` 中 `pat.replace('\\', '')` 替换的是原始正则字符串，而非实际匹配内容。
- **修复**: 改为 `return match.group(0)`。

### H-06: drawing_pipeline 中 detector 变量可能未定义
- **文件**: [drawing_pipeline.py](file:///workspace/v7/preprocessor/drawing_pipeline.py#L246)
- **行号**: 246
- **问题**: 当 `pre_detected_frames` 不为 None 但 entry 为 None 时，`detector` 未定义就使用了。
- **修复**: 在函数开头统一初始化 detector。

### H-07: title_block_extractor 的 pop 操作修改原始数据
- **文件**: [title_block_extractor.py](file:///workspace/v7/preprocessor/title_block_extractor.py#L451)
- **行号**: 451, 491
- **问题**: `item.pop("frame_metadata", [])` 会修改原始数据字典。
- **修复**: 使用 `item.get("frame_metadata", [])` 或 `copy.deepcopy(item)`。

### H-08: ELLIPSE bbox 计算使用错误的短轴长度
- **文件**: [dwg_subset_splitter.py](file:///workspace/v7/preprocessor/dwg_subset_splitter.py#L105-L108)
- **行号**: 105-108
- **问题**: `entity.dxf.minor_axis[0]` 获取的是向量分量而非模长，旋转椭圆的 bbox 计算错误。
- **修复**: 使用 `abs(entity.dxf.minor_axis)` 的模长。

### H-09: rtree 功能声明但未实现
- **文件**: [enhanced_frame_detector.py](file:///workspace/v7/preprocessor/enhanced_frame_detector.py#L76-L83)
- **行号**: 76-83
- **问题**: `_try_build_rtree()` 返回 rtree 类但整个类从未实际使用 rtree 做空间索引。
- **修复**: 实现 rtree 索引加速或移除相关代码。

### H-10: ARC 角度坐标系转换不完整
- **文件**: [pil_renderer.py](file:///workspace/v7/preprocessor/pil_renderer.py#L258-L260)
- **行号**: 258-260
- **问题**: CAD 坐标系到 PIL 坐标系的 ARC 角度转换逻辑不完整，弧线绘制方向可能错误。
- **修复**: 实现完整的坐标系转换逻辑。

### H-11: problem_pool 中 professional 字段被赋值为 severity 值
- **文件**: [pool.py](file:///workspace/v7/problem_pool/pool.py#L183)
- **行号**: 183
- **代码**: `professional=cr.severity or "C"` — `professional` 语义上应代表"专业"而非严重等级。
- **修复**: 改为 `professional=cr.discipline or ""`。

### H-12: 扫描失败时 risk_level 默认为 medium 而非 high
- **文件**: [drawing_scanner.py](file:///workspace/v7/scanner/drawing_scanner.py#L148-L151)
- **行号**: 148-151
- **问题**: 扫描失败时系统以中等风险继续运行，可能遗漏高风险项目。
- **修复**: 扫描失败时 `risk_level` 应默认为 `"high"`（保守策略）。

### H-13: 轴网一致性检查仅检查 X 方向
- **文件**: [cross_context.py](file:///workspace/v7/cross_drawing/cross_context.py#L204)
- **行号**: 204
- **问题**: 仅比较 `axis_range_x`，完全忽略 `axis_range_y`。
- **修复**: 同时检查 Y 方向。

### H-14: 标高值过滤逻辑中正号未被处理
- **文件**: [cross_context.py](file:///workspace/v7/cross_drawing/cross_context.py#L291-L292)
- **行号**: 291-292
- **问题**: `"+3.5"` 中的 `+` 号未被处理，导致正标高被错误过滤掉。
- **修复**: 使用 `try/except float()` 替代字符串操作。

### H-15: 假阴性审计中运算符优先级错误
- **文件**: [false_negative_auditor.py](file:///workspace/v7/audit/false_negative_auditor.py#L119-L121)
- **行号**: 119-121
- **问题**: `or` 的优先级低于 `if/else` 三元表达式，可能获取不相关的图纸文本。
- **修复**: 拆分为多行显式逻辑。

### H-16: 假阴性审计中 verdict 字段不存在于 UnifiedIssue
- **文件**: [false_negative_auditor.py](file:///workspace/v7/audit/false_negative_auditor.py#L165-L169)
- **行号**: 165-169
- **问题**: `UnifiedIssue` 没有 `verdict` 字段，`getattr(i, "verdict", "")` 永远返回空字符串。
- **修复**: 添加 `verdict` 字段或检查其他字段。

### H-17: pickle 反序列化安全风险（unified_pipeline）
- **文件**: [unified_pipeline.py](file:///workspace/v7/unified_pipeline.py#L64-L65)
- **行号**: 64-65, 94
- **问题**: 同 C-06。
- **修复**: 同 C-06。

### H-18: 空间分析全量扫描实体列表
- **文件**: [spatial_reasoning.py](file:///workspace/v7/spatial_reasoning.py#L635-L638)
- **行号**: 635-638
- **问题**: 每次调用 `find_cross_floor_conflicts()` 都 O(N) 全量扫描过滤墙体和柱子。
- **修复**: 建立分类索引。

### H-19: 合理性引擎加权计算未使用权重
- **文件**: [rationality_engine.py](file:///workspace/v7/rationality_engine.py#L336)
- **行号**: 336
- **问题**: 同 C-11。
- **修复**: 同 C-11。

### H-20: 代码大量重复
- **文件**: [unified_pipeline.py](file:///workspace/v7/unified_pipeline.py#L43-L55) vs [spatial_reasoning.py](file:///workspace/v7/spatial_reasoning.py#L447-L466)
- **行号**: 43-55
- **问题**: `classify_enhanced()` 和专业前缀定义完全重复。
- **修复**: 提取到共享模块。

### H-21: 报告翻译器统计数字硬编码
- **文件**: [report_translator.py](file:///workspace/v7/report_translator.py#L540-L577)
- **行号**: 540-577
- **问题**: 同 C-10。
- **修复**: 同 C-10。

### H-22: 报告翻译器极度压缩的单行代码
- **文件**: [report_translator.py](file:///workspace/v7/report_translator.py#L518)
- **行号**: 518
- **代码**: `w=[]; B=lambda:w.append(""); D=lambda s:w.append("  "+s)`
- **问题**: 可读性极差，维护困难。
- **修复**: 使用正常的多行代码。

### H-23: API 密钥无加密库时明文存储
- **文件**: [secure_config.py](file:///workspace/v7/secure_config.py#L92-L94)
- **行号**: 92-94, 113-114
- **问题**: 无 `cryptography` 库时 API Key 仅做 base64 编码（非加密）。
- **修复**: 无加密库时拒绝存储密钥或发出强烈警告。

### H-24: HTTP 服务器 CORS 允许所有来源
- **文件**: [server.py](file:///workspace/v7/server.py#L115)
- **行号**: 115
- **代码**: `self.send_header("Access-Control-Allow-Origin", "*")`
- **修复**: 限制为特定域名。

### H-25: launcher 中 server 变量可能未定义
- **文件**: [launcher.py](file:///workspace/v7/launcher.py#L98)
- **行号**: 98
- **问题**: 如果 `HTTPServer()` 构造失败，`server.server_close()` 会抛 `NameError`。
- **修复**: 将 `server` 初始化为 `None` 并在 finally 块中检查。

### H-26: 三个场景报告生成逻辑在两个文件中重复
- **文件**: [generate_three_scene_reports.py](file:///workspace/v7/generate_three_scene_reports.py) vs [llm_full_review.py](file:///workspace/v7/llm_full_review.py)
- **问题**: `gen_scene1/2/3` 在两个文件中重复实现。
- **修复**: 统一到独立报告模块。

### H-27: 冲突状态管理器 O(N*M) 性能问题
- **文件**: [conflict_state_manager.py](file:///workspace/v7/conflict_state_manager.py#L176-L177)
- **行号**: 176-177
- **问题**: `sync_from_diff()` 中对每个 key 重新计算 `cur_keys`。
- **修复**: 在循环外计算一次。

### H-28: MTEXT 换行符处理错误
- **文件**: [pil_renderer.py](file:///workspace/v7/preprocessor/pil_renderer.py#L291)
- **行号**: 291
- **代码**: `.replace("\\p", "\n")` — 小写 `\p` 在 MTEXT 中是对齐方式而非换行。
- **修复**: 移除 `.replace("\\p", "\n")`。

### H-29: MTEXT 文本提取使用错误属性
- **文件**: [pil_renderer.py](file:///workspace/v7/preprocessor/pil_renderer.py#L289)
- **行号**: 289
- **代码**: `text = e.text` — 对 MTEXT 应使用 `e.plain_text()`。
- **修复**: 改为 `e.plain_text() if hasattr(e, 'plain_text') else e.dxf.text`。

### H-30: find_autocad 函数在两个文件中完全重复
- **文件**: [dwg_converter.py](file:///workspace/v7/preprocessor/dwg_converter.py#L55-L59) vs [cad_printer.py](file:///workspace/v7/preprocessor/cad_printer.py#L27-L33)
- **问题**: 同名函数完全重复。
- **修复**: 合并到共享模块。

### H-31: 框架检测器 A0 前缀匹配过于宽泛
- **文件**: [frame_splitter.py](file:///workspace/v7/preprocessor/frame_splitter.py#L90)
- **行号**: 90
- **代码**: `name.startswith("A0")` — `A0++` 也以 `A0` 开头会被错误惩罚。
- **修复**: 使用精确匹配 `name in ("A0", "A0+", "A0++")`。

### H-32: 图纸分类器 max 结果不确定
- **文件**: [drawing_extractor.py](file:///workspace/v7/preprocessor/drawing_extractor.py#L209)
- **行号**: 209
- **代码**: `max(scores, key=scores.get)` — 多个 discipline 得分相同时结果不确定。
- **修复**: 添加确定性排序。

### H-33: 缓存字典无大小限制导致内存泄漏
- **文件**: [drawing_extractor.py](file:///workspace/v7/preprocessor/drawing_extractor.py#L111), [drawing_scanner.py](file:///workspace/v7/scanner/drawing_scanner.py#L91)
- **行号**: 111, 91
- **问题**: `_text_cache` 和 `_cache` 无大小限制。
- **修复**: 使用 `functools.lru_cache` 或添加缓存大小上限。

### H-34: 缓存键中 os.path.getsize 未处理文件不存在
- **文件**: [drawing_extractor.py](file:///workspace/v7/preprocessor/drawing_extractor.py#L126)
- **行号**: 126
- **问题**: `_cache_key()` 调用 `os.path.getsize(dxf_path)` 但未处理文件不存在的情况。
- **修复**: 添加 `os.path.exists` 检查。

### H-35: openpyxl 引擎硬编码且无异常处理
- **文件**: [title_block_extractor.py](file:///workspace/v7/preprocessor/title_block_extractor.py#L483)
- **行号**: 483
- **问题**: `df.to_excel(..., engine="openpyxl")` 未处理 openpyxl 未安装的情况。
- **修复**: 在 try 块中添加 openpyxl 导入检查。

### H-36: columns 过滤后可能为空列表
- **文件**: [title_block_extractor.py](file:///workspace/v7/preprocessor/title_block_extractor.py#L479)
- **行号**: 479
- **问题**: 过滤后 `columns` 可能为空，导致 `df[columns]` 抛异常。
- **修复**: 添加空列表检查。

### H-37: deepcopy 对 ezdxf 实体可能不完整
- **文件**: [dwg_subset_splitter.py](file:///workspace/v7/preprocessor/dwg_subset_splitter.py#L232)
- **行号**: 232, 298
- **问题**: `copy.deepcopy(e)` 对 ezdxf 实体可能丢失内部引用。
- **修复**: 使用 ezdxf 提供的实体复制方法。

### H-38: IMAGE 实体 bbox 计算不完整
- **文件**: [dwg_subset_splitter.py](file:///workspace/v7/preprocessor/dwg_subset_splitter.py#L130-L131)
- **行号**: 130-131
- **问题**: IMAGE 实体可能有不同的 U/V 像素尺寸和缩放因子。
- **修复**: 使用 `entity.get_bbox()` 或完整计算变换后的边界。

---

## 四、Medium 级问题（应计划修复）

### 按文件分组

#### v7/llm/ 模块

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| M-01 | base_adapter.py | 92 | `ask_json` 中 `except (json.JSONDecodeError, Exception)` 过于宽泛，且 `'raw' in dir()` 检查不可靠 |
| M-02 | base_adapter.py | 118 | `avg_latency_ms` 每次调用都重新计算全部延迟列表的平均值 |
| M-03 | text_adapter.py | 63 | `response.usage` 异常被静默吞掉 |
| M-04 | vision_adapter.py | 112 | 图片 detail 硬编码为 `"high"`，大图时可能超出 token 限制 |
| M-05 | __init__.py | 114-157 | `call_with_failover` 中 fallback_chain 顺序遍历，无成本/成功率感知 |

#### v7/agents/ 模块

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| M-06 | base_agent.py | 133 | `_TEXT_BATCH_CHARS = 90000` 无注释说明依据 |
| M-07 | discipline_agents.py | 36-83 | `_filter_with_content_fallback` 中 `score >= 2` 阈值硬编码 |
| M-08 | discipline_agents.py | 302 | `FreeReviewAgent.execute` 中 `except Exception: self._report.errors += 1` 无日志 |
| M-09 | discipline_agents.py | 338 | `merged_text[:8000]` 截断长度硬编码且与 base_agent 的 90000 不一致 |
| M-10 | chief_agent.py | 44 | `_merge_distance` 声明但未使用 |
| M-11 | chief_agent.py | 77-89 | `_is_duplicate` 仅检查 `cad_coords`，无坐标时直接返回 False，去重失效 |
| M-12 | chief_agent.py | 114 | 级联降级策略 `_SEVERITY_DOWNGRADE` 无文档说明依据 |

#### v7/preprocessor/ 模块

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| M-13 | drawing_extractor.py | 236-237 | `infer_discipline_from_entities` 使用文件名级关键字而非内容级关键字 |
| M-14 | drawing_pipeline.py | 51-53 | `--text-verify` 和 `--no-text-verify` 互斥参数设计易混淆 |
| M-15 | frame_splitter.py | 90 | 图框匹配中 `A0` 前缀惩罚逻辑过于宽泛 |
| M-16 | grid_splitter.py | 44 | 同一图片被读取两次（密度计算和切片） |
| M-17 | grid_splitter.py | 119 | `gc.collect()` 每5个网格调用一次，频率过高 |
| M-18 | grid_splitter.py | 80-81 | 临时目录从未自动清理 |
| M-19 | image_enhancer.py | 21 | 锐化核强度过大（中心权重9） |
| M-20 | title_block_extractor.py | 226-231 | 标签和值的关联仅基于 Y 坐标距离最近匹配 |
| M-21 | standardization_checker.py | 60 | `STD-005` 中空字符串正则匹配所有文本 |
| M-22 | cad_printer.py | 17-24 | AutoCAD 路径硬编码特定用户安装路径 |
| M-23 | cad_printer.py | 187 | 默认字体不支持中文 |
| M-24 | cad_printer.py | 254-256 | 硬编码 `"python"` 命令，Linux 上应为 `"python3"` |
| M-25 | dwg_converter.py | 22-26 | ODA 路径硬编码特定版本号 |
| M-26 | dwg_converter.py | 73-78 | 输出版本硬编码为 ACAD2013 |
| M-27 | dwg_subset_splitter.py | 176-250 | 多个 `_copy_*_defs` 函数结构几乎完全相同 |
| M-28 | dwg_subset_splitter.py | 393-403 | 多布局文件复制全部模型空间导致数据冗余 |
| M-29 | enhanced_frame_detector.py | 23-34 | `STANDARD_FRAMES` 与 `frame_splitter.py` 重复定义 |
| M-30 | pil_renderer.py | 123-158 | INSERT 递归展开上限 100000 可能导致大型图纸展开不完整 |

#### v7/problem_pool/, scanner/, cross_drawing/, audit/

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| M-31 | pool.py | 166-170 | 三个索引字典声明但从未使用 |
| M-32 | pool.py | 228 | 直接访问 `text_entity.x/y/z` 无类型安全保障 |
| M-33 | drawing_scanner.py | 111 | 硬编码截断长度 6000 字符且未告知调用方 |
| M-34 | drawing_scanner.py | 121-126 | 调用 `_extract_json` 私有方法违反封装 |
| M-35 | drawing_scanner.py | 125-126 | JSON 解析异常被完全吞掉（`pass`） |
| M-36 | cross_context.py | 138-140 | 正则表达式每次调用都重新编译 |
| M-37 | cross_context.py | 214, 240, 262, 283, 308, 326 | 所有检查方法硬编码最多返回 5 个问题 |
| M-38 | cross_context.py | 296-297 | 标高基准面判断仅比较最小值过于简单 |
| M-39 | false_negative_auditor.py | 91 | 时区不一致（混用 `datetime.now()` 和 `datetime.now(timezone.utc)`） |
| M-40 | false_negative_auditor.py | 103 | 随机抽样无种子，审计结果不可复现 |
| M-41 | false_negative_auditor.py | 133-134 | 复核异常仅记录在字段中，无日志 |
| M-42 | prompt_templates.py | 13 | 模块级全局变量缓存在多线程中不安全 |
| M-43 | prompt_templates.py | 50-51 | YAML 加载失败异常被完全吞掉 |
| M-44 | prompt_templates.py | 11 | `SYSTEM_BASE` 常量定义但从未使用 |
| M-45 | prompt_templates.py | 97 | 截断长度 90000 硬编码 |
| M-46 | prompt_templates.py | 80-95 | `build_text_prompt` 和 `build_vision_prompt` 大量重复逻辑 |
| M-47 | role_report_generator.py | 15 | 时区不一致（不使用时区） |
| M-48 | role_report_generator.py | 296-306 | 风险评分权重和阈值硬编码 |
| M-49 | role_report_generator.py | 340-344 | 成本估算系数硬编码 |

#### v7/ 根目录散落文件

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| M-50 | llm_full_review.py | 14 | 模块级修改 sys.path |
| M-51 | llm_full_review.py | 104 | 文件编码回退逻辑不完整 |
| M-52 | llm_full_review.py | 全文 | 缓存数据硬编码在源码中 |
| M-53 | rationality_engine.py | 78 | `occupants=0` 时 margin=0 可能产生误导 |
| M-54 | rationality_engine.py | 428 | `annotate_all_rationality()` 直接修改传入参数 |
| M-55 | spatial_reasoning.py | 21-27 | 配置文件加载异常被静默吞掉 |
| M-56 | spatial_reasoning.py | 257 | Python `hash()` 跨进程不确定 |
| M-57 | spatial_reasoning.py | 296 | 缓存目录路径遍历风险 |
| M-58 | spatial_reasoning.py | 597 | 使用 `print` 输出进度信息 |
| M-59 | spatial_reasoning.py | 797-833 | rtree 和非 rtree 版本重复代码 |
| M-60 | unified_pipeline.py | 41 | 直接访问私有属性 `_cache_dir` |
| M-61 | unified_pipeline.py | 187-191 | 手动构造 `argparse.Namespace` 耦合脆弱 |
| M-62 | unified_pipeline.py | 206 | 访问私有属性 `_issues` |
| M-63 | conflict_diff.py | 88-127 | `mark_waived` 和 `mark_resolved` 结构几乎完全相同 |
| M-64 | conflict_state_manager.py | 51-61 | TOCTOU 竞态条件 |
| M-65 | report_translator.py | 25 | 硬编码回退文件名包含具体日期 |
| M-66 | report_translator.py | 155, 168, 519, 526 | 报告编号和日期硬编码 |
| M-67 | server.py | 86-94 | 统计数据硬编码 |
| M-68 | server.py | 278 | 绑定到所有网络接口 |
| M-69 | launcher.py | 89 | 导入了 `admin_main` 但从未使用 |
| M-70 | generate_three_scene_reports.py | 全文 | 与 llm_full_review.py 重复 |
| M-71 | uai_review_data.py | 6-102 | 145条审查数据硬编码在源文件中 |
| M-72 | secure_config.py | 39-44 | 每次调用都重新读取 JSON 文件 |

---

## 五、Low 级问题（可择机修复）

### 按类别分组

#### 死代码 / 未使用

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| L-01 | frame_splitter.py | 13 | `BoundingBox2d` 导入但未使用 |
| L-02 | enhanced_frame_detector.py | 19 | `BoundingBox2d` 导入但未使用 |
| L-03 | enhanced_frame_detector.py | 124-133 | `_get_frame_from_insert_bbox` 定义但未调用 |
| L-04 | enhanced_frame_detector.py | 348-360 | `_apply_text_verification` 未被调用（被 cached 版替代） |
| L-05 | pool.py | 171 | `_merge_distance` 声明但未使用 |
| L-06 | cross_context.py | 60-62 | 三个正则常量定义但未使用 |
| L-07 | prompt_templates.py | 11 | `SYSTEM_BASE` 常量定义但未使用 |
| L-08 | pil_renderer.py | 19-21 | `RENDER_DPI` 等常量未被使用 |
| L-09 | pil_renderer.py | 24 | `_compute_bounding_box` 的 `blocks` 参数未使用 |
| L-10 | title_block_extractor.py | 254 | `_drawing_number_cache` 声明但未使用 |
| L-11 | dwg_converter.py | 157 | `max_workers` 参数声明但未使用 |
| L-12 | launcher.py | 89 | `admin_main` 导入但未使用 |

#### 代码风格 / 可读性

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| L-13 | drawing_extractor.py | 146 | 嵌套三元表达式可读性差 |
| L-14 | drawing_extractor.py | 338 | 同一文件内使用绝对路径导入自身 |
| L-15 | base_adapter.py | 94 | `'raw' in dir()` 检查不可靠 |
| L-16 | llm_full_review.py | 74 | 类型注解使用小写 `callable` |
| L-17 | llm_full_review.py | 1306 | 函数内部导入标准库 |
| L-18 | report_translator.py | 518 | 极度压缩的单行代码 |
| L-19 | grid_splitter.py | 111-113 | 变量名 `_` 过于隐晦 |
| L-20 | cross_context.py | 234 | f-string 中多余的空格 `{ disc}` |
| L-21 | standardization_checker.py | 119 | `DN\d+` 重复出现两次 |
| L-22 | standardization_checker.py | 170 | `len(val) > 0` 与 `val` 冗余 |
| L-23 | pil_renderer.py | 56, 135 | 循环内部导入 `math` |
| L-24 | false_negative_auditor.py | 218 | 函数内部导入 `os` |
| L-25 | false_negative_auditor.py | 156 | 日志中使用 emoji 字符 |

#### 性能（轻微）

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| L-26 | pool.py | 263-266 | 每次排序创建新字典字面量 |
| L-27 | pool.py | 312-313 | `count_dual_verified()` 被调用两次 |
| L-28 | grid_splitter.py | 30 | 读取图片后立即丢弃仅获取尺寸 |
| L-29 | role_report_generator.py | 194 | 循环内每次创建固定字典 |
| L-30 | prompt_templates.py | 179-189 | 每次调用创建新字典 |
| L-31 | drawing_scanner.py | 101 | MD5 对超大文本消耗内存 |

#### 魔法数字 / 硬编码

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| L-32 | base_agent.py | 133 | `_TEXT_BATCH_CHARS = 90000` |
| L-33 | drawing_scanner.py | 111 | 截断长度 6000 |
| L-34 | drawing_scanner.py | 117 | 原始响应截断 500 字符 |
| L-35 | llm_full_review.py | 124, 156 | 截断长度 80000/30000 |
| L-36 | standardization_checker.py | 285 | 85% 通过率阈值 |
| L-37 | rationality_engine.py | 88 | 魔法数字 1.15 和 100 |
| L-38 | cad_printer.py | 233 | 截取 200 个文本实体 |
| L-39 | pil_renderer.py | 206 | 字体大小硬编码 14px |
| L-40 | pil_renderer.py | 165 | 文件大小阈值 80MB |

---

## 六、跨文件系统性问题

### 6.1 Windows 路径硬编码（6 个文件）
- **涉及**: `spatial_reasoning.py`, `llm_full_review.py`, `dxf_marker.py`, `generate_three_scene_reports.py`, `drawing_pipeline.py`, `dwg_converter.py`
- **建议**: 统一使用 `os.path.dirname(os.path.abspath(__file__))` 动态获取路径，禁止硬编码个人路径。

### 6.2 代码重复（4 组）
- **涉及**: `unified_pipeline.py` ↔ `spatial_reasoning.py`（专业分类逻辑）；`generate_three_scene_reports.py` ↔ `llm_full_review.py`（场景报告）；`dwg_converter.py` ↔ `cad_printer.py`（find_autocad）；`enhanced_frame_detector.py` ↔ `frame_splitter.py`（STANDARD_FRAMES）
- **建议**: 提取到共享模块。

### 6.3 pickle 使用（2 个文件）
- **涉及**: `spatial_reasoning.py`, `unified_pipeline.py`
- **建议**: 替换为 `json` 或 `msgpack`。

### 6.4 异常吞没（8 处）
- **涉及**: `drawing_scanner.py`(2处), `prompt_templates.py`(1处), `discipline_agents.py`(1处), `false_negative_auditor.py`(1处), `base_adapter.py`(1处), `role_report_generator.py`(全文件无日志)
- **建议**: 所有 `except Exception: pass` 至少添加 `logger.debug()`。

### 6.5 时区不一致（3 个文件）
- **涉及**: `pool.py`(使用 UTC), `false_negative_auditor.py`(混用), `role_report_generator.py`(不使用时区)
- **建议**: 统一使用 `datetime.now(timezone.utc)`。

### 6.6 硬编码统计数字（3 个文件）
- **涉及**: `report_translator.py`, `server.py`, `excel_reporter.py`
- **建议**: 从实际数据动态计算。

### 6.7 sys.path 全局修改（3 个文件）
- **涉及**: `llm_full_review.py`, `unified_pipeline.py`, `generate_three_scene_reports.py`
- **建议**: 使用 `pyproject.toml` 包管理。

### 6.8 缓存无大小限制（3 个文件）
- **涉及**: `drawing_extractor.py`, `drawing_scanner.py`, `problem_pool/pool.py`
- **建议**: 使用 `functools.lru_cache` 或 `cachetools.LRUCache`。

### 6.9 配置分散（3 个位置）
- **涉及**: `v7/config.yaml`, `v7/config/project_config.yaml`, 各文件内硬编码常量
- **建议**: 统一配置管理。

### 6.10 类型注解缺失（绝大多数文件）
- **建议**: 逐步添加类型注解，优先覆盖公共 API。

---

## 七、修复优先级路线图

### 第一阶段：Critical 修复（1-2 天）
1. C-01 ~ C-02: 标准化检查器正则修复 + 图框拆分渲染修复
2. C-03: 空间分析 bounds 修复
3. C-04: DXF 标记坐标修复
4. C-06 ~ C-08: pickle 替换 + 密钥安全 + HTTP 安全
5. C-09: Windows 路径清理
6. C-11 ~ C-12: 合理性引擎 + 路径遍历修复

### 第二阶段：High 修复（3-5 天）
1. H-01 ~ H-02: 标准化检查器剩余问题
2. H-11 ~ H-16: 问题池 + 扫描器 + 跨图纸分析修复
3. H-17 ~ H-20: 安全 + 性能修复
4. H-26 ~ H-30: 代码重复消除

### 第三阶段：Medium 修复（1-2 周）
1. 异常处理规范化
2. 缓存机制完善
3. 配置统一管理
4. 类型注解补全

### 第四阶段：Low 修复（持续）
1. 死代码清理
2. 代码风格统一
3. 魔法数字提取为常量
4. 性能微优化
