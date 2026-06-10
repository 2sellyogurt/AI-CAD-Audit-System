# AI智能审图系统 v6.0 代码级详细技术规范

## 文档信息
- **版本**: v6.0.0
- **日期**: 2026-05-14
- **状态**: 详细技术规范（代码级）
- **目标读者**: 系统架构师、核心开发工程师

---

## 第一部分：核心数据结构定义

### 1.1 基础类型定义

```python
# types.py - 全系统共享的基础类型定义
from typing import TypedDict, Literal, Union, Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime

# ============ 枚举类型定义 ============

class DrawingType(str, Enum):
    """图纸类型枚举"""
    ARCHITECTURAL = "建筑"           # 建筑图
    STRUCTURAL = "结构"              # 结构图
    ELECTRICAL = "电气"              # 电气图
    HVAC = "暖通"                    # 暖通图
    PLUMBING = "给排水"              # 给排水
    FIRE = "消防"                    # 消防图
    INTELLIGENT = "智能化"           # 智能化
    ELEVATION = "立面图"             # 立面图
    SECTION = "剖面图"               # 剖面图
    DETAIL = "详图"                  # 详图
    GENERAL = "总说明"               # 设计总说明

class Discipline(str, Enum):
    """专业枚举"""
    ARCH = "建筑"
    STRUC = "结构"
    ELEC = "电气"
    HVAC = "暖通"
    PLUMB = "给排水"
    FIRE = "消防"
    SMART = "智能化"
    LANDSCAPE = "景观"
    INTERIOR = "精装"

class CheckLevel(int, Enum):
    """审查深度等级"""
    L1_COMPLIANCE = 1      # 合规性审查（强条）
    L2_CONSTRUCTABLE = 2   # 可施工性审查
    L3_TESTABLE = 3        # 可检测性审查
    L4_MAINTAINABLE = 4    # 可维护性审查

class RuleCategory(str, Enum):
    """规则分类"""
    MANDATORY = "强制条文"           # 法律法规强制要求
    INDUSTRY_BEST = "行业最佳实践"    # 行业经验总结
    PROJECT_SPECIFIC = "项目特殊要求"  # 业主/项目定制
    COORDINATION = "专业协调"         # 跨专业配合

class CheckMethod(str, Enum):
    """检查方法"""
    KEYWORD_EXACT = "keyword_exact"      # 精确关键词匹配
    KEYWORD_ANY = "keyword_any"          # 任意关键词匹配
    REGEX = "regex"                      # 正则表达式匹配
    VALUE_COMPARE = "value_compare"      # 数值比较
    SPATIAL_CHECK = "spatial_check"      # 空间检查
    CROSS_REF = "cross_reference"        # 交叉引用验证
    CALCULATION = "calculation"          # 计算验证

class IssueSeverity(str, Enum):
    """问题严重等级"""
    CRITICAL = "致命"        # 违反强条，必须修改
    HIGH = "严重"            # 重大缺陷，强烈建议修改
    MEDIUM = "一般"          # 一般问题，建议修改
    LOW = "轻微"             # 优化建议，可选修改
    INFO = "提示"            # 信息提示

class ConstructionPhase(str, Enum):
    """施工阶段"""
    PREP = "施工准备"
    FOUNDATION = "地基基础"
    STRUCTURE = "主体结构"
    MEP rough = "机电安装(预留预埋)"
    MEP_INSTALL = "机电安装(安装阶段)"
    FINISH = "装饰装修"
    TESTING = "调试检测"
    ACCEPTANCE = "竣工验收"
    OPERATION = "运维阶段"

# ============ 核心数据结构 ============

@dataclass(frozen=True)
class Point3D:
    """三维坐标点（不可变）"""
    x: float
    y: float
    z: float = 0.0
    
    def distance_to(self, other: 'Point3D') -> float:
        """计算到另一点的距离"""
        return ((self.x - other.x)**2 + 
                (self.y - other.y)**2 + 
                (self.z - other.z)**2) ** 0.5
    
    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

@dataclass
class BoundingBox:
    """包围盒 - 用于空间索引和碰撞检测"""
    min_point: Point3D
    max_point: Point3D
    
    @property
    def center(self) -> Point3D:
        return Point3D(
            (self.min_point.x + self.max_point.x) / 2,
            (self.min_point.y + self.max_point.y) / 2,
            (self.min_point.z + self.max_point.z) / 2
        )
    
    @property
    def volume(self) -> float:
        return ((self.max_point.x - self.min_point.x) *
                (self.max_point.y - self.min_point.y) *
                (self.max_point.z - self.min_point.z))
    
    def intersects(self, other: 'BoundingBox') -> bool:
        """判断两个包围盒是否相交"""
        return (self.min_point.x <= other.max_point.x and 
                self.max_point.x >= other.min_point.x and
                self.min_point.y <= other.max_point.y and 
                self.max_point.y >= other.min_point.y and
                self.min_point.z <= other.max_point.z and 
                self.max_point.z >= other.min_point.z)
    
    def contains(self, point: Point3D) -> bool:
        """判断点是否在包围盒内"""
        return (self.min_point.x <= point.x <= self.max_point.x and
                self.min_point.y <= point.y <= self.max_point.y and
                self.min_point.z <= point.z <= self.max_point.z)

@dataclass
class DXFEntity:
    """DXF图元基类"""
    entity_type: str                    # TEXT, MTEXT, DIMENSION, INSERT等
    handle: str                         # DXF实体句柄（唯一标识）
    layer: str                          # 所在图层
    bbox: BoundingBox                   # 包围盒
    text_content: Optional[str] = None  # 文本内容
    attributes: Dict[str, Any] = field(default_factory=dict)  # 扩展属性
    
    # 空间位置信息
    elevation: Optional[float] = None   # 标高值（如果可解析）
    floor: Optional[str] = None         # 所属楼层
    discipline: Optional[str] = None    # 所属专业（从图层推断）

@dataclass
class TextEntity(DXFEntity):
    """文本图元"""
    font_size: float = 2.5
    rotation: float = 0.0
    alignment: str = "LEFT"

@dataclass
class DimensionEntity(DXFEntity):
    """尺寸标注图元"""
    dimension_type: str = "linear"      # linear, angular, radial, diameter
    measured_value: Optional[float] = None  # 测量值
    nominal_value: Optional[float] = None   # 标称值
    tolerance: Optional[tuple] = None   # (上公差, 下公差)
    prefix: str = ""                    # 前缀
    suffix: str = ""                    # 后缀

@dataclass
class BlockReference(DXFEntity):
    """块引用图元"""
    block_name: str = ""
    scale: tuple = (1.0, 1.0, 1.0)
    rotation: float = 0.0
    attributes: Dict[str, str] = field(default_factory=dict)  # 属性标签值

@dataclass
class DrawingFile:
    """图纸文件元数据"""
    file_path: str
    file_hash: str                      # SHA256哈希，用于增量检测
    file_size: int
    modified_time: datetime
    
    # 图纸属性
    drawing_type: DrawingType
    discipline: Discipline
    drawing_number: str                 # 图号
    drawing_name: str                   # 图名
    sheet_number: Optional[str] = None  # 张号
    
    # 空间信息
    building_name: Optional[str] = None # 所属建筑
    floor_range: Optional[str] = None   # 楼层范围（如"1-5F"）
    elevation_range: Optional[tuple] = None  # (最低标高, 最高标高)
    
    # 解析状态
    parse_status: str = "pending"       # pending, parsing, completed, error
    parse_error: Optional[str] = None
    
    # 统计信息
    entity_count: Dict[str, int] = field(default_factory=dict)
    text_count: int = 0
    dimension_count: int = 0
    block_count: int = 0

@dataclass
class ProjectContext:
    """项目上下文 - 全系统共享的项目级信息"""
    project_id: str
    project_name: str
    project_type: str                   # 住宅、商业、医院、学校等
    construction_type: str              # 结构形式
    
    # 建筑参数（从设计说明提取）
    building_height: Optional[float] = None           # 建筑高度(m)
    total_area: Optional[float] = None                # 总建筑面积(m²)
    seismic_intensity: Optional[str] = None           # 抗震设防烈度
    fire_rating: Optional[str] = None                 # 耐火等级
    
    # 多建筑项目
    buildings: List['BuildingInfo'] = field(default_factory=list)
    
    # 全局参数表
    global_params: Dict[str, Any] = field(default_factory=dict)
    
    # 图纸集合
    drawings: List[DrawingFile] = field(default_factory=list)
    
    # 缓存
    _cache: Dict[str, Any] = field(default_factory=dict, repr=False)

@dataclass
class BuildingInfo:
    """建筑信息"""
    building_id: str
    building_name: str
    building_type: str                  # 主楼、裙房、地下室等
    floors: List['FloorInfo'] = field(default_factory=list)
    bbox: Optional[BoundingBox] = None

@dataclass
class FloorInfo:
    """楼层信息"""
    floor_id: str
    floor_name: str                     # 1F, 2F, B1等
    floor_number: int                   # 数字编号（B1=-1, 1F=1）
    elevation: Optional[float] = None   # 楼层标高
    height: Optional[float] = None      # 层高
    area: Optional[float] = None        # 楼层面积
    discipline_drawings: Dict[str, List[str]] = field(default_factory=dict)  # 专业->图纸列表

# ============ 规则相关数据结构 ============

@dataclass
class RuleCondition:
    """规则条件定义"""
    condition_id: str
    condition_type: CheckMethod
    
    # 关键词相关
    keywords: List[str] = field(default_factory=list)
    keyword_logic: str = "OR"           # AND, OR
    
    # 正则相关
    regex_pattern: Optional[str] = None
    regex_flags: int = 0
    
    # 数值比较相关
    value_path: Optional[str] = None    # 值提取路径（如"params.seismic_intensity"）
    operator: Optional[str] = None      # eq, ne, gt, lt, gte, lte, in, between
    target_value: Optional[Any] = None
    tolerance: Optional[float] = None   # 容差（用于浮点比较）
    
    # 空间检查相关
    spatial_relation: Optional[str] = None  # contains, intersects, distance
    reference_entities: List[str] = field(default_factory=list)
    distance_threshold: Optional[float] = None
    
    # 交叉引用相关
    source_drawing: Optional[str] = None
    target_drawing: Optional[str] = None
    cross_field: Optional[str] = None

@dataclass
class RuleAction:
    """规则动作定义 - 检查通过/失败时的操作"""
    action_type: str                    # flag_issue, extract_value, update_context
    issue_template: Optional[str] = None
    severity: IssueSeverity = IssueSeverity.MEDIUM
    value_mapping: Optional[Dict[str, str]] = None

@dataclass
class ReviewRule:
    """审查规则完整定义"""
    rule_id: str                        # 唯一标识（如"GB50016-2022-5.5.8"）
    rule_name: str                      # 规则名称
    rule_category: RuleCategory
    check_level: CheckLevel
    
    # 适用范围
    applicable_disciplines: List[Discipline]
    applicable_project_types: List[str]  # 适用的项目类型
    applicable_phases: List[ConstructionPhase]
    
    # 规则内容
    description: str                    # 规则描述
    code_reference: str                 # 规范条文引用
    code_clause: Optional[str] = None   # 具体条款号
    
    # 检查逻辑
    preconditions: List[RuleCondition] = field(default_factory=list)  # 前置条件
    check_conditions: List[RuleCondition] = field(default_factory=list)  # 检查条件
    
    # 结果处理
    pass_action: Optional[RuleAction] = None
    fail_action: RuleAction = field(default_factory=lambda: RuleAction("flag_issue"))
    
    # 元数据
    priority: int = 100                 # 优先级（数字越小越优先）
    enabled: bool = True
    version: str = "1.0"
    source_document: Optional[str] = None  # 来源文档
    
    # 运行时统计
    execution_count: int = 0
    issue_count: int = 0
    avg_execution_time: float = 0.0

@dataclass
class RuleSet:
    """规则集 - 按专业/阶段组织的规则集合"""
    ruleset_id: str
    ruleset_name: str
    discipline: Discipline
    phase: ConstructionPhase
    rules: List[ReviewRule] = field(default_factory=list)
    
    def filter_rules(self, project_type: str, check_level: CheckLevel) -> List[ReviewRule]:
        """根据项目类型和审查深度过滤规则"""
        return [
            r for r in self.rules
            if r.enabled 
            and (not r.applicable_project_types or project_type in r.applicable_project_types)
            and r.check_level.value <= check_level.value
        ]

# ============ 审查结果数据结构 ============

@dataclass
class IssueLocation:
    """问题位置信息"""
    drawing_id: str
    drawing_name: str
    entity_handle: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    
    # 便于人工定位的信息
    nearby_text: Optional[str] = None   # 附近文本（用于人工查找）
    grid_reference: Optional[str] = None  # 轴网参考（如"A-1轴附近"）
    floor: Optional[str] = None

@dataclass
class ReviewIssue:
    """审查发现的问题"""
    issue_id: str                       # 唯一标识
    rule_id: str                        # 关联的规则ID
    
    # 问题分类
    severity: IssueSeverity
    category: str                       # 问题分类（如"消防疏散"、"结构安全"）
    
    # 问题描述
    title: str                          # 问题标题（简洁）
    description: str                    # 问题详细描述
    suggestion: Optional[str] = None    # 修改建议
    code_reference: Optional[str] = None  # 规范依据
    
    # 位置信息
    location: IssueLocation
    related_drawings: List[str] = field(default_factory=list)  # 关联图纸
    
    # 证据
    evidence_text: Optional[str] = None     # 文本证据
    evidence_image: Optional[str] = None    # 截图证据（文件路径）
    evidence_data: Dict[str, Any] = field(default_factory=dict)  # 结构化证据
    
    # 状态跟踪
    status: str = "open"                # open, confirmed, disputed, resolved, waived
    assignee: Optional[str] = None      # 指派人
    resolution: Optional[str] = None    # 解决方案
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    confirmed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

@dataclass
class CheckResult:
    """单次检查结果"""
    result_id: str
    rule_id: str
    drawing_id: str
    
    # 执行状态
    status: str                         # passed, failed, skipped, error
    
    # 执行信息
    execution_time_ms: float
    timestamp: datetime
    
    # 结果详情
    matched_entities: List[str] = field(default_factory=list)  # 匹配的实体句柄
    extracted_values: Dict[str, Any] = field(default_factory=dict)  # 提取的值
    
    # 问题（如果status=failed）
    issues: List[ReviewIssue] = field(default_factory=list)
    
    # 错误信息（如果status=error）
    error_message: Optional[str] = None

@dataclass
class DimensionReport:
    """维度审查报告"""
    dimension_id: str                   # 维度标识（如"compliance", "constructable"）
    dimension_name: str                 # 维度名称
    
    # 统计
    total_rules: int
    checked_rules: int
    passed_rules: int
    failed_rules: int
    skipped_rules: int
    
    # 问题汇总
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    issues_by_category: Dict[str, int] = field(default_factory=dict)
    
    # 详细结果
    check_results: List[CheckResult] = field(default_factory=list)
    issues: List[ReviewIssue] = field(default_factory=list)
    
    # 评分（0-100）
    score: Optional[float] = None

@dataclass
class ReviewReport:
    """完整审查报告"""
    report_id: str
    project_id: str
    
    # 执行信息
    started_at: datetime
    completed_at: Optional[datetime] = None
    execution_time_seconds: float = 0.0
    
    # 审查配置
    check_levels: List[CheckLevel] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    
    # 各维度报告
    dimension_reports: Dict[str, DimensionReport] = field(default_factory=dict)
    
    # 汇总统计
    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    
    # 总体评分
    overall_score: Optional[float] = None
    
    # 按角色整理的输出
    designer_issues: List[ReviewIssue] = field(default_factory=list)
    contractor_issues: List[ReviewIssue] = field(default_factory=list)
    supervisor_issues: List[ReviewIssue] = field(default_factory=list)
    owner_issues: List[ReviewIssue] = field(default_factory=list)
    
    # 原始数据（用于后续分析）
    raw_data: Dict[str, Any] = field(default_factory=dict)

# ============ 施工进度相关数据结构 ============

@dataclass
class ConstructionTask:
    """施工任务"""
    task_id: str
    task_name: str
    task_type: str                      # 土建、机电、装修等
    
    # 前置条件
    prerequisites: List[str] = field(default_factory=list)  # 前置任务ID
    required_drawings: List[str] = field(default_factory=list)  # 所需图纸
    required_materials: List[str] = field(default_factory=list)  # 所需材料
    
    # 空间范围
    building_id: Optional[str] = None
    floor_ids: List[str] = field(default_factory=list)
    work_area: Optional[BoundingBox] = None
    
    # 时间估算
    estimated_duration_days: Optional[int] = None
    estimated_start: Optional[datetime] = None
    estimated_end: Optional[datetime] = None
    
    # 资源需求
    labor_requirement: Optional[str] = None
    equipment_requirement: Optional[str] = None
    
    # 审查关联
    related_issues: List[str] = field(default_factory=list)  # 关联的审查问题ID
    risk_level: str = "normal"          # normal, high

@dataclass
class ConstructionSchedule:
    """施工进度计划"""
    schedule_id: str
    project_id: str
    
    # 任务列表
    tasks: List[ConstructionTask] = field(default_factory=list)
    
    # 关键路径
    critical_path: List[str] = field(default_factory=list)  # 关键任务ID序列
    
    # 里程碑
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    
    # 总体时间
    project_start: Optional[datetime] = None
    project_end: Optional[datetime] = None
    total_duration_days: Optional[int] = None
    
    # 审查建议
    review_recommendations: List[str] = field(default_factory=list)

# ============ 缓存相关数据结构 ============

@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None

@dataclass
class ExtractionCache:
    """图纸提取缓存"""
    file_hash: str
    extraction_result: Dict[str, Any]
    extracted_at: datetime
    entity_count: int
    
    def is_valid(self, current_hash: str) -> bool:
        return self.file_hash == current_hash

@dataclass
class RuleCache:
    """规则执行缓存"""
    cache_key: str                      # file_hash + rule_id + params_hash
    result: CheckResult
    computed_at: datetime
    
    @staticmethod
    def generate_key(file_hash: str, rule_id: str, params: Dict) -> str:
        import hashlib
        params_str = str(sorted(params.items()))
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"{file_hash}:{rule_id}:{params_hash}"
```

