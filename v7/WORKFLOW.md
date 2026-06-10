# v7.0 工作流程指南

## 快速启动

```bash
cd v7

# 方式1：干跑测试（无需LLM API Key，验证全管线）
python master_v7.py --dry-run --dxf-dir "C:\Users\azyp\Desktop\医科大图纸DXF"

# 方式2：演示模式（模拟数据+启动Web复核界面）
python master_v7.py --demo --ui --port 8080

# 方式3：完整审查（需LLM API Key）
set ZHIPU_API_KEY=your_key_here
python master_v7.py --dxf-dir "C:\Users\azyp\Desktop\医科大图纸DXF"

# 方式4：仅启动复核界面（已有问题池JSON）
python master_v7.py --review-only output_v7.0/stats/医科大项目_统计.json
```

## 项目结构

```
v7/
├── master_v7.py              # 主控入口（一键串联全流程）
├── config/project_config.yaml # 全局配置（LLM/部署/分类规则）
├── llm/                       # 多模态LLM适配器
├── checkpoints/               # 参数化检查点引擎
│   ├── definitions/           #   检查点YAML定义（按专业）
│   └── templates/             #   Prompt模板
├── preprocessor/              # 图纸预处理（提取+分类+标准化校验）
├── agents/                    # 7个专业Agent + 总工Agent
├── scheduler/                 # Agent集群调度器（并行+异常恢复）
├── problem_pool/              # 统一问题池（溯源链+CAD定位）
├── review_ui/                 # 人工复核Web界面（Flask）
├── audit/                     # 假阴性审计系统
└── output_v7.0/               # 输出目录
    ├── reports/               #   审查报告(Markdown)
    ├── text_extracts/         #   图纸文本提取缓存
    └── stats/                 #   统计数据(JSON)
```

## 完整工作流（6步）

### Step 1: 准备图纸

将DXF文件放入一个目录，建议按专业分文件夹：
```
input/
├── 01基坑支护/
├── 02建筑/
├── 03结构/
├── 04给排水/
├── 06电气/
└── ...
```

### Step 2: 干跑验证（无LLM）

```bash
python master_v7.py --dry-run --dxf-dir "input/"
```

输出: 预处理统计报告 → `output_v7.0/reports/`

### Step 3: 补充检查点（如需）

在 `checkpoints/definitions/` 下创建新YAML：
```yaml
# 结构专业示例: structure.yaml
discipline: structure
checkpoints:
  - id: JG-001
    name: 梁截面尺寸检查
    check_type: dimension_min
    route: dual
    severity: A
    standard_code: GB50010-2010(2015)
    standard_clause: "11.3.5"
    target_object: ["梁", "框架梁"]
    target_property: "截面高度"
    operator: ">="
    limit_value: 400
    unit: mm
```

### Step 4: 配置LLM API Key

```bash
# Windows
set ZHIPU_API_KEY=your_api_key_here

# 或用其他Provider
set DEEPSEEK_API_KEY=sk-xxx
set OPENAI_API_KEY=sk-xxx
```

### Step 5: 运行完整审查

```bash
python master_v7.py --dxf-dir "input/" --output-dir "output_v7.0/"
```

管线自动执行:
1. 预处理: DXF→文本提取+专业分类+标准化校验
2. Agent审查: 7个Agent并行（建筑/结构/暖通/给排水/电气/消防/自由）
3. 总工汇总: 去重→排序→润色→生成报告
4. 审计: 10%抽样假阴性检测

### Step 6: 人工复核

```bash
python master_v7.py --demo --ui --port 8080
# 浏览器打开 http://localhost:8080
```

复核界面操作:
- 逐条审核: 查看溯源链+CAD定位脚本+截图
- 确认/驳回/修改: 一键操作，审计日志自动记录
- 报告导出: 预览→打印PDF

## 审查模式说明

