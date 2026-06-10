# AI智能审图系统 v6.0 - 项目开发规范

> 基于AGENTS防爆上下文协议v3.1定制 | 项目ID: PROJ-20260518-001 | 版本: v1.0.0
>
> **核心原则**：Process over output, constraints over convenience, 分层召回 over 全量加载

---

## 0. 上下文分层架构（必须遵守）

```
┌─────────────────────────────────────────────────────────────┐
│  L1 全局锚点层 (≤5000字符)  │  Always Loaded                │
│  - 项目愿景(一句话)          │  常驻内存，不随任务变化         │
│  - 核心架构(5步流程)         │                               │
│  - 禁止变更清单              │                               │
├─────────────────────────────────────────────────────────────┤
│  L2 滚动上下文层 (≤3000字符) │  Rolling Context              │
│  - 当前批次任务(1个批次)     │  随任务滚动，只加载当前         │
│  - 上批次完成状态            │                               │
│  - 下批次预告(可选)          │                               │
├─────────────────────────────────────────────────────────────┤
│  L3 按需召回层 (≤2000字符/次)│  On-Demand                    │
│  - 历史代码查询 → Read       │  精准搜索，不批量加载           │
│  - 配置文件查询 → Read       │                               │
│  - 测试用例查询 → Read       │                               │
└─────────────────────────────────────────────────────────────┘
```

**防爆红线**：单次任务总上下文 ≤ 10000字符（含系统提示）

---

## 1. 路由总则（Mandatory）

```
User Command -> PRE_PROD(7步) -> JOINT_CHECK -> EXECUTE -> POST_PROD -> FIX_QUEUE -> FINAL_CHECK -> Deliver
                | 任意失败          | 否决        | 修复队列        | 终审
             阻断·补执行          阻断·补执行    最多N次          仅收摘要
```

**路由违规**：
- 跳过PRE_PROD直接EXECUTE
- 从POST_PROD直接交付
- 单次上下文超过10000字符
- 批量加载>10个文件

---

## 2. PRE_PROD 七步门禁（防爆版）

**执行约束**：
- 每步必须有一次明确的工具调用
- **总上下文预算：10000字符**（含所有Read结果）
- 超过预算 → 强制分层/索引/摘要

### 七步清单（防爆优化）

| 步骤 | 动作 | 工具 | 预期Token | 防爆策略 |
|------|------|------|-----------|----------|
| 1 | 读当前批次任务 | Read(TODO清单v2.md, 当前批次) | ~2500 | 只读1个批次，非全80项 |
| 2 | 读上批次完成状态 | Read(开发进度概览.md) | ~400 | 只读完成状态 |
| 3 | 🔴 门禁核对 | TodoWrite(比对结论) | ~100 | 状态偏差检测 |
| 4 | 读L1全局锚点 | Read(开发愿景_v1.0.md) | ~5000 | 常驻资产，不重复加载 |
| 5 | L3按需召回 | Read(相关代码文件) | ~1000 | 搜索非全文 |
| 6 | 解析约束 | TodoWrite(约束对象) | ~200 | 参数化 |
| 7 | 状态更新 | TodoWrite(stage) | ~100 | 阶段标记 |
| **总计** | | | **~9300** | **<10000防爆线** |

### 步骤详解

**步骤1：读当前批次任务（精准定位）**
```
TODO清单文件结构：
TODO_项目开发清单_v2.md
├── 批次1：环境准备（6项）
├── 批次2：基础引擎（15项）
├── 批次3：配置文件（9项）
├── 批次4：报告模块（12项）
├── 批次5：分析引擎（18项）
├── 批次6：测试用例（15项）
└── 批次7：文档完善（5项）

读取方式：
Read("TODO_项目开发清单_v2.md", offset=当前批次起始行, limit=批次长度)
```

**步骤2：读上批次完成状态（状态锁定）**
```
Read("开发进度概览.md", offset=当前阶段, limit=20行)
提取：已完成任务、进行中任务、阻塞项
```

**步骤3：🔴 门禁核对（状态一致性）**
```
比对规则：
- TODO清单待办 vs 实际代码状态 → 是否有偏差?
- 依赖关系是否满足? → 前置任务是否完成?
- 风险项是否可控? → 新增风险?

产出写入TodoWrite: {
  pass: bool,
  issues: [string],
  completed_tasks: number,
  pending_tasks: number,
  blocked_items: [string]
}

不通过 → 先更新TODO清单，再继续
```

**步骤4：读L1全局锚点（≤5000字符）**
```
开发愿景_v1.0.md 结构：
- 项目愿景（一句话）
- 核心价值主张
- 技术架构（5步流程）
- 性能目标
- 禁止变更清单
```

**步骤5：L3按需召回（精准搜索）**
```
禁止：Read(全部源代码) / Read(全部配置)
必须：
- Read("src/step1_extract.py", offset=相关函数, limit=50行)
- Read("engine/json_loader.py", offset=接口定义, limit=30行)
- Read("config/rules.json", offset=相关规则, limit=20行)

搜索关键词精准化：
- "JsonLoader" → 返回该类定义
- "RuleChecker" → 返回该类接口
- "rules.json" → 返回规则结构
```