---

## 第二部分：模块接口详细定义

### 2.1 模块接口总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AI智能审图系统 v6.0 模块架构                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  Input Layer │───▶│  Core Engine │───▶│Output Layer  │───▶│  Reports │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────┘  │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │DXF Extractor │    │ Rule Engine  │    │Issue Manager │                  │
│  │  (M01)       │    │  (M03)       │    │  (M05)       │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│         │                   │                                             │
│         ▼                   ▼                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │Spatial Index │    │Value Checker │    │Schedule Gen  │                  │
│  │  (M02)       │    │  (M04)       │    │  (M06)       │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │Cache Manager │    │Cross-Ref     │    │Multi-Role    │                  │
│  │  (M07)       │    │  (M08)       │    │  (M09)       │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块M01: DXF提取器 (DXFExtractor)

```python
# modules/dxf_extractor.py

from typing import Iterator, Callable, Optional
from pathlib import Path
import ezdxf
from dataclasses import asdict

class DXFExtractor:
    """
    DXF图纸提取器
    
    职责：
    1. 解析DXF文件，提取所有图元信息
    2. 识别和分类图元类型（文本、尺寸、块引用等）
    3. 提取标高、楼层、专业等语义信息
    4. 生成空间索引数据
    
    性能目标：
    - 单文件解析 < 5秒（100MB以下）
    - 内存占用 < 200MB
    """
    
    # 图层到专业的映射表
    LAYER_DISCIPLINE_MAP = {
        # 建筑
        "ARCH": Discipline.ARCH, "建筑": Discipline.ARCH, "建": Discipline.ARCH,
        "WALL": Discipline.ARCH, "墙": Discipline.ARCH,
        "DOOR": Discipline.ARCH, "门": Discipline.ARCH,
        "WINDOW": Discipline.ARCH, "窗": Discipline.ARCH,
        
        # 结构
        "STRUC": Discipline.STRUC, "结构": Discipline.STRUC, "结": Discipline.STRUC,
        "COLUMN": Discipline.STRUC, "柱": Discipline.STRUC,
        "BEAM": Discipline.STRUC, "梁": Discipline.STRUC,
        "SLAB": Discipline.STRUC, "板": Discipline.STRUC,
        "FOUND": Discipline.STRUC, "基础": Discipline.STRUC,
        
        # 电气
        "ELEC": Discipline.ELEC, "电气": Discipline.ELEC, "电": Discipline.ELEC,
        "LIGHT": Discipline.ELEC, "照明": Discipline.ELEC,
        "POWER": Discipline.ELEC, "动力": Discipline.ELEC,
        "FIRE_ALARM": Discipline.ELEC, "火警": Discipline.ELEC,
        
        # 暖通
        "HVAC": Discipline.HVAC, "暖通": Discipline.HVAC, "暖": Discipline.HVAC,
        "AC": Discipline.HVAC, "空调": Discipline.HVAC,
        "VENT": Discipline.HVAC, "通风": Discipline.HVAC,
        
        # 给排水
        "PLUMB": Discipline.PLUMB, "给排水": Discipline.PLUMB, "水": Discipline.PLUMB,
        "WATER": Discipline.PLUMB, "给水": Discipline.PLUMB,
        "DRAIN": Discipline.PLUMB, "排水": Discipline.PLUMB,
        "FIRE_PROT": Discipline.PLUMB, "消防水": Discipline.PLUMB,
    }
    
    # 标高文本匹配正则
    ELEVATION_PATTERNS = [
        r'([±\+\-]?\d+\.?\d*)\s*[mM米]',  # 3.5m, ±0.000m
        r'标高[：:]\s*([±\+\-]?\d+\.?\d*)',  # 标高: 3.5
        r'([\d\.]+)\s*(?:层|F|楼)',  # 3层, 3F
        r'([\+\-]?\d+\.?\d*)\s*(?:米|m)(?:标高)?',  # 3.5米标高
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化提取器
        
        Args:
            config: 配置参数
                - text_height_threshold: 最小文本高度（过滤噪点）
                - extract_dimensions: 是否提取尺寸标注
                - extract_blocks: 是否提取块引用
                - parallel_chunks: 并行处理的分块数
        """
        self.config = config or {}
        self.text_height_threshold = self.config.get('text_height_threshold', 0.5)
        self.extract_dimensions = self.config.get('extract_dimensions', True)
        self.extract_blocks = self.config.get('extract_blocks', True)
        self.parallel_chunks = self.config.get('parallel_chunks', 4)
        
        # 统计信息
        self.stats = {
            'files_processed': 0,
            'entities_extracted': 0,
            'texts_extracted': 0,
            'dimensions_extracted': 0,
            'blocks_extracted': 0,
            'errors': []
        }
    
    def extract_file(self, file_path: str, file_hash: str) -> DrawingFile:
        """
        提取单个DXF文件
        
        Args:
            file_path: DXF文件路径
            file_hash: 文件哈希（用于缓存）
            
        Returns:
            DrawingFile: 图纸文件对象
            
        Raises:
            DXFError: DXF解析错误
            FileNotFoundError: 文件不存在
            
        执行流程：
        1. 检查缓存（如果启用）
        2. 打开DXF文档
        3. 提取模型空间和图纸空间实体
        4. 分类和解析图元
        5. 提取图纸元数据
        6. 保存到缓存
        7. 返回DrawingFile
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"DXF文件不存在: {file_path}")
        
        # 检查缓存
        cache_key = f"extraction:{file_hash}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached
        
        try:
            doc = ezdxf.readfile(file_path)
        except Exception as e:
            self.stats['errors'].append({
                'file': file_path,
                'error': str(e),
                'type': 'parse_error'
            })
            raise DXFError(f"无法解析DXF文件: {e}")
        
        # 提取实体
        msp = doc.modelspace()
        psp = doc.paperspace()
        
        entities = []
        entities.extend(self._extract_from_layout(msp))
        if self.extract_blocks:
            entities.extend(self._extract_from_layout(psp))
        
        # 提取图纸元数据
        drawing_file = self._extract_metadata(doc, file_path, file_hash, entities)
        
        # 保存到缓存
        self._save_cache(cache_key, drawing_file)
        
        self.stats['files_processed'] += 1
        self.stats['entities_extracted'] += len(entities)
        
        return drawing_file
    
    def extract_batch(self, file_paths: List[tuple], 
                      progress_callback: Optional[Callable] = None) -> List[DrawingFile]:
        """
        批量提取多个DXF文件
        
        Args:
            file_paths: [(file_path, file_hash), ...]
            progress_callback: 进度回调函数(current, total, current_file)
            
        Returns:
            List[DrawingFile]: 图纸文件对象列表
            
        执行流程：
        1. 并行处理（多进程）
        2. 每个进程处理一个子集
        3. 合并结果
        4. 更新统计信息
        """
        from concurrent.futures import ProcessPoolExecutor, as_completed
        
        results = []
        total = len(file_paths)
        
        with ProcessPoolExecutor(max_workers=self.parallel_chunks) as executor:
            # 提交所有任务
            future_to_file = {
                executor.submit(self.extract_file, fp, fh): (fp, fh)
                for fp, fh in file_paths
            }
            
            # 收集结果
            for i, future in enumerate(as_completed(future_to_file)):
                file_path, file_hash = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                    if progress_callback:
                        progress_callback(i + 1, total, file_path)
                except Exception as e:
                    self.stats['errors'].append({
                        'file': file_path,
                        'error': str(e),
                        'type': 'batch_error'
                    })
        
        return results
    
    def _extract_from_layout(self, layout) -> List[DXFEntity]:
        """
        从布局中提取实体
        
        Args:
            layout: ezdxf布局对象
            
        Returns:
            List[DXFEntity]: 提取的实体列表
        """
        entities = []
        
        # 提取文本实体
        for entity in layout.query('TEXT MTEXT'):
            try:
                text_entity = self._parse_text_entity(entity)
                if text_entity:
                    entities.append(text_entity)
                    self.stats['texts_extracted'] += 1
            except Exception as e:
                self.stats['errors'].append({
                    'entity': entity.dxftype(),
                    'handle': entity.dxf.handle,
                    'error': str(e)
                })
        
        # 提取尺寸标注
        if self.extract_dimensions:
            for entity in layout.query('DIMENSION'):
                try:
                    dim_entity = self._parse_dimension_entity(entity)
                    if dim_entity:
                        entities.append(dim_entity)
                        self.stats['dimensions_extracted'] += 1
                except Exception as e:
                    pass
        
        # 提取块引用
        if self.extract_blocks:
            for entity in layout.query('INSERT'):
                try:
                    block_entity = self._parse_block_entity(entity)
                    if block_entity:
                        entities.append(block_entity)
                        self.stats['blocks_extracted'] += 1
                except Exception as e:
                    pass
        
        return entities
    
    def _parse_text_entity(self, entity) -> Optional[TextEntity]:
        """
        解析文本实体
        
        Args:
            entity: ezdxf TEXT或MTEXT实体
            
        Returns:
            TextEntity: 解析后的文本实体，或None（如果过滤掉）
        """
        # 获取文本内容
        if entity.dxftype() == 'TEXT':
            text = entity.dxf.text
            height = entity.dxf.height
            rotation = entity.dxf.rotation
        elif entity.dxftype() == 'MTEXT':
            text = entity.text
            height = entity.dxf.char_height
            rotation = entity.dxf.rotation
        else:
            return None
        
        # 过滤过小文本（噪点）
        if height < self.text_height_threshold:
            return None
        
        # 过滤空文本
        text = text.strip() if text else ""
        if not text:
            return None
        
        # 计算包围盒
        insert = entity.dxf.insert
        bbox = self._calculate_text_bbox(insert, text, height, rotation)
        
        # 推断专业和楼层
        layer = entity.dxf.layer
        discipline = self._infer_discipline(layer)
        floor = self._infer_floor(text, layer)
        elevation = self._extract_elevation(text)
        
        return TextEntity(
            entity_type=entity.dxftype(),
            handle=entity.dxf.handle,
            layer=layer,
            bbox=bbox,
            text_content=text,
            font_size=height,
            rotation=rotation,
            elevation=elevation,
            floor=floor,
            discipline=discipline.value if discipline else None
        )
    
    def _parse_dimension_entity(self, entity) -> Optional[DimensionEntity]:
        """解析尺寸标注实体"""
        # 实现尺寸标注解析逻辑
        # ...
        pass
    
    def _parse_block_entity(self, entity) -> Optional[BlockReference]:
        """解析块引用实体"""
        # 实现块引用解析逻辑
        # ...
        pass
    
    def _infer_discipline(self, layer_name: str) -> Optional[Discipline]:
        """
        从图层名推断专业
        
        Args:
            layer_name: 图层名称
            
        Returns:
            Optional[Discipline]: 推断的专业，或None
        """
        layer_upper = layer_name.upper()
        
        for pattern, discipline in self.LAYER_DISCIPLINE_MAP.items():
            if pattern in layer_upper:
                return discipline
        
        return None
    
    def _infer_floor(self, text: str, layer: str) -> Optional[str]:
        """
        从文本和图层推断楼层
        
        Args:
            text: 文本内容
            layer: 图层名称
            
        Returns:
            Optional[str]: 楼层名称，如"1F", "B1"
        """
        import re
        
        # 从文本匹配楼层
        floor_patterns = [
            r'(\d+)\s*[Ff]',  # 1F, 2F
            r'([\d]+)\s*层',  # 1层, 2层
            r'([Bb]\d+)',     # B1, B2
            r'(地下\s*\d+)',   # 地下1
            r'(屋顶|屋面|机房|避难层)',
        ]
        
        for pattern in floor_patterns:
            match = re.search(pattern, text)
            if match:
                floor = match.group(1)
                if floor.startswith('B') or '地下' in floor:
                    return floor.replace('地下', 'B')
                return f"{floor}F"
        
        # 从图层匹配
        if 'FLOOR' in layer.upper() or '楼层' in layer:
            match = re.search(r'(\d+)', layer)
            if match:
                return f"{match.group(1)}F"
        
        return None
    
    def _extract_elevation(self, text: str) -> Optional[float]:
        """
        从文本中提取标高值
        
        Args:
            text: 文本内容
            
        Returns:
            Optional[float]: 标高值（米），或None
        """
        import re
        
        for pattern in self.ELEVATION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    value_str = match.group(1)
                    if value_str.startswith('±'):
                        return 0.0
                    return float(value_str)
                except ValueError:
                    continue
        
        return None
    
    def _calculate_text_bbox(self, insert, text: str, height: float, 
                             rotation: float) -> BoundingBox:
        """
        计算文本包围盒
        
        Args:
            insert: 插入点
            text: 文本内容
            height: 字高
            rotation: 旋转角度
            
        Returns:
            BoundingBox: 文本包围盒
        """
        # 简化计算：假设每个字符宽度为高度的0.6倍
        char_width = height * 0.6
        text_width = len(text) * char_width
        
        # 考虑旋转
        import math
        rad = math.radians(rotation)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        
        # 计算四个角点
        corners = [
            (0, 0),
            (text_width, 0),
            (text_width, height),
            (0, height)
        ]
        
        rotated_corners = []
        for x, y in corners:
            rx = x * cos_r - y * sin_r + insert[0]
            ry = x * sin_r + y * cos_r + insert[1]
            rotated_corners.append((rx, ry))
        
        xs = [c[0] for c in rotated_corners]
        ys = [c[1] for c in rotated_corners]
        
        return BoundingBox(
            min_point=Point3D(min(xs), min(ys), 0),
            max_point=Point3D(max(xs), max(ys), 0)
        )
    
    def _extract_metadata(self, doc, file_path: str, file_hash: str,
                          entities: List[DXFEntity]) -> DrawingFile:
        """
        提取图纸元数据
        
        Args:
            doc: ezdxf文档对象
            file_path: 文件路径
            file_hash: 文件哈希
            entities: 提取的实体列表
            
        Returns:
            DrawingFile: 图纸文件对象
        """
        path = Path(file_path)
        
        # 从文件名推断图纸类型
        filename = path.stem
        drawing_type = self._infer_drawing_type(filename)
        discipline = self._infer_discipline_from_filename(filename)
        
        # 统计实体
        entity_count = {}
        for entity in entities:
            etype = entity.entity_type
            entity_count[etype] = entity_count.get(etype, 0) + 1
        
        # 从文本中提取图号图名
        drawing_number, drawing_name = self._extract_drawing_info(entities)
        
        return DrawingFile(
            file_path=file_path,
            file_hash=file_hash,
            file_size=path.stat().st_size,
            modified_time=datetime.fromtimestamp(path.stat().st_mtime),
            drawing_type=drawing_type,
            discipline=discipline or Discipline.ARCH,
            drawing_number=drawing_number or filename,
            drawing_name=drawing_name or filename,
            parse_status="completed",
            entity_count=entity_count,
            text_count=entity_count.get('TEXT', 0) + entity_count.get('MTEXT', 0),
            dimension_count=entity_count.get('DIMENSION', 0),
            block_count=entity_count.get('INSERT', 0)
        )
    
    def _infer_drawing_type(self, filename: str) -> DrawingType:
        """从文件名推断图纸类型"""
        filename_upper = filename.upper()
        
        if any(k in filename_upper for k in ['立面', 'ELEV', '立面图']):
            return DrawingType.ELEVATION
        elif any(k in filename_upper for k in ['剖面', 'SECT', '剖面图']):
            return DrawingType.SECTION
        elif any(k in filename_upper for k in ['详图', 'DETAIL', '大样']):
            return DrawingType.DETAIL
        elif any(k in filename_upper for k in ['说明', 'NOTE', 'GENERAL']):
            return DrawingType.GENERAL
        elif any(k in filename_upper for k in ['建筑', 'ARCH', '建']):
            return DrawingType.ARCHITECTURAL
        elif any(k in filename_upper for k in ['结构', 'STRUC', '结']):
            return DrawingType.STRUCTURAL
        elif any(k in filename_upper for k in ['电气', 'ELEC', '电']):
            return DrawingType.ELECTRICAL
        elif any(k in filename_upper for k in ['暖通', 'HVAC', '暖']):
            return DrawingType.HVAC
        elif any(k in filename_upper for k in ['给排水', 'PLUMB', '水']):
            return DrawingType.PLUMBING
        elif any(k in filename_upper for k in ['消防', 'FIRE']):
            return DrawingType.FIRE
        
        return DrawingType.GENERAL
    
    def _infer_discipline_from_filename(self, filename: str) -> Optional[Discipline]:
        """从文件名推断专业"""
        filename_upper = filename.upper()
        
        for pattern, discipline in [
            ('建筑|ARCH|建', Discipline.ARCH),
            ('结构|STRUC|结', Discipline.STRUC),
            ('电气|ELEC|电', Discipline.ELEC),
            ('暖通|HVAC|暖', Discipline.HVAC),
            ('给排水|PLUMB|水', Discipline.PLUMB),
            ('消防|FIRE', Discipline.FIRE),
        ]:
            if re.search(pattern, filename_upper):
                return discipline
        
        return None
    
    def _extract_drawing_info(self, entities: List[DXFEntity]) -> tuple:
        """
        从实体中提取图号图名
        
        Returns:
            tuple: (图号, 图名)
        """
        drawing_number = None
        drawing_name = None
        
        # 查找包含"图号"、"图名"的文本
        for entity in entities:
            if not entity.text_content:
                continue
            
            text = entity.text_content
            
            # 图号匹配
            if '图号' in text or '图 号' in text:
                match = re.search(r'图号[：:]\s*([\w\-\.]+)', text)
                if match:
                    drawing_number = match.group(1)
            
            # 图名匹配
            if '图名' in text or '图 名' in text:
                match = re.search(r'图名[：:]\s*(.+)', text)
                if match:
                    drawing_name = match.group(1).strip()
        
        return drawing_number, drawing_name
    
    def _check_cache(self, cache_key: str) -> Optional[DrawingFile]:
        """检查缓存"""
        # 实现缓存检查逻辑
        pass
    
    def _save_cache(self, cache_key: str, data: DrawingFile):
        """保存到缓存"""
        # 实现缓存保存逻辑
        pass
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()


class DXFError(Exception):
    """DXF处理错误"""
    pass
```

