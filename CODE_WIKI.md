# AI CAD Audit System - Code Wiki

## 项目概述

**AI CAD Audit System (AI智能审图系统)** 是一个基于 LLM 和计算机视觉的智能建筑图纸审查平台，自动检查建筑设计是否符合中国国家标准（GB标准）。

### 核心能力

- **多专业覆盖**：18个工程专业方向（建筑、结构、暖通、给排水、电气、消防等）
- **条规合规检查**：100+ 内置检查点，映射 GB50016、GB50011、GB50974 等标准
- **DXF/DWG 解析**：自动图纸提取、框架分割、网格分割、比例识别
- **LLM 驱动分析**：双路径架构（规则检查 + 视觉语言模型审查）
- **跨专业验证**：检测不同工程专业之间的冲突
- **专业报告生成**：生成角色化审查报告（总工、专业工程师、交叉检查）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              输入层                                          │
│                    DXF/DWG 图纸文件 (108+ 张)                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           预处理层 (preprocessor)                            │
│  DrawingExtractor → FrameSplitter → GridSplitter → ImageEnhancer            │
│  文本提取 | 框架分割 | 网格分割 | 图像增强 | 标题栏提取 | 标准化校验           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             扫描层 (scanner)                                 │
│                       DrawingScanner - 图纸智能扫描                          │
│                    建筑类型识别 | 风险等级 | 相关专业判断                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Agent 层 (agents)                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ BuildingAgent│ │StructureAgent│ │  HvacAgent   │ │ PlumbingAgent│        │
│  ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤        │
│  │ElectricalAgent│ │  FireAgent   │ │CurtainWallAge│ │DecorationAgt │        │
│  ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤        │
│  │LandscapeAgent│ │FoundatnPitAgt│ │FreeReviewAgt │ │ ChiefAgent   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌──────────────────────────┐ ┌──────────────┐ ┌──────────────────────────┐
│     问题池 (problem_pool) │ │ 跨图纸分析   │ │   假阴性审计 (audit)      │
│    UnifiedIssue Pool     │ │cross_drawing│ │  FalseNegativeAuditor     │
└──────────────────────────┘ └──────────────┘ └──────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          报告层 (report_v7)                                 │
│                    RoleReportGenerator → Markdown/DOCX                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 模块详解

### 1. v7/master_v7.py - 主入口

**职责**：一键串联全流程的主控模块。

**运行模式**：
| 模式 | 命令 | LLM 调用 | 适用场景 |
|------|------|---------|---------|
| 干跑 | `--dry-run` | 无 | 验证管线/统计图纸/检查分类 |
| 演示 | `--demo` | 无 | 演示 UI/生成模拟报告 |
| 完整 | (默认) | 全部 | 真实审查（需 API Key） |
| 复核 | `--review-only` | 无 | 仅启动复核界面 |

**核心流程**：
```
1. 图纸预处理 → 2. Agent 审查 → 3. 总工汇总 → 4. 假阴性审计
```

**关键函数**：
- `run_dry_run(args)` - 干跑模式验证
- `run_full(args)` - 完整三阶段管线
- `run_demo(args)` - 演示模式
- `main()` - 命令行入口

---

### 2. v7/llm/ - LLM 适配器工厂

**文件结构**：
```
llm/
├── __init__.py      # LLMFactory 工厂类
├── base_adapter.py # 抽象基类
├── text_adapter.py # 文本 LLM 适配器
└── vision_adapter.py # 视觉 LLM 适配器
```

**LLMFactory**：
- 单例模式实现
- 支持多 Provider 路由（智谱/DeepSeek/OpenAI/Ollama）
- 自动故障转移（主模型失效 → 备用模型）
- API 限流控制

**关键方法**：
```python
get_text_adapter(provider="") -> TextAdapter
get_vision_adapter(provider="", complex_mode=False) -> VisionAdapter
call_with_failover(prompt, system, mode, image_paths) -> (result, provider)
```

**环境变量**：
- `ZHIPU_API_KEY` - 智谱 API Key
- `DEEPSEEK_API_KEY` - DeepSeek API Key
- `OPENAI_API_KEY` - OpenAI API Key

---

### 3. v7/checkpoints/ - 检查点引擎

**文件结构**：
```
checkpoints/
├── __init__.py
├── checkpoint_schema.py  # 数据模型定义
├── engine.py             # 检查点执行引擎
├── templates/
│   └── prompt_templates.py
└── definitions/          # YAML 规则文件
    ├── building.yaml
    ├── structure.yaml
    ├── fire.yaml
    └── ...
```