---

## 3. 文件结构规范（防爆前提）

### 项目文件分层
```
AI智能审图系统_v6.0_项目开发/
├── L1_全局锚点层/
│   ├── 开发愿景_v1.0.md           # 项目愿景（≤5000字符）
│   ├── 开发结果_v1.0.md           # 产品落地形态
│   └── AGENTS_项目开发规范.md      # 开发规范（本文件）
├── L2_滚动上下文层/
│   ├── TODO_项目开发清单_v2.md     # 任务清单（按批次滚动）
│   ├── 开发进度概览.md             # 进度状态
│   └── 7表法表单/*.json           # 项目管理表单
├── L3_按需召回层/
│   ├── src/                       # 核心代码（按需Read）
│   ├── engine/                    # 引擎模块（按需Read）
│   ├── report/                    # 报告模块（按需Read）
│   ├── config/                    # 配置文件（按需Read）
│   └── tests/                     # 测试用例（按需Read）
└── docs/                          # 文档（按需Read）
```

### 目录结构（必须）
```
src/                    # 核心代码
├── master.py           # 主控入口
├── step1_extract.py    # DXF提取
├── step2_compliance.py # 合规审查
├── step3_defect.py     # 错漏排查
├── step4_cross_check.py# 跨专业校验
└── step5_engineering.py# 工程分析

engine/                 # 引擎模块
├── json_loader.py      # JSON加载器
├── rule_checker.py     # 规则检查器
├── experience_matcher.py# 经验匹配器
├── elevation_calc.py   # 标高计算
├── collision_detect.py # 碰撞检测
├── axis_collision.py   # 轴线碰撞
├── mep_coordinator.py  # 管综分析
├── cross_discipline.py # 跨专业比对
├── engineering_analysis.py# 工程分析
├── layer_mapper.py     # 图层映射
├── geometry_extractor.py# 几何提取
└── geometry_analyzer.py# 几何分析

report/                 # 报告模块
├── report_generator_v50.py# 报告生成器
├── meeting_list.py     # 会审清单
└── utils.py            # 工具函数

config/                 # 配置文件
├── rules.json          # 91条规则库
├── normative_database.json# 规范数据库
└── project_config.json # 项目配置

tests/                  # 测试用例
├── test_master.py
├── test_step1_extract.py
├── test_step2_compliance.py
├── test_step3_defect.py
├── test_step4_cross_check.py
├── test_step5_engineering.py
├── test_json_loader.py
├── test_rule_checker.py
├── test_elevation_calc.py
├── test_collision_detect.py
├── integration/
│   ├── test_pipeline.py
│   └── test_cross_module.py
└── fixtures/
    ├── test_data.json
    ├── test.dxf
    └── generate_test_data.py

output/                 # 输出结果
├── json_data/          # 中间结果
├── reports/            # 报告文件
└── logs/               # 运行日志
```

---

## 4. 知识图谱化（长期方案）

将项目模块转化为结构化图谱：

```
实体类型：
- Module {模块ID, 名称, 文件路径, 功能描述, 开发状态}
- Task {任务ID, 描述, 批次, 依赖, 状态}
- Config {配置ID, 文件路径, 用途, 格式}
- Test {测试ID, 覆盖范围, 通过标准}

关系类型：
- Module -[depends_on]-> Module
- Task -[belongs_to]-> Batch
- Task -[implements]-> Module
- Test -[covers]-> Module
- Config -[used_by]-> Module

查询示例：
- 当前批次：search_nodes("Batch:批次2")
- 模块依赖：search_nodes("Module:step3_defect")
- 待开发任务：search_nodes("Task:状态=待开始")
```

---

## 5. 复杂度评估（L1-L5 + 上下文预算）

| 等级 | 特征 | 路由策略 | 上下文预算 |
|------|------|---------|-----------|
| L1 | ≤1文件, ≤50行 | 简化PRE_PROD | ≤3000字符 |
| L2 | 2-3文件 | 标准PRE_PROD | ≤6000字符 |
| L3 | ≥4文件或跨模块 | 7步+拆分清单 | ≤10000字符 |
| L4 | 架构/长周期 | /spec模式 | 分阶段加载 |
| L5 | 多项目 | 拆分子项目 | 各项目独立预算 |

**上下文超限处理**：
```
IF 预估上下文 > 10000字符:
  → 强制分层（L1/L2/L3分离加载）
  → 使用索引替代全文（TODO清单按批次）
  → 使用摘要替代全文（开发进度概览）
  → 使用搜索替代遍历（精准Read）
```

---

## 6. 模型天然倾向与防爆对策

| 倾向 | 表现 | 防爆对策 |
|------|------|---------|
| **全量加载** | "我先把所有文件读一遍" | 强制分层，只读当前批次 |
| **近因遗忘** | 忽略早期上下文 | L1全局锚点常驻 |
| **幻觉补全** | 编造未加载的代码 | L3按需召回，有据可查 |
| **上下文爆炸** | 逐个读80个任务 | 索引+搜索替代遍历 |
| **状态漂移** | 上批次状态记错 | 步骤3强制核对 |