### 2.3 模块M02: 空间索引器 (SpatialIndexer)

```python
# modules/spatial_indexer.py

from typing import List, Dict, Set, Iterator, Callable
from rtree import index  # 需要安装: pip install rtree
import numpy as np

class SpatialIndexer:
    """
    空间索引器 - 基于R-tree的高效空间查询
    
    职责：
    1. 为所有DXF实体建立空间索引
    2. 支持快速的空间查询（点查询、范围查询、邻近查询）
    3. 支持跨图纸的空间关系分析
    4. 支持楼层/专业/构件类型的分层索引
    
    性能目标：
    - 索引构建 < 2秒/万实体
    - 点查询 < 1ms
    - 范围查询 < 10ms
    """
    
    def __init__(self):
        """初始化空间索引器"""
        # 全局索引（所有实体）
        self.global_idx = index.Index()
        
        # 分层索引
        self.floor_indices: Dict[str, index.Index] = {}      # 楼层索引
        self.discipline_indices: Dict[str, index.Index] = {}  # 专业索引
        self.type_indices: Dict[str, index.Index] = {}        # 类型索引
        
        # 实体存储
        self.entities: Dict[str, DXFEntity] = {}              # handle -> entity
        self.entity_metadata: Dict[str, Dict] = {}            # handle -> metadata
        
        # 统计
        self.index_stats = {
            'total_entities': 0,
            'indexed_floors': set(),
            'indexed_disciplines': set(),
            'index_build_time_ms': 0
        }
    
    def build_index(self, drawings: List[DrawingFile],
                   entities: List[DXFEntity]) -> 'SpatialIndexer':
        """
        构建空间索引
        
        Args:
            drawings: 图纸文件列表
            entities: 实体列表
            
        Returns:
            SpatialIndexer: self（链式调用）
            
        执行流程：
        1. 清空现有索引
        2. 遍历所有实体
        3. 插入全局索引
        4. 插入分层索引
        5. 更新统计
        """
        import time
        start_time = time.time()
        
        # 清空索引
        self._clear_indices()
        
        # 建立图纸ID到信息的映射
        drawing_map = {d.file_path: d for d in drawings}
        
        # 插入所有实体
        for i, entity in enumerate(entities):
            self._insert_entity(i, entity, drawing_map)
        
        # 更新统计
        self.index_stats['total_entities'] = len(entities)
        self.index_stats['index_build_time_ms'] = (time.time() - start_time) * 1000
        
        return self
    
    def _insert_entity(self, idx: int, entity: DXFEntity, 
                       drawing_map: Dict[str, DrawingFile]):
        """
        插入单个实体到索引
        
        Args:
            idx: 索引ID（R-tree需要整数ID）
            entity: 实体对象
            drawing_map: 图纸信息映射
        """
        bbox = entity.bbox
        
        # 生成边界框坐标 (minx, miny, minz, maxx, maxy, maxz)
        bounds = (
            bbox.min_point.x, bbox.min_point.y, bbox.min_point.z,
            bbox.max_point.x, bbox.max_point.y, bbox.max_point.z
        )
        
        # 存储实体
        self.entities[entity.handle] = entity
        self.entity_metadata[entity.handle] = {
            'index_id': idx,
            'floor': entity.floor,
            'discipline': entity.discipline,
            'entity_type': entity.entity_type
        }
        
        # 插入全局索引
        self.global_idx.insert(idx, bounds)
        
        # 插入楼层索引
        if entity.floor:
            if entity.floor not in self.floor_indices:
                self.floor_indices[entity.floor] = index.Index()
            self.floor_indices[entity.floor].insert(idx, bounds)
            self.index_stats['indexed_floors'].add(entity.floor)
        
        # 插入专业索引
        if entity.discipline:
            if entity.discipline not in self.discipline_indices:
                self.discipline_indices[entity.discipline] = index.Index()
            self.discipline_indices[entity.discipline].insert(idx, bounds)
            self.index_stats['indexed_disciplines'].add(entity.discipline)
        
        # 插入类型索引
        if entity.entity_type not in self.type_indices:
            self.type_indices[entity.entity_type] = index.Index()
        self.type_indices[entity.entity_type].insert(idx, bounds)
    
    def query_point(self, point: Point3D, 
                    filters: Optional[Dict] = None) -> List[DXFEntity]:
        """
        点查询 - 查找包含给定点的所有实体
        
        Args:
            point: 查询点
            filters: 过滤条件
                - floor: 楼层过滤
                - discipline: 专业过滤
                - entity_type: 类型过滤
                
        Returns:
            List[DXFEntity]: 包含该点的实体列表
        """
        # 使用极小包围盒进行点查询
        epsilon = 0.001
        bounds = (
            point.x - epsilon, point.y - epsilon, point.z - epsilon,
            point.x + epsilon, point.y + epsilon, point.z + epsilon
        )
        
        return self.query_range(bounds, filters)
    
    def query_range(self, bounds: tuple,
                   filters: Optional[Dict] = None) -> List[DXFEntity]:
        """
        范围查询 - 查找与给定范围相交的所有实体
        
        Args:
            bounds: (minx, miny, minz, maxx, maxy, maxz)
            filters: 过滤条件
            
        Returns:
            List[DXFEntity]: 相交的实体列表
        """
        # 选择索引
        idx = self._select_index(filters)
        
        # 执行查询
        results = []
        for idx_id in idx.intersection(bounds):
            # 找到对应的实体句柄
            for handle, meta in self.entity_metadata.items():
                if meta['index_id'] == idx_id:
                    entity = self.entities.get(handle)
                    if entity:
                        results.append(entity)
                    break
        
        return results
    
    def query_nearest(self, point: Point3D, k: int = 5,
                     filters: Optional[Dict] = None) -> List[DXFEntity]:
        """
        邻近查询 - 查找距离给定点最近的k个实体
        
        Args:
            point: 查询点
            k: 返回数量
            filters: 过滤条件
            
        Returns:
            List[DXFEntity]: 最近的k个实体
        """
        idx = self._select_index(filters)
        
        # R-tree nearest查询
        coords = (point.x, point.y, point.z)
        nearest_ids = list(idx.nearest(coords, k))
        
        results = []
        for idx_id in nearest_ids:
            for handle, meta in self.entity_metadata.items():
                if meta['index_id'] == idx_id:
                    entity = self.entities.get(handle)
                    if entity:
                        results.append(entity)
                    break
        
        return results
    
    def query_collision(self, bbox: BoundingBox,
                       filters: Optional[Dict] = None) -> List[DXFEntity]:
        """
        碰撞查询 - 查找与给定包围盒相交的实体（用于碰撞检测）
        
        Args:
            bbox: 查询包围盒
            filters: 过滤条件
            
        Returns:
            List[DXFEntity]: 相交的实体列表
        """
        bounds = (
            bbox.min_point.x, bbox.min_point.y, bbox.min_point.z,
            bbox.max_point.x, bbox.max_point.y, bbox.max_point.z
        )
        
        return self.query_range(bounds, filters)
    
    def query_by_text(self, text_pattern: str,
                     filters: Optional[Dict] = None) -> List[DXFEntity]:
        """
        文本查询 - 查找文本内容匹配的实体
        
        Args:
            text_pattern: 文本模式（支持通配符）
            filters: 过滤条件
            
        Returns:
            List[DXFEntity]: 匹配的文本实体
        """
        import fnmatch
        
        results = []
        for handle, entity in self.entities.items():
            if not entity.text_content:
                continue
            
            # 应用过滤条件
            if filters:
                meta = self.entity_metadata[handle]
                if 'floor' in filters and meta.get('floor') != filters['floor']:
                    continue
                if 'discipline' in filters and meta.get('discipline') != filters['discipline']:
                    continue
                if 'entity_type' in filters and meta.get('entity_type') != filters['entity_type']:
                    continue
            
            # 文本匹配
            if fnmatch.fnmatch(entity.text_content, text_pattern):
                results.append(entity)
        
        return results
    
    def query_cross_discipline(self, discipline1: str, discipline2: str,
                               max_distance: float = 1.0) -> List[Dict]:
        """
        跨专业查询 - 查找两个专业在空间上接近的实体对
        
        Args:
            discipline1: 专业1
            discipline2: 专业2
            max_distance: 最大距离（米）
            
        Returns:
            List[Dict]: 接近的实体对列表
                [{"entity1": DXFEntity, "entity2": DXFEntity, "distance": float}]
        """
        results = []
        
        # 获取两个专业的索引
        idx1 = self.discipline_indices.get(discipline1)
        idx2 = self.discipline_indices.get(discipline2)
        
        if not idx1 or not idx2:
            return results
        
        # 遍历专业1的所有实体
        for handle1, entity1 in self.entities.items():
            meta1 = self.entity_metadata.get(handle1)
            if not meta1 or meta1.get('discipline') != discipline1:
                continue
            
            # 在专业2中查询邻近实体
            center = entity1.bbox.center
            nearest = self.query_nearest(center, k=5, 
                                        filters={'discipline': discipline2})
            
            for entity2 in nearest:
                distance = center.distance_to(entity2.bbox.center)
                if distance <= max_distance:
                    results.append({
                        'entity1': entity1,
                        'entity2': entity2,
                        'distance': distance
                    })
        
        return results
    
    def _select_index(self, filters: Optional[Dict]) -> index.Index:
        """
        根据过滤条件选择最优索引
        
        Args:
            filters: 过滤条件
            
        Returns:
            index.Index: 选中的索引
        """
        if not filters:
            return self.global_idx
        
        # 优先级：楼层 > 专业 > 类型
        if 'floor' in filters and filters['floor'] in self.floor_indices:
            return self.floor_indices[filters['floor']]
        
        if 'discipline' in filters and filters['discipline'] in self.discipline_indices:
            return self.discipline_indices[filters['discipline']]
        
        if 'entity_type' in filters and filters['entity_type'] in self.type_indices:
            return self.type_indices[filters['entity_type']]
        
        return self.global_idx
    
    def _clear_indices(self):
        """清空所有索引"""
        self.global_idx = index.Index()
        self.floor_indices.clear()
        self.discipline_indices.clear()
        self.type_indices.clear()
        self.entities.clear()
        self.entity_metadata.clear()
    
    def get_stats(self) -> Dict:
        """获取索引统计信息"""
        return {
            **self.index_stats,
            'floor_count': len(self.floor_indices),
            'discipline_count': len(self.discipline_indices),
            'type_count': len(self.type_indices)
        }
    
    def export_to_json(self) -> Dict:
        """导出索引信息为JSON（用于调试）"""
        return {
            'stats': self.get_stats(),
            'floors': list(self.floor_indices.keys()),
            'disciplines': list(self.discipline_indices.keys()),
            'types': list(self.type_indices.keys()),
            'entity_count': len(self.entities)
        }
```

---

### 2.4 模块M03: 规则引擎 (RuleEngine)

