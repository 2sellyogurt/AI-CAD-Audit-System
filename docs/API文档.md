# 施工图智能审查系统 v6.0 - API文档

## 1. 命令行接口（CLI）

### 1.1 master.py - 主控调度入口

```
python src/master.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--dxf-dir` | str | `/workspace/.uploads` 或 `PIPELINE_DXF_DIR` 环境变量 | DXF 文件目录 |
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` 环境变量 | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` 环境变量 | 报告输出目录 |
| `--skip-step` | int[] | `[]` | 跳过指定步骤（如 `--skip-step 1`） |
| `--only-step` | int[] | `[]` | 只执行指定步骤（如 `--only-step 2 3`） |
| `--stop-after` | int | None | 执行到指定步骤后停止（如 `--stop-after 3`） |
| `--dry-run` | flag | False | 仅显示执行计划，不实际运行 |
| `--llm-provider` | str | `zhipu` | LLM服务提供者（zhipu等） |
| `--llm-model` | str | `glm-4-flash` | LLM模型名称 |
| `--llm-api-key` | str | 环境变量 `LLM_API_KEY` | LLM API密钥 |
| `--building-type` | str | `residential` | 建筑类型（residential/commercial），控制规则自动过滤 |

**示例**:
```bash
# 执行全部9步
python src/master.py

# 指定DXF和输出目录，跳过DXF提取（已有JSON时）
python src/master.py --dxf-dir ./drawings --json-dir ./json_data --output-dir ./output --skip-step 1

# 只执行第2、3步
python src/master.py --only-step 2 3

# 执行到第3步后停止
python src/master.py --stop-after 3

# 公建项目，启用LLM
python src/master.py --building-type commercial --llm-provider zhipu --llm-model glm-4-flash --llm-api-key YOUR_KEY
```

### 1.2 step0_anchor.py - 锚点提取

```
python src/step0_anchor.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--dxf-dir` | str | `/workspace/.uploads` | DXF 文件目录 |
| `--output-dir` | str | `./json_data` | JSON 输出目录 |

**输出**: 锚点数据文件（图号+楼层+轴线范围）。

### 1.3 step1_extract.py - DXF提取

```
python src/step1_extract.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--dxf-dir` | str | `/workspace/.uploads` | DXF 文件目录 |
| `--output-dir` | str | `./json_data` | JSON 输出目录 |
| `--llm-provider` | str | `zhipu` | LLM服务提供者 |
| `--llm-model` | str | `glm-4-flash` | LLM模型名称 |
| `--llm-api-key` | str | 环境变量 `LLM_API_KEY` | LLM API密钥 |

**输出**: 每个DXF文件生成一个 `*_unified.json` 文件。

### 1.4 step2_compliance.py - 合规审查

```
python src/step2_compliance.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |
| `--building-type` | str | `residential` | 建筑类型（residential/commercial），控制规则自动过滤 |
| `--llm-provider` | str | `zhipu` | LLM服务提供者 |
| `--llm-model` | str | `glm-4-flash` | LLM模型名称 |
| `--llm-api-key` | str | 环境变量 `LLM_API_KEY` | LLM API密钥 |

**输出**: `step2_compliance_result.json`

### 1.5 step3_defect.py - 错漏排查

```
python src/step3_defect.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |

**输出**: `step3_defect_result.json`

### 1.6 step4_cross_check.py - 跨专业校验

```
python src/step4_cross_check.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |

**输出**: `step4_cross_check_result.json`

### 1.7 step5_engineering.py - 工程分析+报告

```
python src/step5_engineering.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |
| `--llm-provider` | str | `zhipu` | LLM服务提供者 |
| `--llm-model` | str | `glm-4-flash` | LLM模型名称 |
| `--llm-api-key` | str | 环境变量 `LLM_API_KEY` | LLM API密钥 |

**输出**: 6份 Markdown 报告 + `会审问题清单.md` + `issues_snapshot.json`

### 1.8 step6_bim.py - BIM管线

```
python src/step6_bim.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |

**输出**: BIM管线分析结果

### 1.9 step7_rag.py - RAG审核

```
python src/step7_rag.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |
| `--llm-provider` | str | `zhipu` | LLM服务提供者 |
| `--llm-model` | str | `glm-4-flash` | LLM模型名称 |
| `--llm-api-key` | str | 环境变量 `LLM_API_KEY` | LLM API密钥 |