**15 种检查类型** (`CheckType`)：
| 类型 | 说明 | 示例 |
|------|------|------|
| `dimension_min` | 最小尺寸 | 疏散门 ≥ 900mm |
| `dimension_max` | 最大尺寸 | 风管 ≤ 2500mm |
| `dimension_range` | 尺寸范围 | 间距 2000-3600mm |
| `text_presence` | 文字必须存在 | 无障碍卫生间须标注 |
| `text_absence` | 文字不得存在 | 禁用材料检查 |
| `value_equal` | 值等于 | 防火等级 = 甲级 |
| `value_list` | 值在列表中 | 混凝土 C25/C30/C35 |
| `count_min` | 最小数量 | 疏散出口 ≥ 2 个 |
| `spatial_relation` | 空间关系 | 间距要求 |
| `cross_discipline` | 跨专业一致性 | 建筑 vs 结构标高 |
| `fire_rating` | 耐火等级 | 防火墙 3h |
| `slope_check` | 坡度检查 | 排水管 ≥ 2.6% |
| `clearance_check` | 净距检查 | 管线净距 ≥ 50mm |
| `material_spec` | 材料规格 | 钢筋 HRB400 |
| `free_review` | 自由审查 | 开放式检查 |

**路由策略** (`Route`)：
- `TEXT` - 仅文本路径
- `VISUAL` - 仅视觉路径
- `DUAL` - 双路径验证（A/B 级强制升级为 DUAL）

**严重度等级** (`Severity`)：
- `A` - 强条违反（必须整改）
- `B` - 重要问题（建议整改）
- `C` - 一般问题（提示关注）
- `D` - 信息补充

**CheckpointEngine 核心方法**：
```python
execute_one(checkpoint, text_context, image_paths) -> CheckResult
execute_batch(checkpoints, text_context, image_paths, max_concurrent=5) -> List[CheckResult]
execute_by_discipline(discipline, text_context, image_paths) -> List[CheckResult]
list_by_discipline(discipline) -> List[CheckpointDefinition]
resolve_route(cp) -> Route  # A/B 级强制 DUAL
```

---

### 4. v7/agents/ - Agent 集群

**文件结构**：
```
agents/
├── __init__.py
├── base_agent.py         # 基类
├── discipline_agents.py  # 11 个专业 Agent
└── chief_agent.py        # 总工 Agent
```

**BaseAgent**：
```python
class BaseAgent(ABC):
    config: AgentConfig
    engine: CheckpointEngine

    def build_system_prompt() -> str  # 抽象：构建角色 Prompt
    def filter_drawings(drawings) -> List  # 抽象：过滤本专业图纸
    def execute(drawings, problem_pool, image_paths) -> AgentReport
    def get_checkpoints() -> List[CheckpointDefinition]
```

**专业 Agent 列表**：
| Agent | discipline | 职责 |
|-------|------------|------|
| `BuildingAgent` | building | 建筑专业审查 |
| `StructureAgent` | structure | 结构专业审查 |
| `HvacAgent` | hvac | 暖通空调审查 |
| `PlumbingAgent` | plumbing | 给排水审查 |
| `ElectricalAgent` | electrical | 电气专业审查 |
| `FireAgent` | fire | 消防专业审查 |
| `CurtainWallAgent` | curtain_wall | 幕墙审查 |
| `DecorationAgent` | decoration | 装饰装修审查 |
| `LandscapeAgent` | landscape | 景观绿化审查 |
| `FoundationPitAgent` | foundation_pit | 基坑支护审查 |
| `FreeReviewAgent` | free_review | 自由审查 |
| `ChiefAgent` | - | 总工汇总（跨专业协调） |

**ChiefAgent** 职责：
- 汇总所有专业 Agent 发现
- 跨专业冲突仲裁
- 去重、排序、润色报告

---

### 5. v7/scheduler/ - Agent 调度器

**AgentOrchestrator**：
```python
class AgentOrchestrator:
    def execute_parallel(drawings, problem_pool, image_paths) -> OrchestrationReport
    def execute_sequential(drawings, problem_pool, image_paths) -> OrchestrationReport
    def execute_smart(drawings, problem_pool, image_paths, scan_result) -> OrchestrationReport
```

**调度策略**：
- `execute_parallel` - 11 个 Agent 并行执行
- `execute_sequential` - 按优先级顺序执行
- `execute_smart` - 根据扫描结果智能调度

---

### 6. v7/preprocessor/ - 图纸预处理