| 模式 | 命令 | LLM调用 | 适用场景 |
|------|------|---------|---------|
| 干跑 | `--dry-run` | 无 | 验证管线/统计图纸/检查分类 |
| 演示 | `--demo` | 无 | 演示UI/生成模拟报告 |
| 完整 | (默认) | 全部 | 真实审查（需API Key） |
| 复核 | `--review-only` | 无 | 仅启动复核界面 |

## 直接LLM审查模式

当没有API Key时，可以直接用AI推理审图：

1. 提取图纸文本: `python master_v7.py --dry-run` → `output_v7.0/text_extracts/`
2. 将文本文件内容提供给LLM（如本对话）
3. LLM直接进行语义分析，生成审查报告

**优势**: 零API成本，秒级响应
**限制**: 需人工将文本传递给LLM，适合小批量审查

## 添加检查点

在 `checkpoints/definitions/` 下按专业创建YAML文件：

```yaml
discipline: 专业名(building/structure/hvac/plumbing/electrical/fire)
checkpoints:
  - id: 检查点编号
    name: 检查点名称
    description: 描述
    check_type: 检查类型（见下表）
    route: 审查路径(text/visual/dual)
    severity: A/B/C/D
    standard_code: 规范编号
    standard_clause: 条款号
    clause_text: 条文全文
    target_object: [检查对象列表]
    target_property: 检查属性
    operator: ">=|<=|==|>|<"
    limit_value: 限值
    unit: 单位
    suggestion_template: 整改建议模板
```

### 支持15种检查类型

| 类型 | 说明 | 示例 |
|------|------|------|
| dimension_min | 最小尺寸 | 疏散门≥900mm |
| dimension_max | 最大尺寸 | 风管≤2500mm |
| dimension_range | 尺寸范围 | 间距2000-3600mm |
| text_presence | 文字必须存在 | 无障碍卫生间须标注 |
| text_absence | 文字不得存在 | 禁用材料检查 |
| value_equal | 值等于 | 防火等级=甲级 |
| value_list | 值在列表中 | 混凝土C25/C30/C35 |
| count_min | 最小数量 | 疏散出口≥2个 |
| spatial_relation | 空间关系 | 间距要求 |
| cross_discipline | 跨专业一致性 | 建筑vs结构标高 |
| fire_rating | 耐火等级 | 防火墙3h |
| slope_check | 坡度检查 | 排水管≥2.6% |
| clearance_check | 净距检查 | 管线净距≥50mm |
| material_spec | 材料规格 | 钢筋HRB400 |
| free_review | 自由审查 | 开放式检查 |

## 项目演进路径

```
v6.0 (废弃)                       v7.0 (当前)
─────────────                     ─────────
ezdxf文本提取           →         保留（增强分类+格式清洗）
正则关键词匹配           →         废弃（→检查点LLM审查）
91条规则循环             →         废弃（→参数化检查点引擎）
BIM三维重建              →         废弃（架构预留IFC接口）
硬编码严重度             →         废弃（→LLM语义评估）
模板建议                 →         废弃（→LLM生成建议）
跨专业正则计数           →         废弃（→总工Agent仲裁）
单文件串行报告           →         废弃（→多角色并行报告+Web复核）

新增模块: 检查点引擎 | Agent集群 | 问题池(溯源链) | 复核UI | 审计系统
```

## 常见问题

**Q: 报错 ModuleNotFoundError: No module named 'v7'**
A: 从 `v7/` 目录运行 `python master_v7.py`

**Q: 审查结果都是"待核实"**
A: 正常——TEXT实体不含图块属性/尺寸标注。需走视觉路径（CAD截图+多模态）

**Q: 如何添加新专业检查点**
A: 在 `checkpoints/definitions/` 创建 `{专业名}.yaml`，参照 `building.yaml`

**Q: 112张图纸需要多久**
A: 预处理~26分钟。LLM审查取决于检查点数量和API速度，建筑5检查点~15元/吨