**输出**: RAG审核结果

### 1.10 step8_review.py - 二次审查

```
python src/step8_review.py [参数]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--json-dir` | str | `./json_data` 或 `PIPELINE_JSON_DIR` | JSON 文件目录 |
| `--output-dir` | str | `./output` 或 `PIPELINE_OUTPUT_DIR` | 输出目录 |
| `--llm-provider` | str | `zhipu` | LLM服务提供者 |
| `--llm-model` | str | `glm-4-flash` | LLM模型名称 |
| `--llm-api-key` | str | 环境变量 `LLM_API_KEY` | LLM API密钥 |

**输出**: 二次审查结果

---

## 2. Python API - 引擎模块

### 2.1 engine/json_loader.py - JsonLoader

```python
from engine.json_loader import JsonLoader

loader = JsonLoader(json_dir: str)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `loader.files` | `List[str]` | 返回所有 JSON 文件名列表（仅包含 `*_unified.json` 文件） |
| `loader.get_readable_name(file_name: str)` | `str` | 将 UUID 文件名转换为可读名称（如 `a1b2_建筑平面图_unified.json` → `建筑平面图`） |
| `loader.get_text_lines_by_file(file_name: str)` | `List[str]` | 根据文件名返回该文件中的所有文本行（从 `raw_texts` 字段提取） |
| `loader.get_file_count()` | `int` | 返回 JSON 文件数量 |

**输入文件格式** (`*_unified.json`):
```json
{
  "raw_texts": ["卧室净高2.4m", "层高2.8m"],
  "elevations": [
    {"value": 3.600, "text": "层高3.6m", "type": "层高"},
    {"value": -0.050, "text": "标高-0.05m", "type": "标高"}
  ],
  "metadata": {
    "source_file": "建筑-一层平面图.dxf",
    "discipline": "建筑",
    "building": "综合楼",
    "text_count": 2,
    "elevation_count": 2
  }
}
```

### 2.2 engine/rule_checker.py - RuleChecker

```python
from engine.rule_checker import RuleChecker

checker = RuleChecker(loader: JsonLoader)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `checker.rules_config` | `List[dict]` | 返回已加载的规则配置列表 |
| `checker.rules_path` | `str` | 返回规则文件路径 |
| `checker.check_all_rules()` | `List[dict]` | 对 loader 中所有 JSON 文件逐条规则检查，返回每条规则的审查结果 |
| `checker.get_statistics(rule_results)` | `dict` | 对审查结果进行统计分析，返回合规/不合规/待核实/不适用的数量和按专业分类统计 |
| `checker.search_by_keyword(keyword: str)` | `List[dict]` | 按关键词搜索规则 |
| `checker.search_by_regex(pattern: str)` | `List[dict]` | 按正则表达式搜索规则 |
| `checker.reload_rules()` | `None` | 热加载规则文件（无需重启） |

**check_all_rules() 返回格式**:
```json
{
  "rule_id": "rule_001",
  "category": "建筑",
  "description": "住宅卧室净高不应低于2.4m",
  "severity": "严重",
  "is_mandatory": true,
  "standard_code": "GB 55038-2025 第4.1.2条",
  "compliance_status": "合规",
  "matched_keywords": ["卧室", "净高", "2.4"],
  "file": "建筑平面图",
  "matched_text": "卧室净高不应低于2.45m 符合要求",
  "confidence_level": "L3-完整"
}
```

**severity 四级风险分级**:

| 值 | 说明 |
|----|------|
| `严重` | 强条违反，违反强制性条文，必须整改 |
| `重要` | 非强条违规，违反非强制性条文，建议整改 |
| `一般` | 待核实，需进一步核实确认 |
| `提示` | 合规，符合规范要求 |

**is_mandatory 字段**:
- `true`: 该规则为强制性条文
- `false`: 该规则为非强制性条文

**get_statistics() 返回格式**:
```json
{
  "total": 280,
  "compliant": 30,
  "non_compliant": 5,
  "need_verify": 15,
  "not_applicable": 230,
  "by_discipline": {
    "建筑": {"total": 45, "compliant": 8, "non_compliant": 2, "need_verify": 3, "not_applicable": 32},
    "结构": {"total": 42, ...}
  },
  "by_severity": {
    "严重": {"total": 50, "compliant": 10, "non_compliant": 3, "need_verify": 5, "not_applicable": 32},
    "重要": {"total": 80, ...},
    "一般": {"total": 90, ...},
    "提示": {"total": 60, ...}
  }
}
```