```python
# modules/rule_engine.py

from typing import List, Dict, Any, Optional, Callable, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import json

class RuleEngine:
    """
    规则引擎 - 核心审查逻辑执行器
    
    职责：
    1. 加载和管理审查规则库
    2. 根据项目特征预过滤规则
    3. 执行规则检查（支持多种检查方法）
    4. 收集和整理检查结果
    5. 支持规则优先级和依赖关系
    
    性能目标：
    - 规则加载 < 1秒（500条规则）
    - 单规则执行 < 50ms
    - 全量检查 < 30秒（100条规则 x 5图纸）
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化规则引擎
        
        Args:
            config: 配置参数
                - rules_path: 规则库文件路径
                - max_workers: 并行执行的最大线程数
                - enable_cache: 是否启用结果缓存
                - cache_ttl: 缓存有效期（秒）
        """
        self.config = config or {}
        self.rules_path = self.config.get('rules_path', 'config/rules.json')
        self.max_workers = self.config.get('max_workers', 4)
        self.enable_cache = self.config.get('enable_cache', True)
        
        # 规则存储
        self.rules: Dict[str, ReviewRule] = {}           # rule_id -> rule
        self.rulesets: Dict[str, RuleSet] = {}           # ruleset_id -> ruleset
        self.rules_by_discipline: Dict[str, List[str]] = {}  # discipline -> rule_ids
        self.rules_by_phase: Dict[str, List[str]] = {}   # phase -> rule_ids
        
        # 检查方法注册表
        self.check_methods: Dict[str, Callable] = {
            'keyword_exact': self._check_keyword_exact,
            'keyword_any': self._check_keyword_any,
            'regex': self._check_regex,
            'value_compare': self._check_value_compare,
            'spatial_check': self._check_spatial,
            'cross_reference': self._check_cross_ref,
            'calculation': self._check_calculation,
        }
        
        # 运行时统计
        self.stats = {
            'rules_loaded': 0,
            'rules_executed': 0,
            'rules_passed': 0,
            'rules_failed': 0,
            'rules_skipped': 0,
            'total_execution_time_ms': 0,
            'errors': []
        }
        
        # 加载规则
        self._load_rules()
    
    def _load_rules(self):
        """
        从JSON文件加载规则库
        
        规则文件格式：
        {
            "version": "6.0",
            "rulesets": [
                {
                    "ruleset_id": "arch_compliance",
                    "ruleset_name": "建筑专业合规性规则集",
                    "discipline": "建筑",
                    "phase": "设计阶段",
                    "rules": [...]
                }
            ]
        }
        """
        try:
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for rs_data in data.get('rulesets', []):
                ruleset = self._parse_ruleset(rs_data)
                self.rulesets[ruleset.ruleset_id] = ruleset
                
                # 索引规则
                for rule in ruleset.rules:
                    self.rules[rule.rule_id] = rule
                    
                    # 按专业索引
                    for disc in rule.applicable_disciplines:
                        disc_key = disc.value if isinstance(disc, Discipline) else disc
                        if disc_key not in self.rules_by_discipline:
                            self.rules_by_discipline[disc_key] = []
                        self.rules_by_discipline[disc_key].append(rule.rule_id)
                    
                    # 按阶段索引
                    for phase in rule.applicable_phases:
                        phase_key = phase.value if isinstance(phase, ConstructionPhase) else phase
                        if phase_key not in self.rules_by_phase:
                            self.rules_by_phase[phase_key] = []
                        self.rules_by_phase[phase_key].append(rule.rule_id)
            
            self.stats['rules_loaded'] = len(self.rules)
            
        except Exception as e:
            self.stats['errors'].append({
                'type': 'load_error',
                'message': f"加载规则库失败: {e}"
            })
            raise RuleEngineError(f"无法加载规则库: {e}")
    
    def _parse_ruleset(self, data: Dict) -> RuleSet:
        """解析规则集数据"""
        rules = [self._parse_rule(r) for r in data.get('rules', [])]
        
        return RuleSet(
            ruleset_id=data['ruleset_id'],
            ruleset_name=data['ruleset_name'],
            discipline=Discipline(data['discipline']),
            phase=ConstructionPhase(data['phase']),
            rules=rules
        )
    
    def _parse_rule(self, data: Dict) -> ReviewRule:
        """解析规则数据"""
        # 解析前置条件
        preconditions = [
            self._parse_condition(c) for c in data.get('preconditions', [])
        ]
        
        # 解析检查条件
        check_conditions = [
            self._parse_condition(c) for c in data.get('check_conditions', [])
        ]
        
        # 解析失败动作
        fail_action = self._parse_action(data.get('fail_action', {}))
        
        # 解析通过动作（可选）
        pass_action = None
        if 'pass_action' in data:
            pass_action = self._parse_action(data['pass_action'])
        
        return ReviewRule(
            rule_id=data['rule_id'],
            rule_name=data['rule_name'],
            rule_category=RuleCategory(data.get('rule_category', 'MANDATORY')),
            check_level=CheckLevel(data.get('check_level', 1)),
            applicable_disciplines=[
                Discipline(d) for d in data.get('applicable_disciplines', [])
            ],
            applicable_project_types=data.get('applicable_project_types', []),
            applicable_phases=[
                ConstructionPhase(p) for p in data.get('applicable_phases', [])
            ],
            description=data.get('description', ''),
            code_reference=data.get('code_reference', ''),
            code_clause=data.get('code_clause'),
            preconditions=preconditions,
            check_conditions=check_conditions,
            pass_action=pass_action,
            fail_action=fail_action,
            priority=data.get('priority', 100),
            enabled=data.get('enabled', True),
            version=data.get('version', '1.0'),
            source_document=data.get('source_document')
        )
    
    def _parse_condition(self, data: Dict) -> RuleCondition:
        """解析条件数据"""
        return RuleCondition(
            condition_id=data.get('condition_id', ''),
            condition_type=CheckMethod(data.get('condition_type', 'keyword_exact')),
            keywords=data.get('keywords', []),
            keyword_logic=data.get('keyword_logic', 'OR'),
            regex_pattern=data.get('regex_pattern'),
            regex_flags=data.get('regex_flags', 0),
            value_path=data.get('value_path'),
            operator=data.get('operator'),
            target_value=data.get('target_value'),
            tolerance=data.get('tolerance'),
            spatial_relation=data.get('spatial_relation'),
            reference_entities=data.get('reference_entities', []),
            distance_threshold=data.get('distance_threshold'),
            source_drawing=data.get('source_drawing'),
            target_drawing=data.get('target_drawing'),
            cross_field=data.get('cross_field')
        )
    
    def _parse_action(self, data: Dict) -> RuleAction:
        """解析动作数据"""
        return RuleAction(
            action_type=data.get('action_type', 'flag_issue'),
            issue_template=data.get('issue_template'),
            severity=IssueSeverity(data.get('severity', 'MEDIUM')),
            value_mapping=data.get('value_mapping')
        )
    
    def filter_rules(self, project_context: ProjectContext,
                    check_level: CheckLevel,
                    target_disciplines: Optional[List[Discipline]] = None,
                    target_phases: Optional[List[ConstructionPhase]] = None) -> List[ReviewRule]:
        """
        根据项目上下文过滤规则
        
        Args:
            project_context: 项目上下文
            check_level: 审查深度等级
            target_disciplines: 目标专业（None表示全部）
            target_phases: 目标阶段（None表示全部）
            
        Returns:
            List[ReviewRule]: 过滤后的规则列表
            
        过滤逻辑：
        1. 只选择启用的规则
        2. 检查深度等级 <= 目标等级
        3. 专业匹配（如果指定）
        4. 阶段匹配（如果指定）
        5. 项目类型匹配
        6. 按优先级排序
        """
        filtered = []
        
        for rule in self.rules.values():
            # 检查启用状态
            if not rule.enabled:
                continue
            
            # 检查深度等级
            if rule.check_level.value > check_level.value:
                continue
            
            # 检查专业
            if target_disciplines:
                if not any(d in rule.applicable_disciplines for d in target_disciplines):
                    continue
            
            # 检查阶段
            if target_phases:
                if not any(p in rule.applicable_phases for p in target_phases):
                    continue
            
            # 检查项目类型
            if rule.applicable_project_types:
                if project_context.project_type not in rule.applicable_project_types:
                    continue
            
            filtered.append(rule)
        
        # 按优先级排序（数字小的优先）
        filtered.sort(key=lambda r: r.priority)
        
        return filtered
    
    def execute_check(self, rule: ReviewRule,
                     drawing: DrawingFile,
                     entities: List[DXFEntity],
                     project_context: ProjectContext,
                     spatial_indexer: Optional['SpatialIndexer'] = None) -> CheckResult:
        """
        执行单个规则检查
        
        Args:
            rule: 要执行的规则
            drawing: 目标图纸
            entities: 图纸实体列表
            project_context: 项目上下文
            spatial_indexer: 空间索引器（用于空间检查）
            
        Returns:
            CheckResult: 检查结果
            
        执行流程：
        1. 检查前置条件
        2. 执行检查条件
        3. 收集匹配实体
        4. 提取相关值
        5. 生成检查结果
        6. 执行通过/失败动作
        """
        import time
        start_time = time.time()
        
        result_id = f"{rule.rule_id}_{drawing.file_hash[:8]}"
        
        try:
            # 步骤1: 检查前置条件
            pre_passed, pre_matches = self._check_conditions(
                rule.preconditions, entities, project_context, spatial_indexer
            )
            
            if not pre_passed:
                # 前置条件不满足，跳过此规则
                return CheckResult(
                    result_id=result_id,
                    rule_id=rule.rule_id,
                    drawing_id=drawing.file_path,
                    status='skipped',
                    execution_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(),
                    error_message="前置条件不满足"
                )
            
            # 步骤2: 执行检查条件
            check_passed, check_matches = self._check_conditions(
                rule.check_conditions, entities, project_context, spatial_indexer
            )
            
            # 步骤3: 提取值
            extracted_values = self._extract_values(
                rule.check_conditions, check_matches, entities, project_context
            )
            
            # 步骤4: 生成结果
            execution_time = (time.time() - start_time) * 1000
            
            if check_passed:
                # 检查通过
                result = CheckResult(
                    result_id=result_id,
                    rule_id=rule.rule_id,
                    drawing_id=drawing.file_path,
                    status='passed',
                    execution_time_ms=execution_time,
                    timestamp=datetime.now(),
                    matched_entities=[e.handle for e in check_matches],
                    extracted_values=extracted_values
                )
                
                # 执行通过动作
                if rule.pass_action:
                    self._execute_action(rule.pass_action, result, drawing, project_context)
                
                self.stats['rules_passed'] += 1
                
            else:
                # 检查失败，生成问题
                issues = self._generate_issues(
                    rule, drawing, check_matches, extracted_values
                )
                
                result = CheckResult(
                    result_id=result_id,
                    rule_id=rule.rule_id,
                    drawing_id=drawing.file_path,
                    status='failed',
                    execution_time_ms=execution_time,
                    timestamp=datetime.now(),
                    matched_entities=[e.handle for e in check_matches],
                    extracted_values=extracted_values,
                    issues=issues
                )
                
                # 执行失败动作
                self._execute_action(rule.fail_action, result, drawing, project_context)
                
                self.stats['rules_failed'] += 1
            
            # 更新规则统计
            rule.execution_count += 1
            rule.avg_execution_time = (
                (rule.avg_execution_time * (rule.execution_count - 1) + execution_time)
                / rule.execution_count
            )
            
            self.stats['rules_executed'] += 1
            self.stats['total_execution_time_ms'] += execution_time
            
            return result
            
        except Exception as e:
            self.stats['errors'].append({
                'rule_id': rule.rule_id,
                'drawing': drawing.file_path,
                'error': str(e)
            })
            
            return CheckResult(
                result_id=result_id,
                rule_id=rule.rule_id,
                drawing_id=drawing.file_path,
                status='error',
                execution_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now(),
                error_message=str(e)
            )
    
    def execute_batch(self, rules: List[ReviewRule],
                     drawings: List[DrawingFile],
                     entities_map: Dict[str, List[DXFEntity]],
                     project_context: ProjectContext,
                     spatial_indexer: Optional['SpatialIndexer'] = None,
                     progress_callback: Optional[Callable] = None) -> List[CheckResult]:
        """
        批量执行规则检查
        
        Args:
            rules: 规则列表
            drawings: 图纸列表
            entities_map: 图纸路径到实体列表的映射
            project_context: 项目上下文
            spatial_indexer: 空间索引器
            progress_callback: 进度回调(current, total)
            
        Returns:
            List[CheckResult]: 所有检查结果
        """
        results = []
        total = len(rules) * len(drawings)
        current = 0
        
        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            
            for rule in rules:
                for drawing in drawings:
                    entities = entities_map.get(drawing.file_path, [])
                    future = executor.submit(
                        self.execute_check,
                        rule, drawing, entities, project_context, spatial_indexer
                    )
                    futures.append((future, rule, drawing))
            
            # 收集结果
            for future, rule, drawing in futures:
                try:
                    result = future.result()
                    results.append(result)
                    
                    current += 1
                    if progress_callback:
                        progress_callback(current, total, rule.rule_id, drawing.file_path)
                        
                except Exception as e:
                    self.stats['errors'].append({
                        'rule_id': rule.rule_id,
                        'drawing': drawing.file_path,
                        'error': str(e)
                    })
        
        return results
    
    def _check_conditions(self, conditions: List[RuleCondition],
                         entities: List[DXFEntity],
                         project_context: ProjectContext,
                         spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """
        检查条件列表
        
        Returns:
            tuple: (是否全部通过, 匹配的实体列表)
        """
        if not conditions:
            return True, entities
        
        all_matches = []
        
        for condition in conditions:
            check_method = self.check_methods.get(condition.condition_type.value)
            if not check_method:
                continue
            
            passed, matches = check_method(
                condition, entities, project_context, spatial_indexer
            )
            
            if not passed:
                return False, []
            
            all_matches.extend(matches)
        
        # 去重
        seen = set()
        unique_matches = []
        for e in all_matches:
            if e.handle not in seen:
                seen.add(e.handle)
                unique_matches.append(e)
        
        return True, unique_matches
    
    def _check_keyword_exact(self, condition: RuleCondition,
                            entities: List[DXFEntity],
                            project_context: ProjectContext,
                            spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """精确关键词检查"""
        matches = []
        
        for entity in entities:
            if not entity.text_content:
                continue
            
            text = entity.text_content
            
            if condition.keyword_logic == 'AND':
                # 所有关键词都必须存在
                if all(kw in text for kw in condition.keywords):
                    matches.append(entity)
            else:  # OR
                # 任意关键词存在即可
                if any(kw in text for kw in condition.keywords):
                    matches.append(entity)
        
        return len(matches) > 0, matches
    
    def _check_keyword_any(self, condition: RuleCondition,
                          entities: List[DXFEntity],
                          project_context: ProjectContext,
                          spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """任意关键词检查（同精确检查，但逻辑不同）"""
        return self._check_keyword_exact(condition, entities, project_context, spatial_indexer)
    
    def _check_regex(self, condition: RuleCondition,
                    entities: List[DXFEntity],
                    project_context: ProjectContext,
                    spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """正则表达式检查"""
        if not condition.regex_pattern:
            return False, []
        
        pattern = re.compile(condition.regex_pattern, condition.regex_flags)
        matches = []
        
        for entity in entities:
            if not entity.text_content:
                continue
            
            if pattern.search(entity.text_content):
                matches.append(entity)
        
        return len(matches) > 0, matches
    
    def _check_value_compare(self, condition: RuleCondition,
                            entities: List[DXFEntity],
                            project_context: ProjectContext,
                            spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """数值比较检查"""
        matches = []
        
        # 获取要比较的值
        value = self._get_value(condition.value_path, entities, project_context)
        
        if value is None:
            return False, []
        
        # 执行比较
        target = condition.target_value
        op = condition.operator
        tolerance = condition.tolerance or 0
        
        try:
            if op == 'eq':
                passed = abs(float(value) - float(target)) <= tolerance
            elif op == 'ne':
                passed = abs(float(value) - float(target)) > tolerance
            elif op == 'gt':
                passed = float(value) > float(target)
            elif op == 'lt':
                passed = float(value) < float(target)
            elif op == 'gte':
                passed = float(value) >= float(target)
            elif op == 'lte':
                passed = float(value) <= float(target)
            elif op == 'in':
                passed = value in target if isinstance(target, (list, tuple)) else False
            elif op == 'between':
                passed = target[0] <= float(value) <= target[1] if isinstance(target, (list, tuple)) and len(target) == 2 else False
            else:
                passed = False
            
            if passed:
                matches = entities  # 返回所有实体作为匹配
            
            return passed, matches
            
        except (ValueError, TypeError):
            return False, []
    
    def _check_spatial(self, condition: RuleCondition,
                      entities: List[DXFEntity],
                      project_context: ProjectContext,
                      spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """空间检查"""
        if not spatial_indexer:
            return False, []
        
        matches = []
        
        for entity in entities:
            # 根据空间关系查询
            if condition.spatial_relation == 'intersects':
                nearby = spatial_indexer.query_collision(entity.bbox)
                matches.extend(nearby)
            elif condition.spatial_relation == 'contains':
                # 检查entity是否包含reference_entities
                pass
            elif condition.spatial_relation == 'distance':
                center = entity.bbox.center
                nearby = spatial_indexer.query_nearest(
                    center, k=10,
                    filters={'discipline': condition.reference_entities[0]} if condition.reference_entities else None
                )
                for n in nearby:
                    dist = center.distance_to(n.bbox.center)
                    if dist <= condition.distance_threshold:
                        matches.append(n)
        
        return len(matches) > 0, matches
    
    def _check_cross_ref(self, condition: RuleCondition,
                        entities: List[DXFEntity],
                        project_context: ProjectContext,
                        spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """交叉引用检查"""
        # 实现跨图纸引用验证逻辑
        # 例如：验证设计说明中的参数与图纸标注是否一致
        pass
    
    def _check_calculation(self, condition: RuleCondition,
                          entities: List[DXFEntity],
                          project_context: ProjectContext,
                          spatial_indexer: Optional['SpatialIndexer']) -> tuple:
        """计算验证检查"""
        # 实现计算验证逻辑
        # 例如：验证疏散距离计算、荷载计算等
        pass
    
    def _get_value(self, value_path: str,
                  entities: List[DXFEntity],
                  project_context: ProjectContext) -> Any:
        """
        根据路径获取值
        
        路径格式：
        - "params.seismic_intensity" -> 从项目参数获取
        - "entity.elevation" -> 从实体标高获取
        - "text.match(\d+)" -> 从文本匹配获取
        """
        if not value_path:
            return None
        
        parts = value_path.split('.')
        
        if parts[0] == 'params':
            # 从项目参数获取
            return project_context.global_params.get('.'.join(parts[1:]))
        
        elif parts[0] == 'entity':
            # 从实体获取
            if parts[1] == 'elevation':
                for e in entities:
                    if e.elevation is not None:
                        return e.elevation
            return None
        
        return None
    
    def _extract_values(self, conditions: List[RuleCondition],
                       matches: List[DXFEntity],
                       entities: List[DXFEntity],
                       project_context: ProjectContext) -> Dict[str, Any]:
        """提取条件相关的值"""
        values = {}
        
        for condition in conditions:
            if condition.value_path:
                value = self._get_value(condition.value_path, entities, project_context)
                if value is not None:
                    values[condition.value_path] = value
        
        return values
    
    def _generate_issues(self, rule: ReviewRule,
                        drawing: DrawingFile,
                        matches: List[DXFEntity],
                        extracted_values: Dict[str, Any]) -> List[ReviewIssue]:
        """生成问题列表"""
        issues = []
        
        for entity in matches:
            issue_id = f"{rule.rule_id}_{entity.handle}_{datetime.now().timestamp()}"
            
            # 格式化问题描述
            description = rule.fail_action.issue_template or rule.description
            description = self._format_template(description, {
                'rule_name': rule.rule_name,
                'drawing_name': drawing.drawing_name,
                'entity_text': entity.text_content or '',
                'code_reference': rule.code_reference or '',
                **extracted_values
            })
            
            issue = ReviewIssue(
                issue_id=issue_id,
                rule_id=rule.rule_id,
                severity=rule.fail_action.severity,
                category=rule.rule_category.value,
                title=f"{rule.rule_name}",
                description=description,
                suggestion=f"请参考{rule.code_reference}进行修改",
                code_reference=rule.code_reference,
                location=IssueLocation(
                    drawing_id=drawing.file_path,
                    drawing_name=drawing.drawing_name,
                    entity_handle=entity.handle,
                    bbox=entity.bbox,
                    nearby_text=entity.text_content,
                    floor=entity.floor
                ),
                evidence_text=entity.text_content,
                evidence_data={
                    'extracted_values': extracted_values,
                    'entity_type': entity.entity_type,
                    'layer': entity.layer
                }
            )
            
            issues.append(issue)
            rule.issue_count += 1
        
        return issues
    
    def _execute_action(self, action: RuleAction,
                       result: CheckResult,
                       drawing: DrawingFile,
                       project_context: ProjectContext):
        """执行规则动作"""
        # 实现动作执行逻辑
        # 例如：更新项目上下文、记录日志、触发通知等
        pass
    
    def _format_template(self, template: str, values: Dict) -> str:
        """格式化模板字符串"""
        try:
            return template.format(**values)
        except KeyError as e:
            return template
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()
    
    def export_rules(self, output_path: str):
        """导出规则库到JSON"""
        data = {
            'version': '6.0',
            'rulesets': []
        }
        
        for ruleset in self.rulesets.values():
            rs_data = {
                'ruleset_id': ruleset.ruleset_id,
                'ruleset_name': ruleset.ruleset_name,
                'discipline': ruleset.discipline.value,
                'phase': ruleset.phase.value,
                'rules': []
            }
            
            for rule in ruleset.rules:
                rs_data['rules'].append({
                    'rule_id': rule.rule_id,
                    'rule_name': rule.rule_name,
                    'description': rule.description,
                    'code_reference': rule.code_reference,
                    'priority': rule.priority,
                    'execution_count': rule.execution_count,
                    'issue_count': rule.issue_count,
                    'avg_execution_time': rule.avg_execution_time
                })
            
            data['rulesets'].append(rs_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class RuleEngineError(Exception):
    """规则引擎错误"""
    pass
```