**文件结构**：
```
preprocessor/
├── __init__.py
├── drawing_extractor.py    # DXF 文本提取
├── drawing_pipeline.py      # 完整预处理管线
├── frame_splitter.py        # 框架分割
├── grid_splitter.py         # 网格分割
├── image_enhancer.py        # 图像增强
├── title_block_extractor.py # 标题栏提取
├── standardization_checker.py # 标准化校验
├── cad_printer.py          # CAD 打印
├── dwg_converter.py        # DWG 转换
└── dwg_subset_splitter.py  # DWG 子集分割
```

**DrawingExtractor**：
```python
class DrawingExtractor:
    def process_drawing(dxf_path, png_output_dir=None) -> DrawingInfo
    def classify(filename) -> str  # 按文件名分类专业
    def extract_text_entities(dxf_path) -> List[TextEntity]
```

**DrawingInfo** 数据结构：
```python
@dataclass
class DrawingInfo:
    filename: str
    readable_name: str
    discipline: str
    text_entities: List[TextEntity]
    text_content: str
    png_path: Optional[str]
    png_paths: List[str]
```

**TextEntity** 数据结构：
```python
@dataclass
class TextEntity:
    entity_handle: str
    text: str
    x: float
    y: float
    layer: str
    color: str
    entity_type: str
    source_file: str
```

---

### 7. v7/problem_pool/ - 统一问题池

```python
class ProblemPool:
    def add_issue(issue: UnifiedIssue)
    def add_from_checkpoint(result, text_entity, agent_name)
    def record_compliance(checkpoint_id, ...)
    def get_compliant_results() -> List
    def stats() -> Dict
    def count_by_severity() -> Dict
    def count_dual_verified() -> int
```

**UnifiedIssue** 数据模型：
```python
@dataclass
class UnifiedIssue:
    issue_id: str
    checkpoint_id: str
    checkpoint_name: str
    discipline: str
    professional: str
    description: str
    severity: str  # A/B/C/D
    suggestion: str
    standard_code: str
    standard_clause: str
    drawing_name: str
    location: str
    cad_script: str  # CAD 定位脚本
    confidence: str
    route_used: str  # text/visual/dual
    provenance: Provenance
```

**Provenance** (溯源链)：
```python
@dataclass
class Provenance:
    data_source: DataSource
    verification: Optional[Verification]
    processor_steps: List[ProcessorStep]
```

---

### 8. v7/scanner/ - 图纸智能扫描

```python
class DrawingScanner:
    def scan(merged_text) -> ScanResult
```

**ScanResult**：
```python
@dataclass
class ScanResult:
    building_type: str       # 建筑类型
    risk_level: str         # low/medium/high
    relevant_disciplines: List[str]
    suggested_skip_disciplines: List[str]
    priority_tags: List[str]
    visual_required: bool
    scan_time_ms: float
    notes: str
```

---

### 9. v7/cross_drawing/ - 跨图纸分析

```python
class CrossDrawingContext:
    def add_drawing(name, discipline, text_content)
    def get_context_summary() -> str
    def analyze() -> List[CrossDrawingIssue]
```

---

### 10. v7/audit/ - 假阴性审计

```python
class FalseNegativeAuditor:
    def audit() -> AuditReport
```

抽样检测已通过的检查点，识别潜在的假阴性（false negative）。

---

### 11. v7/report_v7/ - 报告生成

```python
class RoleReportGenerator:
    def generate_chief_report(pool, project_name, coverage_stats) -> ChiefReport
    def generate_discipline_reports(pool) -> List
```

---

### 12. v7/admin/ - 管理后台

基于 http.server 的管理界面。

**页面模块** (`pages/`)：
- `drawings.py` - 图纸管理
- `rules.py` - 规则管理
- `agents.py` - Agent 配置
- `api_config.py` - API 配置
- `results.py` - 审查结果
- `system.py` - 系统设置

**启动**：`python v7/admin/server.py`

---

### 13. v7/review_ui/ - 人工复核界面

基于 Flask 的 Web 复核界面。

```python
def run_server(pool, project_name, port, output_dir)
```

**功能**：
- 逐条审核问题
- 查看溯源链 + CAD 定位脚本
- 确认/驳回/修改
- 报告导出

**启动**：`python -m v7.review_ui.app` 或 `master_v7.py --demo --ui`

---

### 14. v7/db/ - 数据库层

SQLite 数据库 schema。

**核心表**：
| 表名 | 用途 |
|------|------|
| `projects` | 项目定义 |
| `drawings` | 图纸文件记录 |
| `checkpoints` | 检查点规则 |
| `agent_configs` | Agent 配置 |
| `api_keys` | LLM API 密钥（加密） |
| `reviews` | 审查会话 |
| `review_issues` | 审查问题明细 |
| `config_versions` | 配置变更历史 |
| `settings` | 系统设置 |