### 2.3 engine/elevation_calc.py - ElevationCalc

```python
from engine.elevation_calc import ElevationCalc

calc = ElevationCalc(loader: JsonLoader)
results = calc.run_all_checks()
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `run_all_checks()` | `dict` | 返回标高计算、净高验算、梁开洞可行性分析的全部结果 |

**返回结构**: `{ "summary": {...}, "elevations": [...], "beam_dimensions": [...], "slab_thickness": [...], "finish_thickness": [...], "functional_net_height": [...], "beam_drilling": [...] }`

### 2.4 engine/collision_detect.py - CollisionDetect

```python
from engine.collision_detect import CollisionDetect

detect = CollisionDetect(loader: JsonLoader)
results = detect.run_all_checks(beam_dimensions: List[dict])
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `run_all_checks(beam_dimensions)` | `dict` | 执行8类碰撞检测，`beam_dimensions` 来自 ElevationCalc 结果 |

### 2.5 engine/geometric_collision.py - GeometricCollision

```python
from engine.geometric_collision import GeometricCollision

collision = GeometricCollision(loader: JsonLoader)
results = collision.run_all_checks()
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `run_all_checks()` | `dict` | 执行跨专业标高+轴线几何碰撞检测 |

### 2.6 engine/axis_collision.py - AxisCollisionDetector

```python
from engine.axis_collision import AxisCollisionDetector

detector = AxisCollisionDetector(loader: JsonLoader)
results = detector.run_all_checks()
```

### 2.7 engine/mep_coordinator.py - MepCoordinator

```python
from engine.mep_coordinator import MepCoordinator

coordinator = MepCoordinator(loader: JsonLoader, rules_config: List[dict])
results = coordinator.run_all_checks()
```

### 2.8 engine/cross_discipline.py - CrossDiscipline

```python
from engine.cross_discipline import CrossDiscipline

checker = CrossDiscipline(loader: JsonLoader, rules_config: List[dict] = None)
results = checker.run_all_checks()
deep_results = checker.deep_check()
```

### 2.9 engine/engineering_analysis.py - EngineeringAnalyzer

```python
from engine.engineering_analysis import EngineeringAnalyzer

analyzer = EngineeringAnalyzer(loader: JsonLoader, rules_config: List[dict] = None)
results = analyzer.run_all_checks()
report = analyzer.full_lifecycle_report()
```

### 2.10 engine/construction_schedule.py - ConstructionSchedule

```python
from engine.construction_schedule import ConstructionSchedule

scheduler = ConstructionSchedule()
results = scheduler.analyze(project_data: dict)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `analyze(project_data)` | `dict` | 施工排程分析 v2.0，返回工期可行性、关键路径、优化建议 |

### 2.11 engine/discipline_identifier.py - DisciplineIdentifier

```python
from engine.discipline_identifier import DisciplineIdentifier

identifier = DisciplineIdentifier()
discipline = identifier.identify(file_name: str, content: str = None)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `identify(file_name, content)` | `str` | 两级策略专业识别：先文件名匹配，再内容语义分析，未识别率2.7% |

### 2.12 engine/experience_matcher.py - ExperienceMatcher

```python
from engine.experience_matcher import ExperienceMatcher

matcher = ExperienceMatcher()
results = matcher.run_checks(report_texts: List[str] = None)
matcher.print_summary(results)
```

### 2.13 engine/layer_mapper.py - LayerMapper

```python
from engine.layer_mapper import LayerMapper

mapper = LayerMapper()
discipline, category = mapper.classify(layer_name: str)
```

### 2.14 engine/geometry_extractor.py - GeometryExtractor

```python
from engine.geometry_extractor import GeometryExtractor

extractor = GeometryExtractor(layer_mapper: LayerMapper)
result = extractor.extract_from_dxf(dxf_path: str)
```

### 2.15 engine/geometry_analyzer.py - GeometryAnalyzer

```python
from engine.geometry_analyzer import GeometryAnalyzer