---

### 2.5 模块M04: 数值检查器 (ValueChecker)

```python
# modules/value_checker.py

from typing import List, Dict, Any, Optional, Tuple
import re

class ValueChecker:
    """
    数值检查器 - 专门处理数值提取、比较和验证
    
    职责：
    1. 从文本中提取数值（支持多种格式）
    2. 执行数值比较（支持容差）
    3. 验证数值范围和单位
    4. 处理数值计算和推导
    
    支持的数值格式：
    - 整数：100, 100mm
    - 浮点数：3.5, 3.5m
    - 分数：1/2, 3/4
    - 范围：10-20, 10~20
    - 带单位：100mm, 3.5m, 50㎡
    """
    
    # 数值提取正则模式
    VALUE_PATTERNS = {
        'elevation': [
            r'([±\+\-]?\d+\.?\d*)\s*[mM米]',
            r'标高[：:]\s*([±\+\-]?\d+\.?\d*)',
        ],
        'dimension': [
            r'(\d+\.?\d*)\s*[mM米]',
            r'(\d+\.?\d*)\s*[mM][²2]',
            r'(\d+\.?\d*)\s*[mM][³3]',
            r'(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*cm',
        ],
        'area': [
            r'(\d+\.?\d*)\s*㎡',
            r'(\d+\.?\d*)\s*m[²2]',
            r'面积[：:]\s*(\d+\.?\d*)',
        ],
        'percentage': [
            r'(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)\s*百分之',
        ],
        'ratio': [
            r'比[率例][：:]\s*(\d+\.?\d*)',
            r'(\d+)[：:](\d+)',
        ],
        'temperature': [
            r'(\d+\.?\d*)\s*[°度][Cc]',
            r'(\d+\.?\d*)\s*摄氏度',
        ],
        'pressure': [
            r'(\d+\.?\d*)\s*[Mm]?[Pp][Aa]',
            r'(\d+\.?\d*)\s*帕[斯卡]?',
        ],
    }
    
    # 单位换算表（统一到国际单位）
    UNIT_CONVERSIONS = {
        'mm': 0.001,      # 毫米 -> 米
        'cm': 0.01,       # 厘米 -> 米
        'm': 1.0,         # 米
        'km': 1000.0,     # 千米 -> 米
        '㎡': 1.0,        # 平方米
        'm2': 1.0,        # 平方米
        'm²': 1.0,        # 平方米
        'm3': 1.0,        # 立方米
        'm³': 1.0,        # 立方米
        'pa': 1.0,        # 帕斯卡
        'kpa': 1000.0,    # 千帕 -> 帕
        'mpa': 1000000.0, # 兆帕 -> 帕
    }
    
    def __init__(self):
        """初始化数值检查器"""
        self.compiled_patterns = {
            category: [re.compile(p) for p in patterns]
            for category, patterns in self.VALUE_PATTERNS.items()
        }
        self.extraction_cache = {}
    
    def extract_value(self, text: str, value_type: str,
                     unit: Optional[str] = None) -> Optional[Dict]:
        """
        从文本中提取特定类型的数值
        
        Args:
            text: 输入文本
            value_type: 数值类型（elevation, dimension, area等）
            unit: 期望的单位（可选）
            
        Returns:
            Optional[Dict]: 提取结果
                {
                    'value': float,      # 数值
                    'unit': str,         # 单位
                    'raw': str,          # 原始文本
                    'normalized': float  # 标准化后的值（国际单位）
                }
        """
        if not text:
            return None
        
        # 检查缓存
        cache_key = f"{text}:{value_type}:{unit}"
        if cache_key in self.extraction_cache:
            return self.extraction_cache[cache_key]
        
        patterns = self.compiled_patterns.get(value_type, [])
        
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                result = self._parse_match(match, text, unit)
                self.extraction_cache[cache_key] = result
                return result
        
        return None
    
    def extract_all_values(self, text: str) -> Dict[str, List[Dict]]:
        """
        从文本中提取所有类型的数值
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, List[Dict]]: 按类型分类的数值列表
        """
        results = {}
        
        for value_type in self.VALUE_PATTERNS.keys():
            values = []
            patterns = self.compiled_patterns.get(value_type, [])
            
            for pattern in patterns:
                for match in pattern.finditer(text):
                    result = self._parse_match(match, text)
                    if result:
                        values.append(result)
            
            if values:
                results[value_type] = values
        
        return results
    
    def _parse_match(self, match: re.Match, text: str,
                    target_unit: Optional[str] = None) -> Dict:
        """解析匹配结果"""
        raw = match.group(0)
        
        # 提取数值
        value_str = match.group(1) if match.groups() else raw
        
        # 处理特殊符号
        if value_str.startswith('±'):
            value_str = value_str[1:]
        
        try:
            value = float(value_str)
        except ValueError:
            return None
        
        # 提取单位
        unit = self._extract_unit(raw)
        
        # 标准化
        normalized = self._normalize_value(value, unit)
        
        # 如果需要转换到目标单位
        if target_unit and unit != target_unit:
            value = self._convert_unit(normalized, target_unit)
        
        return {
            'value': value,
            'unit': unit or 'unknown',
            'raw': raw,
            'normalized': normalized
        }
    
    def _extract_unit(self, text: str) -> Optional[str]:
        """从文本中提取单位"""
        text_lower = text.lower()
        
        for unit in self.UNIT_CONVERSIONS.keys():
            if unit.lower() in text_lower:
                return unit
        
        # 中文单位匹配
        if '米' in text:
            return 'm'
        if '毫米' in text or 'mm' in text_lower:
            return 'mm'
        if '厘米' in text or 'cm' in text_lower:
            return 'cm'
        
        return None
    
    def _normalize_value(self, value: float, unit: Optional[str]) -> float:
        """将数值标准化为国际单位"""
        if not unit:
            return value
        
        conversion = self.UNIT_CONVERSIONS.get(unit.lower())
        if conversion:
            return value * conversion
        
        return value
    
    def _convert_unit(self, normalized_value: float, target_unit: str) -> float:
        """将标准化值转换为目标单位"""
        conversion = self.UNIT_CONVERSIONS.get(target_unit.lower())
        if conversion and conversion != 0:
            return normalized_value / conversion
        return normalized_value
    
    def compare_values(self, value1: Dict, value2: Dict,
                      operator: str, tolerance: Optional[float] = None) -> bool:
        """
        比较两个数值
        
        Args:
            value1: 第一个数值（提取结果格式）
            value2: 第二个数值
            operator: 比较运算符（eq, ne, gt, lt, gte, lte）
            tolerance: 容差（用于浮点比较）
            
        Returns:
            bool: 比较结果
        """
        v1 = value1.get('normalized', value1.get('value'))
        v2 = value2.get('normalized', value2.get('value'))
        
        if v1 is None or v2 is None:
            return False
        
        tol = tolerance or 0
        
        if operator == 'eq':
            return abs(v1 - v2) <= tol
        elif operator == 'ne':
            return abs(v1 - v2) > tol
        elif operator == 'gt':
            return v1 > v2 + tol
        elif operator == 'lt':
            return v1 < v2 - tol
        elif operator == 'gte':
            return v1 >= v2 - tol
        elif operator == 'lte':
            return v1 <= v2 + tol
        
        return False
    
    def validate_range(self, value: Dict, min_val: Optional[float] = None,
                      max_val: Optional[float] = None) -> Tuple[bool, str]:
        """
        验证数值是否在范围内
        
        Returns:
            Tuple[bool, str]: (是否通过, 错误信息)
        """
        v = value.get('normalized', value.get('value'))
        
        if min_val is not None and v < min_val:
            return False, f"数值 {v} 小于最小值 {min_val}"
        
        if max_val is not None and v > max_val:
            return False, f"数值 {v} 大于最大值 {max_val}"
        
        return True, ""
    
    def calculate_clearance(self, entity1: DXFEntity,
                           entity2: DXFEntity) -> Optional[float]:
        """
        计算两个实体之间的净距
        
        Args:
            entity1: 实体1
            entity2: 实体2
            
        Returns:
            Optional[float]: 净距（米），如果无法计算则返回None
        """
        # 计算包围盒中心点距离
        center1 = entity1.bbox.center
        center2 = entity2.bbox.center
        
        center_distance = center1.distance_to(center2)
        
        # 估算实体尺寸（简化计算）
        size1 = self._estimate_size(entity1.bbox)
        size2 = self._estimate_size(entity2.bbox)
        
        # 净距 = 中心距 - 半径和
        clearance = center_distance - (size1 + size2) / 2
        
        return max(0, clearance)
    
    def _estimate_size(self, bbox: BoundingBox) -> float:
        """估算实体尺寸（取包围盒最大维度）"""
        dx = bbox.max_point.x - bbox.min_point.x
        dy = bbox.max_point.y - bbox.min_point.y
        dz = bbox.max_point.z - bbox.min_point.z
        return max(dx, dy, dz)
    
    def batch_extract(self, entities: List[DXFEntity],
                     value_type: str) -> Dict[str, List[Dict]]:
        """
        批量提取实体中的数值
        
        Args:
            entities: 实体列表
            value_type: 数值类型
            
        Returns:
            Dict[str, List[Dict]]: 实体handle到数值列表的映射
        """
        results = {}
        
        for entity in entities:
            if not entity.text_content:
                continue
            
            value = self.extract_value(entity.text_content, value_type)
            if value:
                if entity.handle not in results:
                    results[entity.handle] = []
                results[entity.handle].append(value)
        
        return results
```

---

### 2.6 模块M05: 问题管理器 (IssueManager)