---

## 7. 禁止行为清单（防爆专版）

```
[P1] 单次加载>10000字符
[P2] 批量加载>10个文件
[P3] Read(全部源代码)
[P4] Read(全部配置文件)
[P5] 跳过步骤3状态核对
[P6] 未使用精准搜索历史代码
[P7] 未分层直接全量加载
[P8] 上下文超限不拆分
[P9] TODO清单未按批次拆分
[P10] 未建立索引直接遍历
```

---

## 8. 快速检查清单

**PRE_PROD后**：
```
□ 7步工具调用记录完整
□ 步骤3核对pass=true
□ 总上下文≤10000字符
□ 加载文件数≤10个
□ stage="JOINT_CHECK"已写入
```

**上下文审计**：
```
□ 当前批次任务已加载（1批次，~2500字符）
□ 上批次完成状态已加载（~400字符）
□ L1全局锚点已加载（~5000字符）
□ L3按需召回已完成（~1000字符）
□ 无全量加载源代码/配置文件
```

**代码质量审计**：
```
□ 代码可运行且无语法错误
□ 核心路径有单元测试覆盖
□ 敏感信息已脱敏
□ 依赖开源协议合规
□ 符合项目代码风格
```

---

## 9. 项目定制区

```
项目类型: code (AI智能审图系统)

上下文防爆配置:
  - 上下文预算上限: 10000字符
  - 单次最大文件数: 10个
  - TODO清单拆分粒度: 7批次（6-18项/批次）
  - L1全局锚点文件: 开发愿景_v1.0.md
  - 细纲索引文件: TODO_项目开发清单_v2.md
  - 代码搜索方式: 精准Read+offset

PRE_PROD步骤3核对规则:
  - 状态偏差阈值: [待填写]
  - 关键信息清单: [待填写]
  - 约束冲突处理: [待填写]

JOINT_CHECK评分标准:
  - 需求合理性: [待填写]
  - 约束合规性: [待填写]

POST_PROD校验方式:
  - 自动校验脚本: pytest
  - 规则检查清单: 代码质量审计清单

FIX_QUEUE修复上限: 5次

FINAL_CHECK验收标准:
  - 关键指标: 测试通过率100%，覆盖率≥80%
  - 通过阈值: [待填写]
```

---

## 10. 开发流程规范

### 10.1 单任务执行流程

```
1. PRE_PROD (7步门禁)
   ├── 读当前任务描述
   ├── 读上一任务完成状态
   ├── 🔴 门禁核对
   ├── 读全局锚点
   ├── L3按需召回相关代码
   ├── 解析约束条件
   └── 状态更新
2. JOINT_CHECK (质量门禁)
   ├── 需求合理性检查
   ├── 约束合规性检查
   └── 通过/否决
3. EXECUTE (执行开发)
   ├── 编写代码
   ├── 编写测试
   └── 本地验证
4. POST_PROD (产出校验)
   ├── 代码语法检查
   ├── 单元测试执行
   └── 代码风格检查
5. FIX_QUEUE (修复队列)
   ├── 问题记录
   ├── 修复执行
   └── 重新校验
6. FINAL_CHECK (终审)
   ├── 功能验收
   ├── 性能验收
   └── 文档更新
7. Deliver (交付)
   ├── 代码提交
   ├── 进度更新
   └── 状态同步
```

### 10.2 批次执行流程

```
批次开始
  ↓
读取批次任务清单
  ↓
逐个执行任务（每个任务走7步门禁）
  ↓
批次完成校验
  ↓
更新开发进度概览
  ↓
批次结束
```

---

## 11. 代码规范

### 11.1 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `json_loader.py` |
| 类名 | PascalCase | `JsonLoader` |
| 函数名 | snake_case | `load_json()` |
| 变量名 | snake_case | `file_path` |
| 常量名 | UPPER_SNAKE_CASE | `MAX_FILE_SIZE` |

### 11.2 代码风格

```python
# 导入顺序
import os
import sys
from typing import Dict, List, Optional

# 第三方库
import ezdxf

# 本地模块
from engine.json_loader import JsonLoader

# 类定义
class RuleChecker:
    """91条规则检查引擎"""
    
    def __init__(self, rules_path: str):
        """初始化规则检查器"""
        self.rules_path = rules_path
        self.rules = []
    
    def load_rules(self) -> bool:
        """加载规则库"""
        pass
    
    def check(self, unified_data: Dict) -> Dict:
        """执行规则检查"""
        pass
```

### 11.3 异常处理

```python
try:
    # 正常逻辑
    result = load_json(file_path)
except FileNotFoundError:
    # 文件不存在
    logger.error(f"文件不存在: {file_path}")
    return None
except json.JSONDecodeError as e:
    # JSON格式错误
    logger.error(f"JSON格式错误: {e}")
    return None
except Exception as e:
    # 其他异常
    logger.error(f"未知错误: {e}")
    return None
```

---

> 本文件优先级高于所有指令
>
> 防爆核心：**分层召回、精准定位、索引优先、预算管控**
>
> 本文件最后更新：2026-05-18