analyzer = GeometryAnalyzer(components: List, dimensions: List)
findings = analyzer.run_all_checks()
summary = analyzer.get_summary()
```

### 2.16 engine/lru_cache.py - LruCache

```python
from engine.lru_cache import LruCache

cache = LruCache(capacity: int = 128)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `get(key: str)` | `Any` | 获取缓存值，未命中返回 None |
| `put(key: str, value: Any)` | `None` | 写入缓存，超出容量自动淘汰最久未使用项 |
| `invalidate(key: str)` | `None` | 使指定缓存项失效 |
| `clear()` | `None` | 清空全部缓存 |
| `stats()` | `dict` | 返回缓存统计（命中率、容量、当前大小） |

### 2.17 engine/performance_monitor.py - PerformanceMonitor

```python
from engine.performance_monitor import PerformanceMonitor

monitor = PerformanceMonitor()
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `start_timer(name: str)` | `None` | 开始计时 |
| `stop_timer(name: str)` | `float` | 停止计时，返回耗时（秒） |
| `record_metric(name: str, value: float)` | `None` | 记录自定义指标 |
| `get_report()` | `dict` | 连性能报告（各步骤耗时、内存占用、缓存命中率） |
| `reset()` | `None` | 重置所有监控数据 |

---

## 3. Python API - LLM模块

### 3.1 engine/llm/client.py - LLMClient

```python
from engine.llm.client import LLMClient

client = LLMClient(provider: str = "zhipu", model: str = "glm-4-flash", api_key: str = None)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `client.chat(messages: List[dict])` | `str` | 发送聊天请求，返回模型响应文本 |
| `client.chat_with_context(prompt: str, context: str)` | `str` | 带上下文的聊天请求 |

### 3.2 engine/llm/elevation.py - LLMElevation

```python
from engine.llm.elevation import LLMElevation

elevation_llm = LLMElevation(client: LLMClient)
results = elevation_llm.extract_elevations(texts: List[str])
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `extract_elevations(texts)` | `List[dict]` | LLM辅助标高提取，返回标高数据列表 |

### 3.3 engine/llm/compliance.py - LLMCompliance

```python
from engine.llm.compliance import LLMCompliance

compliance_llm = LLMCompliance(client: LLMClient)
results = compliance_llm.judge_compliance(rule: dict, evidence: str)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `judge_compliance(rule, evidence)` | `dict` | LLM辅助合规判定，返回判定结果与理由 |

### 3.4 engine/llm/engineering.py - LLMEngineering

```python
from engine.llm.engineering import LLMEngineering

engineering_llm = LLMEngineering(client: LLMClient)
results = engineering_llm.analyze(engineering_data: dict)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `analyze(engineering_data)` | `dict` | LLM辅助工程分析，返回分析结论与建议 |

### 3.5 engine/llm/rag.py - LLMRAG

```python
from engine.llm.rag import LLMRAG

rag_llm = LLMRAG(client: LLMClient)
results = rag_llm.review(query: str, documents: List[str])
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `review(query, documents)` | `dict` | LLM辅助RAG审核，返回审核结果 |

### 3.6 engine/llm/review.py - LLMReview

```python
from engine.llm.review import LLMReview

review_llm = LLMReview(client: LLMClient)
results = review_llm.secondary_review(review_data: dict)
```

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `secondary_review(review_data)` | `dict` | LLM辅助二次审查，返回审查结论与误报/漏报标记 |

---

## 4. Python API - 报告模块

### 4.1 report/utils.py

```python
from report.utils import infer_floor

floor = infer_floor(file_name: str)
```

| 输入 | 返回 |
|------|------|
| `"一层平面图"` | `"1F"` |
| `"屋顶平面图"` | `"RF"` |
| `"地下室平面图"` | `"B1"` |
| `"地下二层平面图"` | `"B2"` |
| `""` 或 `None` | `"UNKNOWN"` |

### 4.2 report/report_generator_v50.py

```python
from report.report_generator_v50 import generate_all_reports

paths = generate_all_reports(
    output_dir: str,
    rule_results: List[dict],
    rule_stats: dict,
    elevation_results: dict,
    collision_results: dict,
    mep_results: dict,
    cross_check_results: dict,
    deep_check_results: dict,
    engineering_results: dict,
    project_info: dict,
    loader: JsonLoader
)
```