```python
# modules/issue_manager.py

from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
import json

class IssueManager:
    """
    问题管理器 - 审查问题的全生命周期管理
    
    职责：
    1. 收集和存储审查发现的问题
    2. 问题去重和合并
    3. 问题分类和优先级排序
    4. 问题状态跟踪（open -> confirmed -> resolved）
    5. 生成多角色视图
    6. 问题统计和报告
    
    问题生命周期：
    open -> confirmed -> resolved
       |        |          |
       v        v          v
    disputed  waived    reopened
    """
    
    def __init__(self):
        """初始化问题管理器"""
        self.issues: Dict[str, ReviewIssue] = {}  # issue_id -> issue
        self.issues_by_rule: Dict[str, List[str]] = defaultdict(list)  # rule_id -> issue_ids
        self.issues_by_drawing: Dict[str, List[str]] = defaultdict(list)  # drawing_id -> issue_ids
        self.issues_by_severity: Dict[str, List[str]] = defaultdict(list)  # severity -> issue_ids
        self.issues_by_category: Dict[str, List[str]] = defaultdict(list)  # category -> issue_ids
        
        # 去重索引
        self._duplicate_index: Dict[str, str] = {}  # hash -> issue_id
        
        # 统计
        self.stats = {
            'total_issues': 0,
            'open_issues': 0,
            'confirmed_issues': 0,
            'resolved_issues': 0,
            'disputed_issues': 0,
            'waived_issues': 0,
            'merged_issues': 0
        }
    
    def add_issue(self, issue: ReviewIssue,
                 check_duplicate: bool = True) -> Optional[str]:
        """
        添加问题
        
        Args:
            issue: 问题对象
            check_duplicate: 是否检查重复
            
        Returns:
            Optional[str]: 添加的问题ID，如果是重复则返回None
        """
        # 检查重复
        if check_duplicate:
            duplicate_id = self._check_duplicate(issue)
            if duplicate_id:
                # 合并重复问题
                self._merge_issues(duplicate_id, issue)
                self.stats['merged_issues'] += 1
                return None
        
        # 存储问题
        self.issues[issue.issue_id] = issue
        
        # 更新索引
        self.issues_by_rule[issue.rule_id].append(issue.issue_id)
        self.issues_by_drawing[issue.location.drawing_id].append(issue.issue_id)
        self.issues_by_severity[issue.severity.value].append(issue.issue_id)
        self.issues_by_category[issue.category].append(issue.issue_id)
        
        # 添加到去重索引
        dup_hash = self._compute_duplicate_hash(issue)
        self._duplicate_index[dup_hash] = issue.issue_id
        
        # 更新统计
        self.stats['total_issues'] += 1
        self.stats['open_issues'] += 1
        
        return issue.issue_id
    
    def add_issues(self, issues: List[ReviewIssue],
                  check_duplicate: bool = True) -> List[str]:
        """批量添加问题"""
        added_ids = []
        for issue in issues:
            issue_id = self.add_issue(issue, check_duplicate)
            if issue_id:
                added_ids.append(issue_id)
        return added_ids
    
    def _check_duplicate(self, issue: ReviewIssue) -> Optional[str]:
        """检查是否存在重复问题"""
        dup_hash = self._compute_duplicate_hash(issue)
        return self._duplicate_index.get(dup_hash)
    
    def _compute_duplicate_hash(self, issue: ReviewIssue) -> str:
        """
        计算问题去重哈希
        
        去重逻辑：同一规则 + 同一图纸 + 相似位置 = 重复
        """
        import hashlib
        
        # 使用规则ID、图纸ID和位置信息生成哈希
        location_key = ""
        if issue.location.bbox:
            # 将位置量化到网格（1米网格）
            grid_size = 1000  # 1米 = 1000单位
            center = issue.location.bbox.center
            grid_x = int(center.x / grid_size)
            grid_y = int(center.y / grid_size)
            location_key = f"{grid_x},{grid_y}"
        
        hash_input = f"{issue.rule_id}:{issue.location.drawing_id}:{location_key}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]
    
    def _merge_issues(self, existing_id: str, new_issue: ReviewIssue):
        """合并重复问题"""
        existing = self.issues.get(existing_id)
        if not existing:
            return
        
        # 保留更严重的等级
        severity_order = {'致命': 4, '严重': 3, '一般': 2, '轻微': 1, '提示': 0}
        if severity_order.get(new_issue.severity.value, 0) > severity_order.get(existing.severity.value, 0):
            existing.severity = new_issue.severity
        
        # 合并证据
        if new_issue.evidence_text and new_issue.evidence_text not in (existing.evidence_text or ''):
            existing.evidence_text = f"{existing.evidence_text or ''}; {new_issue.evidence_text}"
        
        # 合并关联图纸
        for drawing_id in new_issue.related_drawings:
            if drawing_id not in existing.related_drawings:
                existing.related_drawings.append(drawing_id)
    
    def update_status(self, issue_id: str, new_status: str,
                     resolution: Optional[str] = None,
                     assignee: Optional[str] = None) -> bool:
        """
        更新问题状态
        
        Args:
            issue_id: 问题ID
            new_status: 新状态
            resolution: 解决方案（可选）
            assignee: 指派人（可选）
            
        Returns:
            bool: 是否更新成功
        """
        issue = self.issues.get(issue_id)
        if not issue:
            return False
        
        old_status = issue.status
        issue.status = new_status
        
        if resolution:
            issue.resolution = resolution
        
        if assignee:
            issue.assignee = assignee
        
        # 更新时间戳
        from datetime import datetime
        if new_status == 'confirmed':
            issue.confirmed_at = datetime.now()
        elif new_status == 'resolved':
            issue.resolved_at = datetime.now()
        
        # 更新统计
        self._update_status_stats(old_status, new_status)
        
        return True
    
    def _update_status_stats(self, old_status: str, new_status: str):
        """更新状态统计"""
        status_map = {
            'open': 'open_issues',
            'confirmed': 'confirmed_issues',
            'resolved': 'resolved_issues',
            'disputed': 'disputed_issues',
            'waived': 'waived_issues'
        }
        
        if old_status in status_map:
            self.stats[status_map[old_status]] -= 1
        if new_status in status_map:
            self.stats[status_map[new_status]] += 1
    
    def get_issues(self, filters: Optional[Dict] = None) -> List[ReviewIssue]:
        """
        获取问题列表（支持过滤）
        
        Args:
            filters: 过滤条件
                - severity: 严重等级列表
                - status: 状态列表
                - category: 分类列表
                - rule_id: 规则ID
                - drawing_id: 图纸ID
                - assignee: 指派人
                
        Returns:
            List[ReviewIssue]: 问题列表
        """
        issues = list(self.issues.values())
        
        if not filters:
            return issues
        
        if 'severity' in filters:
            severities = filters['severity'] if isinstance(filters['severity'], list) else [filters['severity']]
            issues = [i for i in issues if i.severity.value in severities]
        
        if 'status' in filters:
            statuses = filters['status'] if isinstance(filters['status'], list) else [filters['status']]
            issues = [i for i in issues if i.status in statuses]
        
        if 'category' in filters:
            categories = filters['category'] if isinstance(filters['category'], list) else [filters['category']]
            issues = [i for i in issues if i.category in categories]
        
        if 'rule_id' in filters:
            issues = [i for i in issues if i.rule_id == filters['rule_id']]
        
        if 'drawing_id' in filters:
            issues = [i for i in issues if i.location.drawing_id == filters['drawing_id']]
        
        if 'assignee' in filters:
            issues = [i for i in issues if i.assignee == filters['assignee']]
        
        return issues
    
    def get_issues_by_role(self, role: str) -> List[ReviewIssue]:
        """
        获取特定角色关注的问题
        
        Args:
            role: 角色（designer, contractor, supervisor, owner）
            
        Returns:
            List[ReviewIssue]: 该角色关注的问题列表
        """
        all_issues = list(self.issues.values())
        
        if role == 'designer':
            # 设计师关注：所有需要修改的问题
            return [i for i in all_issues if i.status in ['open', 'confirmed', 'reopened']]
        
        elif role == 'contractor':
            # 施工方关注：可施工性问题、材料问题
            contractor_categories = ['可施工性', '材料', '工艺', '预留预埋']
            return [i for i in all_issues if i.category in contractor_categories]
        
        elif role == 'supervisor':
            # 监理关注：质量问题、安全问题、检测问题
            supervisor_categories = ['质量', '安全', '检测', '验收']
            return [i for i in all_issues if i.category in supervisor_categories or i.severity.value in ['致命', '严重']]
        
        elif role == 'owner':
            # 业主关注：影响功能、成本、进度的问题
            owner_categories = ['功能缺陷', '成本影响', '进度影响', '合规性']
            return [i for i in all_issues if i.category in owner_categories or i.severity.value == '致命']
        
        return all_issues
    
    def get_summary(self) -> Dict:
        """获取问题汇总统计"""
        return {
            'stats': self.stats,
            'by_severity': {
                severity: len(issue_ids)
                for severity, issue_ids in self.issues_by_severity.items()
            },
            'by_category': {
                category: len(issue_ids)
                for category, issue_ids in self.issues_by_category.items()
            },
            'by_status': {
                status: len([i for i in self.issues.values() if i.status == status])
                for status in ['open', 'confirmed', 'resolved', 'disputed', 'waived']
            }
        }
    
    def export_issues(self, output_path: str, format: str = 'json'):
        """导出问题列表"""
        if format == 'json':
            data = {
                'summary': self.get_summary(),
                'issues': [
                    {
                        'issue_id': i.issue_id,
                        'rule_id': i.rule_id,
                        'severity': i.severity.value,
                        'category': i.category,
                        'title': i.title,
                        'description': i.description,
                        'status': i.status,
                        'location': {
                            'drawing': i.location.drawing_name,
                            'floor': i.location.floor,
                            'grid': i.location.grid_reference
                        }
                    }
                    for i in self.issues.values()
                ]
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        elif format == 'csv':
            import csv
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', '规则', '严重等级', '分类', '标题', '状态', '图纸'])
                for issue in self.issues.values():
                    writer.writerow([
                        issue.issue_id,
                        issue.rule_id,
                        issue.severity.value,
                        issue.category,
                        issue.title,
                        issue.status,
                        issue.location.drawing_name
                    ])
```

---

### 2.7 模块M06: 施工进度生成器 (ScheduleGenerator)