---

## 配置文件

### v7/config.yaml

空间分析配置：
- `floor_map` - 楼层名称映射
- `discipline_rules` - 专业分类规则（按文件名前缀）
- `layer_rules` - 图层分类规则
- `conflict_rules` - 冲突检测规则
- `runtime` - 运行时参数

### v7/config/project_config.yaml

LLM 配置：
- `llm.deployment.mode` - 部署模式（local/hybrid/cloud）
- `llm.providers` - Provider 配置
- `llm.routing` - 路由策略

---

## 依赖关系

```
requirements.txt
├── python-docx>=0.8.11       # 报告生成
├── ezdxf>=1.2.0              # DXF/DWG 解析
├── numpy>=1.24.0             # 数值计算
├── scipy>=1.10.0             # 科学计算
├── scikit-learn>=1.2.0       # 机器学习
├── rtree>=1.1.0              # 空间索引
├── shapely>=2.0.1            # 几何计算
├── pyyaml>=6.0               # YAML 解析
├── requests>=2.28.0          # HTTP 客户端
├── cryptography>=41.0.0      # 配置加密
├── flask>=3.0.0              # Web UI
└── openai>=1.0.0            # LLM API
```

---

## 运行方式

### 环境准备

```bash
# Python 3.10+
python --version

# 安装依赖
pip install -r requirements.txt
```

### 配置 API Key

```bash
# 方式1：智谱 AI（推荐国内用户）
export ZHIPU_API_KEY="your-api-key"

# 方式2：DeepSeek
export DEEPSEEK_API_KEY="your-api-key"

# 方式3：OpenAI
export OPENAI_API_KEY="your-api-key"
```

### 运行模式

```bash
cd v7

# 完整审查（需 DXF 文件 + LLM API Key）
python master_v7.py --dxf-dir "input/" --output-dir "output_v7.0/"

# 干跑测试（无 LLM，验证管线）
python master_v7.py --dry-run --dxf-dir "input/"

# 演示模式（模拟数据 + Web 界面）
python master_v7.py --demo --ui --port 8080

# 仅启动复核界面（使用已有问题池）
python master_v7.py --review-only output_v7.0/stats/项目_统计.json
```

### Web 服务

```bash
# 管理后台
python v7/admin/server.py

# 复核界面
python v7/review_ui/app.py
```

---

## 项目结构

```
AI-CAD-Audit-System/
├── v7/                         # 主代码目录
│   ├── master_v7.py           # 主入口
│   ├── config.yaml            # 空间分析配置
│   ├── config/                # 配置目录
│   │   └── project_config.yaml # LLM 配置
│   ├── llm/                   # LLM 适配器
│   ├── checkpoints/           # 检查点引擎
│   │   ├── definitions/       # YAML 规则
│   │   └── templates/         # Prompt 模板
│   ├── agents/                # Agent 集群
│   ├── scheduler/             # 调度器
│   ├── preprocessor/          # 预处理
│   ├── scanner/               # 图纸扫描
│   ├── problem_pool/          # 问题池
│   ├── audit/                 # 假阴性审计
│   ├── cross_drawing/         # 跨图纸分析
│   ├── report_v7/             # 报告生成
│   ├── admin/                 # 管理后台
│   ├── review_ui/             # 复核界面
│   └── db/                    # 数据库
├── tests/                     # 测试
├── docs/                      # 文档
├── config/                    # 配置模板
├── scripts/                   # 工具脚本
└── requirements.txt           # 依赖
```

---

## 关键数据流

```
DXF 文件
    │
    ▼
DrawingExtractor.process_drawing()
    │
    ├──► DrawingInfo (filename, discipline, text_entities)
    │
    ▼
DrawingScanner.scan()
    │
    └──► ScanResult (building_type, risk_level, relevant_disciplines)
    │
    ▼
AgentOrchestrator.execute_smart()
    │
    ├──► 11 个专业 Agent 并行执行
    │        │
    │        ▼
    │    CheckpointEngine.execute_one()
    │        │
    │        ├──► Text 路径 → TextAdapter.ask_with_retry()
    │        │
    │        └──► Visual 路径 → VisionAdapter.ask_with_retry()
    │
    ▼
ProblemPool (UnifiedIssue 集合)
    │
    ├──► CrossDrawingContext.analyze()
    │
    ├──► FalseNegativeAuditor.audit()
    │
    └──► ChiefAgent.execute()
             │
             ▼
        ChiefReport (Markdown)
```