**返回**: `Dict[str, str]`，包含以下键：
- `"compliance_report"` → 强条合规性审查报告路径
- `"defect_report"` → 基础错漏排查报告路径
- `"cross_report"` → 跨专业一致性校验报告路径
- `"summary_report"` → 综合评估摘要报告路径
- `"meeting_list"` → 图纸会审问题清单路径
- `"llm_report"` → LLM分析报告路径

### 4.3 report/meeting_list.py

```python
from report.meeting_list import MeetingList

gen = MeetingList(output_dir: str)
path = gen.generate(
    project_info: dict,
    rule_results: list,
    elevation_results: dict,
    collision_results: dict,
    mep_results: dict,
    cross_check_results: dict,
    deep_check_results: dict,
    engineering_analysis: dict,
    loader: JsonLoader
)
```

---

## 5. 配置接口

### 5.1 config/rules.json

规则条目格式：
```json
{
  "rule_id": "rule_001",
  "category": "建筑",
  "description": "住宅卧室净高不应低于2.4m",
  "keywords": ["卧室", "净高", "2.4"],
  "regex": "卧室.*净高.*(2\\.?\\d+)",
  "severity": "严重",
  "is_mandatory": true,
  "standard_code": "GB 55038-2025 第4.1.2条",
  "building_types": ["residential"],
  "mapping_rules": {
    "discipline": "建筑",
    "sub_category": "净高"
  }
}
```

**关键字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `severity` | str | 四级风险分级：严重/重要/一般/提示 |
| `is_mandatory` | bool | 是否为强制性条文 |
| `building_types` | List[str] | 适用建筑类型（residential/commercial），公建专用规则标记为 `["commercial"]` |
| `mapping_rules` | dict | 规则映射信息（专业、子类别等） |

**规则统计**：共280条，6大专业各约40-50条，含23条公建专用规则。

### 5.2 config/project_config.json

```json
{
  "project_name": "AI智能审图系统 v6.0",
  "version": "6.0.0",
  "paths": { "input_dir": "./input", "output_dir": "./output", ... },
  "performance": { "max_file_parse_time": 5, "max_rule_check_time": 30, ... },
  "logging": { "level": "INFO", "format": "...", "file": "./output/logs/system.log" },
  "building_type": "residential",
  "llm": { "provider": "zhipu", "model": "glm-4-flash", "api_key_env": "LLM_API_KEY" }
}
```

---

## 6. 输出文件

| 文件 | 来源步骤 | 格式 |
|------|----------|------|
| 锚点数据文件 | Step 0 | JSON |
| `*_unified.json` | Step 1 | JSON |
| `step2_compliance_result.json` | Step 2 | JSON |
| `step3_defect_result.json` | Step 3 | JSON |
| `step4_cross_check_result.json` | Step 4 | JSON |
| `强条合规性审查报告_*.md` | Step 5 | Markdown |
| `基础错漏排查报告_*.md` | Step 5 | Markdown |
| `跨专业一致性校验报告_*.md` | Step 5 | Markdown |
| `综合评估摘要_*.md` | Step 5 | Markdown |
| `会审问题清单_*.md` | Step 5 | Markdown |
| `LLM分析报告_*.md` | Step 5 | Markdown |
| `issues_snapshot.json` | Step 5 | JSON |
| BIM管线分析结果 | Step 6 | JSON |
| RAG审核结果 | Step 7 | JSON |
| 二次审查结果 | Step 8 | JSON |

## 7. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PIPELINE_DXF_DIR` | `/workspace/.uploads` | DXF 文件目录 |
| `PIPELINE_JSON_DIR` | `./json_data` | JSON 文件目录 |
| `PIPELINE_OUTPUT_DIR` | `./output` | 输出目录 |
| `LLM_API_KEY` | 无 | LLM API密钥（智谱glm-4-flash） |

## 8. 测试接口

```bash
# 运行全部测试
pytest tests/ -v

# 运行指定测试目录
pytest tests/unit/ -v
pytest tests/integration/ -v

# 运行指定测试文件
pytest tests/test_json_loader.py -v
pytest tests/test_rule_checker.py -v
pytest tests/test_main_pipeline.py -v

# 运行指定测试函数
pytest tests/test_json_loader.py::test_init_normal_json -v
```