```python
# modules/schedule_generator.py

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

class ScheduleGenerator:
    """
    施工进度生成器 - 基于图纸信息生成模拟施工进度计划
    
    职责：
    1. 分析图纸信息提取施工任务
    2. 根据专业逻辑建立任务依赖关系
    3. 估算任务工期
    4. 识别关键路径
    5. 关联审查问题到施工任务
    
    施工阶段定义：
    - 施工准备：临建、测量放线
    - 地基基础：土方、桩基、基础
    - 主体结构：钢筋、模板、混凝土
    - 机电预留预埋：随主体结构同步
    - 机电安装：管道、桥架、设备
    - 装饰装修：墙面、地面、吊顶
    - 调试检测：单机调试、系统联调
    - 竣工验收：专项验收、综合验收
    """
    
    # 标准工期参考（天/单位）
    STANDARD_DURATIONS = {
        # 基础工程
        'earthwork': {'unit': 'm³', 'rate': 50},           # 50m³/天
        'pile_foundation': {'unit': '根', 'rate': 2},      # 2根/天
        'foundation_slab': {'unit': 'm²', 'rate': 100},    # 100m²/天
        
        # 结构工程
        'rebar': {'unit': 't', 'rate': 2},                 # 2吨/天
        'formwork': {'unit': 'm²', 'rate': 50},            # 50m²/天
        'concrete': {'unit': 'm³', 'rate': 100},           # 100m³/天
        
        # 机电工程
        'electrical_conduit': {'unit': 'm', 'rate': 100},  # 100m/天
        'plumbing_pipe': {'unit': 'm', 'rate': 80},        # 80m/天
        'hvac_duct': {'unit': 'm²', 'rate': 30},           # 30m²/天
        'fire_sprinkler': {'unit': '头', 'rate': 20},      # 20头/天
        
        # 装修工程
        'wall_tiles': {'unit': 'm²', 'rate': 20},          # 20m²/天
        'floor_tiles': {'unit': 'm²', 'rate': 30},         # 30m²/天
        'ceiling': {'unit': 'm²', 'rate': 25},             # 25m²/天
        'painting': {'unit': 'm²', 'rate': 100},           # 100m²/天
    }
    
    # 任务依赖关系
    TASK_DEPENDENCIES = {
        'structure_floor': ['foundation_complete'],
        'mep_rough_floor': ['structure_floor'],
        'mep_install_floor': ['mep_rough_floor', 'structure_floor'],
        'finish_wall': ['mep_install_floor'],
        'finish_ceiling': ['mep_install_floor'],
        'testing': ['finish_wall', 'finish_ceiling'],
        'acceptance': ['testing'],
    }
    
    def __init__(self):
        """初始化进度生成器"""
        self.tasks: List[ConstructionTask] = []
        self.task_map: Dict[str, ConstructionTask] = {}
        self.project_context: Optional[ProjectContext] = None
    
    def generate_schedule(self, project_context: ProjectContext,
                         drawings: List[DrawingFile],
                         issues: List[ReviewIssue],
                         start_date: Optional[datetime] = None) -> ConstructionSchedule:
        """
        生成施工进度计划
        
        Args:
            project_context: 项目上下文
            drawings: 图纸列表
            issues: 审查问题列表
            start_date: 计划开工日期
            
        Returns:
            ConstructionSchedule: 施工进度计划
        """
        self.project_context = project_context
        
        if not start_date:
            start_date = datetime.now()
        
        # 步骤1: 从图纸提取施工任务
        self._extract_tasks_from_drawings(drawings)
        
        # 步骤2: 建立任务依赖关系
        self._establish_dependencies()
        
        # 步骤3: 估算任务工期
        self._estimate_durations()
        
        # 步骤4: 关联审查问题
        self._link_issues_to_tasks(issues)
        
        # 步骤5: 计算关键路径
        critical_path = self._calculate_critical_path()
        
        # 步骤6: 生成里程碑
        milestones = self._generate_milestones(start_date)
        
        # 步骤7: 计算总体时间
        project_end = self._calculate_project_end(start_date)
        
        return ConstructionSchedule(
            schedule_id=f"schedule_{project_context.project_id}",
            project_id=project_context.project_id,
            tasks=self.tasks,
            critical_path=critical_path,
            milestones=milestones,
            project_start=start_date,
            project_end=project_end,
            total_duration_days=(project_end - start_date).days if project_end else None,
            review_recommendations=self._generate_review_recommendations()
        )
    
    def _extract_tasks_from_drawings(self, drawings: List[DrawingFile]):
        """从图纸提取施工任务"""
        for drawing in drawings:
            # 根据图纸类型和专业生成任务
            tasks = self._create_tasks_for_drawing(drawing)
            for task in tasks:
                self.tasks.append(task)
                self.task_map[task.task_id] = task
    
    def _create_tasks_for_drawing(self, drawing: DrawingFile) -> List[ConstructionTask]:
        """为单张图纸创建施工任务"""
        tasks = []
        
        # 根据专业和楼层创建任务
        if drawing.discipline == Discipline.STRUC:
            # 结构图纸 -> 结构施工任务
            for floor in drawing.floor_range.split('-') if drawing.floor_range else ['1F']:
                task = ConstructionTask(
                    task_id=f"struct_{drawing.building_name}_{floor}",
                    task_name=f"{drawing.building_name} {floor} 结构施工",
                    task_type="结构",
                    building_id=drawing.building_name,
                    floor_ids=[floor],
                    required_drawings=[drawing.file_path]
                )
                tasks.append(task)
        
        elif drawing.discipline in [Discipline.ELEC, Discipline.HVAC, Discipline.PLUMB]:
            # 机电图纸 -> 机电安装任务
            for floor in drawing.floor_range.split('-') if drawing.floor_range else ['1F']:
                # 预留预埋任务
                rough_task = ConstructionTask(
                    task_id=f"mep_rough_{drawing.discipline.value}_{floor}",
                    task_name=f"{floor} {drawing.discipline.value}预留预埋",
                    task_type="机电预留预埋",
                    building_id=drawing.building_name,
                    floor_ids=[floor],
                    required_drawings=[drawing.file_path]
                )
                tasks.append(rough_task)
                
                # 安装任务
                install_task = ConstructionTask(
                    task_id=f"mep_install_{drawing.discipline.value}_{floor}",
                    task_name=f"{floor} {drawing.discipline.value}安装",
                    task_type="机电安装",
                    building_id=drawing.building_name,
                    floor_ids=[floor],
                    required_drawings=[drawing.file_path],
                    prerequisites=[rough_task.task_id]
                )
                tasks.append(install_task)
        
        return tasks
    
    def _establish_dependencies(self):
        """建立任务依赖关系"""
        for task in self.tasks:
            # 自动添加标准依赖
            if task.task_type == "结构":
                # 结构任务依赖基础完成
                task.prerequisites.append("foundation_complete")
            
            elif task.task_type == "机电预留预埋":
                # 预留预埋依赖同楼层结构完成
                floor_struct_task = f"struct_{task.building_id}_{task.floor_ids[0]}"
                if floor_struct_task in self.task_map:
                    task.prerequisites.append(floor_struct_task)
            
            elif task.task_type == "机电安装":
                # 安装依赖预留预埋和结构
                floor_rough_task = f"mep_rough_{task.task_id.split('_')[2]}_{task.floor_ids[0]}"
                if floor_rough_task in self.task_map:
                    task.prerequisites.append(floor_rough_task)
    
    def _estimate_durations(self):
        """估算任务工期"""
        for task in self.tasks:
            # 根据任务类型和工程量估算
            if task.task_type == "结构":
                # 标准楼层结构施工：7-10天
                task.estimated_duration_days = 8
            elif task.task_type == "机电预留预埋":
                # 随结构同步：2-3天
                task.estimated_duration_days = 2
            elif task.task_type == "机电安装":
                # 标准楼层机电安装：5-7天
                task.estimated_duration_days = 6
    
    def _link_issues_to_tasks(self, issues: List[ReviewIssue]):
        """关联审查问题到施工任务"""
        for issue in issues:
            # 根据问题位置和类型找到关联任务
            for task in self.tasks:
                if self._is_issue_related_to_task(issue, task):
                    task.related_issues.append(issue.issue_id)
                    # 如果问题严重，标记任务为高风险
                    if issue.severity.value in ['致命', '严重']:
                        task.risk_level = 'high'
    
    def _is_issue_related_to_task(self, issue: ReviewIssue, task: ConstructionTask) -> bool:
        """判断问题是否与任务相关"""
        # 检查图纸关联
        if issue.location.drawing_id in task.required_drawings:
            return True
        
        # 检查楼层关联
        if issue.location.floor and issue.location.floor in task.floor_ids:
            return True
        
        return False
    
    def _calculate_critical_path(self) -> List[str]:
        """计算关键路径"""
        # 使用拓扑排序找到关键路径
        # 简化实现：按楼层和专业顺序
        critical_path = []
        
        # 按楼层分组
        floor_tasks: Dict[str, List[str]] = {}
        for task in self.tasks:
            for floor in task.floor_ids:
                if floor not in floor_tasks:
                    floor_tasks[floor] = []
                floor_tasks[floor].append(task.task_id)
        
        # 按楼层顺序排列
        sorted_floors = sorted(floor_tasks.keys(), 
                              key=lambda f: int(f.replace('F', '').replace('B', '-')))
        
        for floor in sorted_floors:
            # 每个楼层的关键路径：结构 -> 机电预留 -> 机电安装
            struct_task = next((t for t in floor_tasks[floor] if 'struct' in t), None)
            rough_task = next((t for t in floor_tasks[floor] if 'rough' in t), None)
            install_task = next((t for t in floor_tasks[floor] if 'install' in t), None)
            
            if struct_task:
                critical_path.append(struct_task)
            if rough_task:
                critical_path.append(rough_task)
            if install_task:
                critical_path.append(install_task)
        
        return critical_path
    
    def _generate_milestones(self, start_date: datetime) -> List[Dict]:
        """生成里程碑节点"""
        milestones = []
        
        # 基础完成
        foundation_end = start_date + timedelta(days=30)
        milestones.append({
            'name': '基础工程完成',
            'date': foundation_end,
            'type': 'phase_complete'
        })
        
        # 结构封顶（假设10层，每层8天）
        structure_end = foundation_end + timedelta(days=80)
        milestones.append({
            'name': '主体结构封顶',
            'date': structure_end,
            'type': 'phase_complete'
        })
        
        # 机电安装完成
        mep_end = structure_end + timedelta(days=60)
        milestones.append({
            'name': '机电安装完成',
            'date': mep_end,
            'type': 'phase_complete'
        })
        
        # 竣工验收
        acceptance_date = mep_end + timedelta(days=30)
        milestones.append({
            'name': '竣工验收',
            'date': acceptance_date,
            'type': 'project_complete'
        })
        
        return milestones
    
    def _calculate_project_end(self, start_date: datetime) -> datetime:
        """计算项目结束日期"""
        # 简化计算：基础30天 + 结构80天 + 机电60天 + 装修60天 + 验收30天
        total_days = 30 + 80 + 60 + 60 + 30
        return start_date + timedelta(days=total_days)
    
    def _generate_review_recommendations(self) -> List[str]:
        """生成审查建议"""
        recommendations = []
        
        # 检查高风险任务
        high_risk_tasks = [t for t in self.tasks if t.risk_level == 'high']
        if high_risk_tasks:
            recommendations.append(
                f"发现{len(high_risk_tasks)}个高风险任务，建议在施工前优先解决相关审查问题"
            )
        
        # 检查关键路径上的任务
        critical_tasks = [t for t in self.tasks if t.task_id in self._calculate_critical_path()]
        recommendations.append(
            f"关键路径包含{len(critical_tasks)}个任务，建议重点关注"
        )
        
        return recommendations


# ============ 第三部分：系统数据流与状态机 ============

## 3.1 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              AI智能审图系统 v6.0 数据流                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  Input Layer                                                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │ DXF Files   │  │ Project Info│  │ Rules DB    │  │ Config      │                │
│  │ (5-20 files)│  │ (JSON/YAML) │  │ (500+ rules)│  │ (YAML)      │                │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                │
│         │                │                │                │                        │
│         ▼                ▼                ▼                ▼                        │
│  ┌─────────────────────────────────────────────────────────────────┐               │
│  │                     Extraction Phase                             │               │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │               │
│  │  │ File Hash   │─▶│ DXF Parse   │─▶│ Entity      │             │               │
│  │  │ Check       │  │ (ezdxf)     │  │ Extract     │             │               │
│  │  └─────────────┘  └─────────────┘  └─────────────┘             │               │
│  │         │                                    │                  │               │
│  │         │ Cache Hit                          ▼                  │               │
│  │         └─────────────────────────────▶┌─────────────┐         │               │
│  │                                        │ Unified     │         │               │
│  │                                        │ Entity List │         │               │
│  │                                        └──────┬──────┘         │               │
│  └───────────────────────────────────────────────┼────────────────┘               │
│                                                  │                                  │
│                                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────────┐               │
│  │                     Indexing Phase                               │               │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │               │
│  │  │ Spatial     │  │ Discipline  │  │ Floor       │             │               │
│  │  │ Index       │  │ Index       │  │ Index       │             │               │
│  │  │ (R-tree)    │  │ (Hash Map)  │  │ (Hash Map)  │             │               │
│  │  └─────────────┘  └─────────────┘  └─────────────┘             │               │
│  │         │                │                │                     │               │
│  │         └────────────────┴────────────────┘                     │               │
│  │                            │                                    │               │
│  │                            ▼                                    │               │
│  │                   ┌─────────────────┐                           │               │
│  │                   │ Project Context │                           │               │
│  │                   │ (Global Params) │                           │               │
│  │                   └────────┬────────┘                           │               │
│  └────────────────────────────┼────────────────────────────────────┘               │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐               │
│  │                     Rule Filtering Phase                         │               │
│  │                                                                  │               │
│  │   Input: 500 rules                                               │               │
│  │      │                                                           │               │
│  │      ▼                                                           │               │
│  │   ┌─────────────────────────────────────────────────────────┐   │               │
│  │   │ Filter Chain:                                           │   │               │
│  │   │ 1. By Discipline    500 ──▶ 80 rules (建筑)              │   │               │
│  │   │ 2. By Check Level    80 ──▶ 60 rules (L1+L2)             │   │               │
│  │   │ 3. By Project Type   60 ──▶ 50 rules (住宅)              │   │               │
│  │   │ 4. By Phase          50 ──▶ 40 rules (当前阶段)          │   │               │
│  │   └─────────────────────────────────────────────────────────┘   │               │
│  │                            │                                     │               │
│  │                            ▼                                     │               │
│  │                   Filtered Rule Set (40 rules)                   │               │
│  └────────────────────────────┬────────────────────────────────────┘               │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐               │
│  │                     Execution Phase                              │               │
│  │                                                                  │               │
│  │   ┌─────────────────────────────────────────────────────────┐   │               │
│  │   │ Parallel Execution (4 workers)                          │   │               │
│  │   │                                                         │   │               │
│  │   │  Worker 1: Rule 1-10  ──▶ Results 1-10                  │   │               │
│  │   │  Worker 2: Rule 11-20 ──▶ Results 11-20                 │   │               │
│  │   │  Worker 3: Rule 21-30 ──▶ Results 21-30                 │   │               │
│  │   │  Worker 4: Rule 31-40 ──▶ Results 31-40                 │   │               │
│  │   │                                                         │   │               │
│  │   │  Cache Check: Skip if (file_hash + rule_id) match       │   │               │
│  │   └─────────────────────────────────────────────────────────┘   │               │
│  │                            │                                     │               │
│  │                            ▼                                     │               │
│  │   ┌─────────────────────────────────────────────────────────┐   │               │
│  │   │ Check Results (40 rules × 5 drawings = 200 checks)      │   │               │
│  │   │                                                         │   │               │
│  │   │ Status Distribution:                                    │   │               │
│  │   │ - Passed:   150 checks                                  │   │               │
│  │   │ - Failed:   40 checks  ──▶ Issues                       │   │               │
│  │   │ - Skipped:   8 checks                                   │   │               │
│  │   │ - Error:     2 checks                                   │   │               │
│  │   └─────────────────────────────────────────────────────────┘   │               │
│  └────────────────────────────┬────────────────────────────────────┘               │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐               │
│  │                     Issue Processing Phase                       │               │
│  │                                                                  │               │
│  │   Raw Issues (40)                                                │               │
│  │      │                                                           │               │
│  │      ▼                                                           │               │
│  │   ┌─────────────────────────────────────────────────────────┐   │               │
│  │   │ Deduplication                                           │   │               │
│  │   │ - Same rule + same location = duplicate                 │   │               │
│  │   │ - 40 issues ──▶ 35 unique issues                        │   │               │
│  │   └─────────────────────────────────────────────────────────┘   │               │
│  │                            │                                     │               │
│  │                            ▼                                     │               │
│  │   ┌─────────────────────────────────────────────────────────┐   │               │
│  │   │ Severity Classification                                 │   │               │
│  │   │ - Critical: 5 issues                                    │   │               │
│  │   │ - High:    10 issues                                    │   │               │
│  │   │ - Medium:  15 issues                                    │   │               │
│  │   │ - Low:      5 issues                                    │   │               │
│  │   └─────────────────────────────────────────────────────────┘   │               │
│  │                            │                                     │               │
│  │                            ▼                                     │               │
│  │   ┌─────────────────────────────────────────────────────────┐   │               │
│  │   │ Role-based Distribution                                 │   │               │
│  │   │ - Designer:    35 issues (all)                          │   │               │
│  │   │ - Contractor:  20 issues (constructability)             │   │               │
│  │   │ - Supervisor:  15 issues (quality/safety)               │   │               │
│  │   │ - Owner:        5 issues (critical only)                │   │               │
│  │   └─────────────────────────────────────────────────────────┘   │               │
│  └────────────────────────────┬────────────────────────────────────┘               │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐               │
│  │                     Output Generation Phase                      │               │
│  │                                                                  │               │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │               │
│  │   │ JSON Report │  │ Excel Report│  │ PDF Report  │             │               │
│  │   │ (Machine)   │  │ (Human)     │  │ (Formal)    │             │               │
│  │   └─────────────┘  └─────────────┘  └─────────────┘             │               │
│  │                                                                  │               │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │               │
│  │   │ Schedule    │  │ Cost Impact │  │ Risk Report │             │               │
│  │   │ (Gantt)     │  │ Analysis    │  │ (High Risk) │             │               │
│  │   └─────────────┘  └─────────────┘  └─────────────┘             │               │
│  └─────────────────────────────────────────────────────────────────┘               │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## 3.2 审查流程状态机

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              审查流程状态机                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│                              ┌─────────────┐                                        │
│                              │    IDLE     │                                        │
│                              │  (初始状态)  │                                        │
│                              └──────┬──────┘                                        │
│                                     │ start_review()                                 │
│                                     ▼                                               │
│                              ┌─────────────┐                                        │
│                              │  EXTRACTING │◄──────────────────┐                   │
│                              │  (提取中)   │                   │                   │
│                              └──────┬──────┘                   │                   │
│                                     │ extraction_complete        │                   │
│                                     ▼                          │ retry_extraction   │
│                              ┌─────────────┐                   │                   │
│                              │  INDEXING   │◄──────────────────┤                   │
│                              │  (索引中)   │                   │                   │
│                              └──────┬──────┘                   │                   │
│                                     │ indexing_complete          │                   │
│                                     ▼                          │                   │
│                              ┌─────────────┐                   │                   │
│                              │  FILTERING  │◄──────────────────┤                   │
│                              │  (过滤规则) │                   │                   │
│                              └──────┬──────┘                   │                   │
│                                     │ filtering_complete         │                   │
│                                     ▼                          │                   │
│                              ┌─────────────┐                   │                   │
│                              │  CHECKING   │◄──────────────────┤                   │
│                              │  (检查中)   │───────────────────┤                   │
│                              └──────┬──────┘  check_progress    │                   │
│                                     │                          │                   │
│                    ┌────────────────┼────────────────┐         │                   │
│                    │                │                │         │                   │
│                    ▼                ▼                ▼         │                   │
│             ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │                   │
│             │  PASSED     │ │  FAILED     │ │  SKIPPED    │   │                   │
│             │  (通过)     │ │  (失败)     │ │  (跳过)     │   │                   │
│             └─────────────┘ └──────┬──────┘ └─────────────┘   │                   │
│                                    │                          │                   │
│                                    ▼                          │                   │
│                             ┌─────────────┐                   │                   │
│                             │  ISSUE_GEN  │                   │                   │
│                             │ (生成问题)  │                   │                   │
│                             └──────┬──────┘                   │                   │
│                                    │                          │                   │
│                                    ▼                          │                   │
│  ┌─────────────────────────────────────────────────────────┐  │                   │
│  │                    CHECK_COMPLETE                        │  │                   │
│  │                    (检查完成)                            │  │                   │
│  └─────────────────────────────────────────────────────────┘  │                   │
│                                    │                          │                   │
│                                    ▼                          │                   │
│  ┌─────────────────────────────────────────────────────────┐  │                   │
│  │                    REPORT_GENERATING                     │  │                   │
│  │                    (生成报告中)                          │  │                   │
│  └─────────────────────────────────────────────────────────┘  │                   │
│                                    │                          │                   │
│                                    ▼                          │                   │
│                              ┌─────────────┐                  │                   │
│                              │  COMPLETED  │                  │                   │
│                              │  (已完成)   │──────────────────┘                   │
│                              └─────────────┘     export_results                    │
│                                    │                                               │
│                                    ▼                                               │
│                              ┌─────────────┐                                       │
│                              │    ERROR    │◄─────────────────────────────┐       │
│                              │  (错误状态)  │                              │       │
│                              └─────────────┘                              │       │
│                                    │                                      │       │
│                                    └──────────────────────────────────────┘       │
│                                              any_error                              │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## 3.3 问题生命周期状态机

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              问题生命周期状态机                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌─────────────┐                                                                   │
│   │   DETECTED  │  (系统自动检测)                                                    │
│   │  (检测到)   │                                                                   │
│   └──────┬──────┘                                                                   │
│          │ auto_create_issue                                                        │
│          ▼                                                                          │
│   ┌─────────────┐     confirm()      ┌─────────────┐                               │
│   │    OPEN     │───────────────────▶│  CONFIRMED  │                               │
│   │  (待确认)   │                    │  (已确认)   │                               │
│   └──────┬──────┘                    └──────┬──────┘                               │
│          │                                  │                                       │
│          │ dispute()                        │ resolve()                            │
│          ▼                                  ▼                                       │
│   ┌─────────────┐                    ┌─────────────┐                               │
│   │  DISPUTED   │                    │  RESOLVED   │                               │
│   │  (有争议)   │                    │  (已解决)   │                               │
│   └──────┬──────┘                    └──────┬──────┘                               │
│          │                                  │                                       │
│          │ resolve_dispute()                │ reopen()                             │
│          │ or waive()                       │                                      │
│          ▼                                  ▼                                       │
│   ┌─────────────┐                    ┌─────────────┐                               │
│   │   WAIVED    │◄───────────────────│  REOPENED   │                               │
│   │  (已豁免)   │     waive()        │  (重新打开) │                               │
│   └─────────────┘                    └──────┬──────┘                               │
│                                             │                                       │
│                                             └───────────────────────────────────────┘
│                                                            confirm()                │
│                                                                                     │
│   状态说明：                                                                          │
│   - DETECTED: 系统通过规则检查自动检测到潜在问题                                       │
│   - OPEN: 问题已创建，等待人工确认                                                     │
│   - CONFIRMED: 问题已确认，需要修改                                                    │
│   - DISPUTED: 对问题存在争议，需要讨论                                                 │
│   - RESOLVED: 问题已解决/修改完成                                                      │
│   - WAIVED: 问题被豁免（如设计变更、规范特例等）                                        │
│   - REOPENED: 已解决的问题重新打开                                                     │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 第四部分：性能优化策略（代码级）

### 4.1 增量缓存实现

```python
# modules/cache_manager.py

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timedelta

class CacheManager:
    """
    缓存管理器 - 实现多级缓存策略
    
    缓存层级：
    1. L1: 内存缓存（最快，重启丢失）
    2. L2: 本地文件缓存（较快，持久化）
    3. L3: 分布式缓存（较慢，共享）
    """
    
    def __init__(self, cache_dir: str = ".cache", ttl: int = 86400):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录
            ttl: 缓存有效期（秒）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl = ttl
        
        # L1: 内存缓存
        self._memory_cache: Dict[str, Any] = {}
        self._memory_meta: Dict[str, Dict] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        查找顺序：L1 -> L2 -> L3
        """
        # L1: 内存缓存
        if key in self._memory_cache:
            meta = self._memory_meta.get(key)
            if meta and not self._is_expired(meta):
                return self._memory_cache[key]
            else:
                # 过期，清理
                del self._memory_cache[key]
                del self._memory_meta[key]
        
        # L2: 文件缓存
        cache_file = self.cache_dir / f"{key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                
                if not self._is_expired(data.get('meta', {})):
                    # 提升到L1
                    self._memory_cache[key] = data['value']
                    self._memory_meta[key] = data['meta']
                    return data['value']
                else:
                    # 过期，删除
                    cache_file.unlink()
            except Exception:
                pass
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存值
        
        写入顺序：L1 + L2
        """
        ttl = ttl or self.ttl
        meta = {
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(seconds=ttl),
            'size': len(pickle.dumps(value))
        }
        
        # L1: 内存缓存
        self._memory_cache[key] = value
        self._memory_meta[key] = meta
        
        # L2: 文件缓存
        cache_file = self.cache_dir / f"{key}.pkl"
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({'value': value, 'meta': meta}, f)
        except Exception as e:
            print(f"Cache write error: {e}")
    
    def _is_expired(self, meta: Dict) -> bool:
        """检查缓存是否过期"""
        expires_at = meta.get('expires_at')
        if not expires_at:
            return True
        return datetime.now() > expires_at
    
    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """计算文件哈希（用于增量检测）"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def clear_expired(self):
        """清理过期缓存"""
        # 清理L1
        expired_keys = [
            k for k, meta in self._memory_meta.items()
            if self._is_expired(meta)
        ]
        for k in expired_keys:
            del self._memory_cache[k]
            del self._memory_meta[k]
        
        # 清理L2
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                if self._is_expired(data.get('meta', {})):
                    cache_file.unlink()
            except Exception:
                pass


# 使用示例：增量提取
class IncrementalExtractor:
    """增量提取器"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    def extract(self, file_path: str) -> DrawingFile:
        """增量提取"""
        # 计算文件哈希
        file_hash = self.cache.compute_file_hash(file_path)
        cache_key = f"extraction:{file_hash}"
        
        # 检查缓存
        cached = self.cache.get(cache_key)
        if cached:
            print(f"Cache hit: {file_path}")
            return cached
        
        # 缓存未命中，执行提取
        print(f"Cache miss: {file_path}")
        result = self._do_extract(file_path)
        
        # 保存到缓存
        self.cache.set(cache_key, result)
        
        return result
    
    def _do_extract(self, file_path: str) -> DrawingFile:
        """实际提取逻辑"""
        # ... 提取代码
        pass
```

### 4.2 并行处理实现

```python
# modules/parallel_processor.py

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import List, Callable, TypeVar, Generic
import multiprocessing as mp

T = TypeVar('T')
R = TypeVar('R')

class ParallelProcessor:
    """
    并行处理器 - 统一的并行处理接口
    
    支持两种并行模式：
    1. 多进程：CPU密集型任务（规则检查）
    2. 多线程：IO密集型任务（文件读取）
    """
    
    def __init__(self, max_workers: Optional[int] = None):
        """
        初始化并行处理器
        
        Args:
            max_workers: 最大工作进程/线程数，None表示使用CPU核心数
        """
        self.max_workers = max_workers or mp.cpu_count()
    
    def process_map(self, 
                   func: Callable[[T], R], 
                   items: List[T],
                   use_processes: bool = True,
                   chunksize: int = 1) -> List[R]:
        """
        并行处理列表
        
        Args:
            func: 处理函数
            items: 输入列表
            use_processes: 是否使用多进程（True=多进程，False=多线程）
            chunksize: 每个工作单元的任务数
            
        Returns:
            List[R]: 处理结果列表（保持输入顺序）
        """
        Executor = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        
        with Executor(max_workers=self.max_workers) as executor:
            results = list(executor.map(func, items, chunksize=chunksize))
        
        return results
    
    def process_async(self,
                     func: Callable[[T], R],
                     items: List[T],
                     use_processes: bool = True,
                     callback: Optional[Callable[[int, int], None]] = None) -> List[R]:
        """
        异步并行处理（带进度回调）
        
        Args:
            func: 处理函数
            items: 输入列表
            use_processes: 是否使用多进程
            callback: 进度回调函数(completed, total)
            
        Returns:
            List[R]: 处理结果列表
        """
        Executor = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        results = [None] * len(items)
        
        with Executor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(func, item): i 
                for i, item in enumerate(items)
            }
            
            # 收集结果
            completed = 0
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    results[index] = e
                
                completed += 1
                if callback:
                    callback(completed, len(items))
        
        return results


# 使用示例：并行规则检查
class ParallelRuleChecker:
    """并行规则检查器"""
    
    def __init__(self, rule_engine: RuleEngine, max_workers: int = 4):
        self.rule_engine = rule_engine
        self.processor = ParallelProcessor(max_workers)
    
    def check_drawings(self, 
                      rules: List[ReviewRule],
                      drawings: List[DrawingFile],
                      entities_map: Dict[str, List[DXFEntity]],
                      project_context: ProjectContext) -> List[CheckResult]:
        """并行检查多个图纸"""
        
        # 构建任务列表
        tasks = []
        for rule in rules:
            for drawing in drawings:
                entities = entities_map.get(drawing.file_path, [])
                tasks.append((rule, drawing, entities, project_context))
        
        # 并行执行
        def check_task(task):
            rule, drawing, entities, context = task
            return self.rule_engine.execute_check(rule, drawing, entities, context)
        
        results = self.processor.process_async(
            check_task, tasks, use_processes=True
        )
        
        return results
```

---

## 第五部分：规则库JSON Schema

### 5.1 完整规则定义Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AI智能审图系统规则库",
  "description": "v6.0规则库JSON Schema定义",
  "type": "object",
  "required": ["version", "rulesets"],
  "properties": {
    "version": {
      "type": "string",
      "description": "规则库版本",
      "enum": ["6.0"]
    },
    "metadata": {
      "type": "object",
      "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "author": {"type": "string"},
        "total_rules": {"type": "integer"}
      }
    },
    "rulesets": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/ruleset"
      }
    }
  },
  "definitions": {
    "ruleset": {
      "type": "object",
      "required": ["ruleset_id", "ruleset_name", "discipline", "phase", "rules"],
      "properties": {
        "ruleset_id": {
          "type": "string",
          "pattern": "^[a-z][a-z0-9_]*$"
        },
        "ruleset_name": {"type": "string"},
        "discipline": {
          "type": "string",
          "enum": ["建筑", "结构", "电气", "暖通", "给排水", "消防", "智能化"]
        },
        "phase": {
          "type": "string",
          "enum": ["设计阶段", "施工准备", "地基基础", "主体结构", "机电安装", "装饰装修", "竣工验收"]
        },
        "rules": {
          "type": "array",
          "items": {
            "$ref": "#/definitions/rule"
          }
        }
      }
    },
    "rule": {
      "type": "object",
      "required": ["rule_id", "rule_name", "check_level", "description"],
      "properties": {
        "rule_id": {
          "type": "string",
          "description": "规则唯一标识",
          "examples": ["GB50016-2022-5.5.8", "FIRE-EXIT-001"]
        },
        "rule_name": {"type": "string"},
        "rule_category": {
          "type": "string",
          "enum": ["强制条文", "行业最佳实践", "项目特殊要求", "专业协调"],
          "default": "强制条文"
        },
        "check_level": {
          "type": "integer",
          "minimum": 1,
          "maximum": 4,
          "description": "1=合规性, 2=可施工性, 3=可检测性, 4=可维护性"
        },
        "applicable_disciplines": {
          "type": "array",
          "items": {"type": "string"}
        },
        "applicable_project_types": {
          "type": "array",
          "items": {"type": "string"}
        },
        "applicable_phases": {
          "type": "array",
          "items": {"type": "string"}
        },
        "description": {"type": "string"},
        "code_reference": {"type": "string"},
        "code_clause": {"type": "string"},
        "preconditions": {
          "type": "array",
          "items": {"$ref": "#/definitions/condition"}
        },
        "check_conditions": {
          "type": "array",
          "items": {"$ref": "#/definitions/condition"}
        },
        "fail_action": {"$ref": "#/definitions/action"},
        "pass_action": {"$ref": "#/definitions/action"},
        "priority": {
          "type": "integer",
          "minimum": 1,
          "default": 100
        },
        "enabled": {
          "type": "boolean",
          "default": true
        },
        "version": {
          "type": "string",
          "default": "1.0"
        },
        "source_document": {"type": "string"}
      }
    },
    "condition": {
      "type": "object",
      "required": ["condition_type"],
      "properties": {
        "condition_id": {"type": "string"},
        "condition_type": {
          "type": "string",
          "enum": ["keyword_exact", "keyword_any", "regex", "value_compare", "spatial_check", "cross_reference", "calculation"]
        },
        "keywords": {
          "type": "array",
          "items": {"type": "string"}
        },
        "keyword_logic": {
          "type": "string",
          "enum": ["AND", "OR"],
          "default": "OR"
        },
        "regex_pattern": {"type": "string"},
        "regex_flags": {"type": "integer", "default": 0},
        "value_path": {"type": "string"},
        "operator": {
          "type": "string",
          "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "in", "between"]
        },
        "target_value": {},
        "tolerance": {"type": "number"},
        "spatial_relation": {
          "type": "string",
          "enum": ["contains", "intersects", "distance"]
        },
        "reference_entities": {
          "type": "array",
          "items": {"type": "string"}
        },
        "distance_threshold": {"type": "number"},
        "source_drawing": {"type": "string"},
        "target_drawing": {"type": "string"},
        "cross_field": {"type": "string"}
      }
    },
    "action": {
      "type": "object",
      "required": ["action_type"],
      "properties": {
        "action_type": {
          "type": "string",
          "enum": ["flag_issue", "extract_value", "update_context"]
        },
        "issue_template": {"type": "string"},
        "severity": {
          "type": "string",
          "enum": ["致命", "严重", "一般", "轻微", "提示"],
          "default": "一般"
        },
        "value_mapping": {
          "type": "object"
        }
      }
    }
  }
}
```

### 5.2 规则示例

```json
{
  "rule_id": "GB50016-2022-5.5.8",
  "rule_name": "公共建筑疏散门净宽度检查",
  "rule_category": "强制条文",
  "check_level": 1,
  "applicable_disciplines": ["建筑"],
  "applicable_project_types": ["公共建筑", "商业建筑", "办公建筑"],
  "applicable_phases": ["设计阶段", "施工准备"],
  "description": "公共建筑内疏散门和安全出口的净宽度不应小于0.90m",
  "code_reference": "《建筑设计防火规范》GB50016-2022 第5.5.8条",
  "code_clause": "5.5.8",
  "preconditions": [
    {
      "condition_type": "keyword_any",
      "keywords": ["疏散门", "安全出口", "出口"],
      "keyword_logic": "OR"
    }
  ],
  "check_conditions": [
    {
      "condition_type": "value_compare",
      "value_path": "entity.dimension",
      "operator": "gte",
      "target_value": 0.9,
      "tolerance": 0.01
    }
  ],
  "fail_action": {
    "action_type": "flag_issue",
    "issue_template": "在{drawing_name}中发现疏散门/安全出口净宽度为{entity.dimension}m，小于规范要求的0.90m。请按{code_reference}进行修改。",
    "severity": "严重"
  },
  "priority": 10,
  "enabled": true,
  "version": "1.0",
  "source_document": "GB50016-2022"
}
```

---

## 第六部分：API接口定义

### 6.1 RESTful API设计

```yaml
# api/openapi.yaml

openapi: 3.0.0
info:
  title: AI智能审图系统 API
  version: 6.0.0
  description: 智能审图系统的RESTful API接口

servers:
  - url: http://localhost:8000/api/v6

paths:
  /projects:
    post:
      summary: 创建项目
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProjectCreate'
      responses:
        201:
          description: 项目创建成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Project'

  /projects/{project_id}/drawings:
    post:
      summary: 上传图纸
      parameters:
        - name: project_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                files:
                  type: array
                  items:
                    type: string
                    format: binary
      responses:
        200:
          description: 上传成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  uploaded:
                    type: integer
                  failed:
                    type: integer
                  drawings:
                    type: array
                    items:
                      $ref: '#/components/schemas/DrawingFile'

  /projects/{project_id}/review:
    post:
      summary: 启动审查
      parameters:
        - name: project_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                check_level:
                  type: integer
                  enum: [1, 2, 3, 4]
                disciplines:
                  type: array
                  items:
                    type: string
                phases:
                  type: array
                  items:
                    type: string
      responses:
        202:
          description: 审查已启动
          content:
            application/json:
              schema:
                type: object
                properties:
                  review_id:
                    type: string
                  status:
                    type: string
                    enum: [pending, running, completed, failed]

  /reviews/{review_id}:
    get:
      summary: 获取审查状态
      parameters:
        - name: review_id
          in: path
          required: true
          schema:
            type: string
      responses:
        200:
          description: 审查状态
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ReviewStatus'

  /reviews/{review_id}/report:
    get:
      summary: 获取审查报告
      parameters:
        - name: review_id
          in: path
          required: true
          schema:
            type: string
        - name: format
          in: query
          schema:
            type: string
            enum: [json, pdf, excel]
            default: json
        - name: role
          in: query
          schema:
            type: string
            enum: [designer, contractor, supervisor, owner]
      responses:
        200:
          description: 审查报告
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ReviewReport'
            application/pdf:
              schema:
                type: string
                format: binary

components:
  schemas:
    Project:
      type: object
      properties:
        project_id:
          type: string
        project_name:
          type: string
        project_type:
          type: string
        created_at:
          type: string
          format: date-time
        status:
          type: string
          enum: [active, archived]

    DrawingFile:
      type: object
      properties:
        file_path:
          type: string
        file_hash:
          type: string
        drawing_type:
          type: string
        discipline:
          type: string
        drawing_number:
          type: string
        drawing_name:
          type: string
        parse_status:
          type: string
          enum: [pending, parsing, completed, error]

    ReviewStatus:
      type: object
      properties:
        review_id:
          type: string
        status:
          type: string
        progress:
          type: number
          minimum: 0
          maximum: 100
        started_at:
          type: string
          format: date-time
        completed_at:
          type: string
          format: date-time
        stats:
          type: object
          properties:
            total_rules:
              type: integer
            checked_rules:
              type: integer
            issues_found:
              type: integer

    ReviewReport:
      type: object
      properties:
        report_id:
          type: string
        project_id:
          type: string
        started_at:
          type: string
          format: date-time
        completed_at:
          type: string
          format: date-time
        total_issues:
          type: integer
        issues_by_severity:
          type: object
        issues:
          type: array
          items:
            $ref: '#/components/schemas/ReviewIssue'

    ReviewIssue:
      type: object
      properties:
        issue_id:
          type: string
        rule_id:
          type: string
        severity:
          type: string
          enum: [致命, 严重, 一般, 轻微, 提示]
        title:
          type: string
        description:
          type: string
        location:
          type: object
          properties:
            drawing_name:
              type: string
            floor:
              type: string
```

---

## 第七部分：部署与配置

### 7.1 系统配置文件

```yaml
# config/system.yaml

system:
  name: "AI智能审图系统"
  version: "6.0.0"
  debug: false
  log_level: INFO

paths:
  data_dir: "./data"
  cache_dir: "./cache"
  output_dir: "./output"
  rules_dir: "./config/rules"
  temp_dir: "/tmp/ai_review"

processing:
  # 并行处理配置
  max_workers: 4
  chunk_size: 100
  
  # 缓存配置
  enable_cache: true
  cache_ttl: 86400  # 24小时
  
  # 性能限制
  max_file_size_mb: 500
  max_entities_per_file: 100000
  timeout_seconds: 300

extraction:
  # DXF提取配置
  text_height_threshold: 0.5
  extract_dimensions: true
  extract_blocks: true
  extract_attributes: true
  
  # 图层映射
  layer_discipline_map:
    "建筑|ARCH|建": "建筑"
    "结构|STRUC|结": "结构"
    "电气|ELEC|电": "电气"
    "暖通|HVAC|暖": "暖通"
    "给排水|PLUMB|水": "给排水"

rules:
  # 规则引擎配置
  rules_file: "config/rules.json"
  auto_reload: false
  
  # 默认检查深度
  default_check_level: 2
  
  # 规则过滤
  filter_by_project_type: true
  filter_by_phase: true

output:
  # 输出格式
  formats:
    - json
    - excel
    - pdf
  
  # 报告配置
  include_evidence: true
  include_screenshots: false
  max_issues_per_report: 1000
  
  # 多角色输出
  generate_role_views: true
  roles:
    - designer
    - contractor
    - supervisor
    - owner

schedule:
  # 进度计划配置
  enable_schedule_generation: true
  standard_working_days_per_week: 5
  holidays: []
  
  # 工期估算
  use_standard_durations: true
  duration_buffer_percent: 10
```

### 7.2 Docker部署配置

```dockerfile
# Dockerfile

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libspatialindex-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建必要目录
RUN mkdir -p data cache output logs

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yaml

version: '3.8'

services:
  ai-review:
    build: .
    image: ai-review-system:v6.0
    container_name: ai-review
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./cache:/app/cache
      - ./output:/app/output
      - ./config:/app/config
    environment:
      - LOG_LEVEL=INFO
      - MAX_WORKERS=4
      - CACHE_TTL=86400
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 附录

### A. 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| DXF | Drawing Exchange Format | AutoCAD图纸交换格式 |
| 强条 | Mandatory Code | 强制性条文，必须遵守的规范条款 |
| 标高 | Elevation | 建筑物某点相对于基准面的高度 |
| 净距 | Clearance | 两个物体之间的最小距离 |
| 关键路径 | Critical Path | 决定项目最短工期的任务序列 |
| R-tree | R-tree | 空间索引数据结构 |

### B. 参考资料

1. 《建筑设计防火规范》GB50016-2022
2. 《建筑工程施工质量验收统一标准》GB50300-2013
3. ezdxf文档: https://ezdxf.readthedocs.io/
4. R-tree索引: https://rtree.readthedocs.io/

### C. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v5.1 | 2024-01 | 初始版本，基础合规检查 |
| v6.0 | 2026-05 | 实际实现：5步工作流+12引擎+3报告+61项测试 |

---

## 附录D: v6.0 实际实现对照

本规范为前瞻性设计文档。截至 **2026-05-19**，v6.0 实际实现情况如下：

### 已实现（与规范一致）

| 规范章节 | 实际实现 | 差异说明 |
|---------|---------|---------|
| 1.1 基础类型定义 | ✅ 各引擎中已使用TypedDict/Dataclass | 分散实现在各引擎中，未单独types.py |
| 2.1 JsonLoader | `engine/json_loader.py` 159行 | 功能一致 |
| 2.2 RuleChecker | `engine/rule_checker.py` 345行 | 支持91条规则 |
| 2.3 ElevationCalc | `engine/elevation_calc.py` 279行 | 功能一致 |
| 2.4 CollisionDetect | `engine/collision_detect.py` 323行 | 基础文本碰撞 |
| 2.5 MepCoordinator | `engine/mep_coordinator.py` 295行 | 功能一致 |
| 2.6 CrossDiscipline | `engine/cross_discipline.py` 589行 | 功能一致 |
| 2.7 EngineeringAnalyzer | `engine/engineering_analysis.py` 535行 | 功能一致 |
| 2.8 ExperienceMatcher | `engine/experience_matcher.py` 278行 | 功能一致 |

### 未实现（v6.1+规划）

| 规范内容 | 说明 | 规划 |
|---------|------|------|
| geometry/_analyzer.py (规范中模块) | 更名为 geometry_extractor + geometry_analyzer | ✅ 已实现 |
| analysis/ 目录 | 合并到 engine/ 目录 | 结构简化 |
| api/ 目录（Web接口） | 未实现，暂为CLI模式 | v6.1规划 |
| 三维重建模块（3.1-3.3） | 未实现 | v6.2+规划 |
| R-tree空间索引 | 未实现 | v6.2+规划 |
| Docker部署 | 未实现 | v6.1规划 |
| 数据库持久化 | 未实现，使用JSON文件 | 不影响功能 |

---

**文档结束**
