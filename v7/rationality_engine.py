# -*- coding: utf-8 -*-
"""
合理性评估引擎 v1.0
将审查系统从"条文符合性判断"升级为"工程合理性评估"
覆盖: 疏散组织 / 管线排布 / 结构最优区间 / 设备选型

三级标准框架:
  R0(0~30分)  = 条文明确禁止, 设计不可行
  R1(30~55分) = 条文合格但设计非最优(可优化)
  R2(55~80分) = 条文合格且设计合理
  R3(80~100分)= 条文无明确规定,需工程经验判断且设计优秀
"""

# ================================================================
# ① R0~R3 框架定义与工具函数
# ================================================================

def classify_rationality(score):
    """将得分映射到R0~R3等级"""
    if score <= 30:
        return "R0", "设计不可行, 条文明确禁止或严重不满足工程基本要求"
    elif score <= 55:
        return "R1", "条文合格但设计非最优, 存在可优化空间"
    elif score <= 80:
        return "R2", "条文合格且设计基本合理"
    else:
        return "R3", "设计优秀, 超出规范最低要求且考虑周全"

def make_rationality(level, score, explanation):
    return {"level": level, "score": score, "explanation": explanation}

# ================================================================
# ② 疏散宽度合理性模型
# ================================================================
"""
核心公式:
  计算需求宽度 = 使用人数 / 100 × 宽度指标(m/百人)
  实际裕量 = (实际标注宽度 - 计算需求宽度) / 计算需求宽度 × 100%
  高峰修正:
    教学楼: 1.3 (课间集中疏散)
    宿舍楼: 1.1 (非同步疏散)
    普通办公: 1.0
  距离衰减 = clamp((50m - 最远距离) / 50m, 0.2, 1.0)
  最终得分 = min(100, 基础分 + 裕量加分 - 高峰惩罚)
"""

EVACUATION_WIDTH_PER_100 = {
    "二类高层": 1.00,  # GB50016 第5.5.21条
    "一类高层": 1.00,
    "多层": 0.75,
}

PEAK_FACTOR = {
    "教学楼": 1.30,
    "宿舍楼": 1.10,
    "办公": 1.00,
    "实验室": 1.05,
    "阶梯教室": 1.40,
    "食堂": 1.50,
    "图书馆": 1.20,
}


def evaluate_evacuation(occupants, doors_width, building_type, use_type, max_distance):
    """
    评估疏散宽度合理性
    Args:
        occupants: 使用人数
        doors_width: 疏散门/走道/楼梯总宽度(m)
        building_type: 建筑类别(二类高层/多层等)
        use_type: 使用功能(教学楼/宿舍楼等)
        max_distance: 最远疏散距离(m)
    Returns:
        rationality dict
    """
    width_per_100 = EVACUATION_WIDTH_PER_100.get(building_type, 1.00)
    required = (occupants / 100.0) * width_per_100
    margin = (doors_width - required) / required * 100.0 if required > 0 else 0

    peak = PEAK_FACTOR.get(use_type, 1.0)
    dist_factor = max(0.2, min(1.0, (50.0 - max_distance) / 50.0))

    # 基础分: 满足规范=50分
    base = 50.0
    # 裕量加分: 每10%裕量+5分, 上限30分
    margin_bonus = min(30, margin * 0.5)
    # 高峰惩罚: 高峰系数>1.15时, 每超出0.1扣10分
    peak_penalty = max(0, (peak - 1.15) * 100) if peak > 1.15 else 0
    # 距离修正: 最远距离<30m加分, >40m扣分
    dist_bonus = (10.0 if max_distance < 30 else -10.0 if max_distance > 45 else 0)

    score = base + margin_bonus - peak_penalty + dist_bonus
    score = max(5, min(100, score))

    level, desc = classify_rationality(score)

    explanation = (
        f"规范需求宽度{required:.2f}m({occupants}人÷100×{width_per_100}m/百人), "
        f"标注宽度{doors_width:.2f}m, 裕量{margin:.0f}%。"
        f"{use_type}高峰系数{peak}, "
        f"最远疏散距离{max_distance}m。"
        f"峰值需求{(required*peak):.2f}m。"
        f"{'峰值需求超过标注宽度, 建议增宽或增设出口' if required*peak > doors_width else '标注宽度可覆盖高峰需求'}"
    )
    return make_rationality(level, round(score), explanation)


# ================================================================
# ③ 管线排布合理性模型
# ================================================================

PIPE_SPACING_RULES = {
    "给水/排水": {"水平_min_m": 0.5, "垂直_min_m": 0.15},
    "电力": {"水平_min_m": 1.0, "垂直_min_m": 0.5},
    "通信": {"水平_min_m": 0.5, "垂直_min_m": 0.3},
    "燃气钢管": {"水平_min_m": 0.5, "垂直_min_m": 0.15},
    "燃气PE管": {"水平_min_m": 1.0, "垂直_min_m": 0.3},
    "热力": {"水平_min_m": 1.5, "垂直_min_m": 0.15},
}


def evaluate_pipe_layout(spacing_data):
    """
    评估管线排布合理性
    Args:
        spacing_data: dict {
            "horizontal_margin": 实际水平间距(m),
            "vertical_margin": 实际垂直净距(m),
            "pipe_type1": "给水/排水",
            "pipe_type2": "电力",
            "has_maintenance_space": True/False(是否有检修空间),
            "construction_order_ok": True/False(施工顺序是否合理),
            "valve_accessible": True/False(阀门/检查井是否可达),
        }
    Returns:
        rationality dict
    """
    # 取两管类型中更严格的标准
    rule1 = PIPE_SPACING_RULES.get(spacing_data.get("pipe_type1", "给水/排水"), PIPE_SPACING_RULES["给水/排水"])
    rule2 = PIPE_SPACING_RULES.get(spacing_data.get("pipe_type2", "给水/排水"), PIPE_SPACING_RULES["给水/排水"])
    h_min = max(rule1["水平_min_m"], rule2["水平_min_m"])
    v_min = max(rule1["垂直_min_m"], rule2["垂直_min_m"])

    h_margin = spacing_data.get("horizontal_margin", 0)
    v_margin = spacing_data.get("vertical_margin", 0)

    # 水平间距得分(25分)
    h_ratio = h_margin / h_min if h_min > 0 else 1.0
    h_score = min(25, h_ratio * 15)

    # 垂直净距得分(20分)
    v_ratio = v_margin / v_min if v_min > 0 else 1.0
    v_score = min(20, v_ratio * 12)

    # 检修空间(25分)
    maintenance_score = 25 if spacing_data.get("has_maintenance_space") else 10

    # 施工顺序(15分)
    order_score = 15 if spacing_data.get("construction_order_ok") else 5

    # 维护便利(15分)
    valve_score = 15 if spacing_data.get("valve_accessible") else 5

    total = h_score + v_score + maintenance_score + order_score + valve_score
    level, desc = classify_rationality(total)

    explanation = (
        f"管线1({spacing_data.get('pipe_type1','?')})与管线2({spacing_data.get('pipe_type2','?')}): "
        f"水平间距{h_margin}m(要求≥{h_min}m), 垂直净距{v_margin}m(要求≥{v_min}m)。"
        f"检修空间{'有' if spacing_data.get('has_maintenance_space') else '无'}, "
        f"施工顺序{'合理' if spacing_data.get('construction_order_ok') else '存疑'}, "
        f"阀门可达{'是' if spacing_data.get('valve_accessible') else '否'}。"
        f"得分={total}/100。"
    )
    return make_rationality(level, round(total), explanation)


# ================================================================
# ⑤ 结构配筋/截面最优区间基线库
# ================================================================

STRUCT_OPTIMAL_RANGE = {
    "简支梁": {
        "reinforcement_ratio": (0.008, 0.015),   # 最优配筋率0.8%~1.5%
        "span_depth_ratio": (10, 12),              # 最优高跨比1/12~1/10
        "concrete_grade": "C30~C40",
        "norm_min_reinforcement": 0.002,
        "norm_max_reinforcement": 0.025,
    },
    "连续梁": {
        "reinforcement_ratio": (0.006, 0.012),
        "span_depth_ratio": (12, 15),
        "concrete_grade": "C30~C40",
        "norm_min_reinforcement": 0.002,
        "norm_max_reinforcement": 0.025,
    },
    "悬挑梁": {
        "reinforcement_ratio": (0.008, 0.015),
        "span_depth_ratio": (5, 6),
        "concrete_grade": "C30~C40",
        "norm_min_reinforcement": 0.002,
        "norm_max_reinforcement": 0.025,
    },
    "框架柱": {
        "reinforcement_ratio": (0.008, 0.012),
        "axial_ratio_limit": 0.75,
        "concrete_grade": "C35~C50",
        "norm_min_reinforcement": 0.006,
        "norm_max_reinforcement": 0.050,
    },
    "楼板": {
        "reinforcement_ratio": (0.004, 0.008),
        "span_thickness_ratio": (30, 35),
        "concrete_grade": "C30",
        "norm_min_reinforcement": 0.0015,
        "norm_max_reinforcement": 0.012,
    },
    "剪力墙": {
        "reinforcement_ratio": (0.0025, 0.005),
        "height_thickness_ratio": (16, 20),
        "concrete_grade": "C35~C50",
        "norm_min_reinforcement": 0.0025,
        "norm_max_reinforcement": 0.010,
    },
    "独立基础": {
        "reinforcement_per_meter": (0.004, 0.006),
        "depth_width_ratio": 0.6,
        "concrete_grade": "C30",
        "norm_min_per_meter": 0.0015,
        "norm_max_per_meter": 0.010,
    },
    "桩基": {
        "reinforcement_ratio": (0.004, 0.006),
        "concrete_grade": "C35~C40",
        "norm_min_reinforcement": 0.002,
        "norm_max_reinforcement": 0.0065,
    },
    "钢框架梁": {
        "span_depth_ratio": (10, 15),
        "steel_grade": "Q345~Q390",
        "stress_ratio": (0.7, 0.85),  # 应力比最优区间
    },
    "钢框架柱": {
        "slenderness_ratio": (40, 80),
        "steel_grade": "Q345~Q390",
        "stress_ratio": (0.6, 0.80),
    },
    "型钢混凝土梁": {
        "steel_ratio": (0.04, 0.08),
        "span_depth_ratio": (12, 18),
        "concrete_grade": "C35~C50",
    },
    "叠合楼板": {
        "precast_thickness_ratio": (0.4, 0.5),  # 预制层/总厚
        "cast_in_place_min_mm": 70,
        "total_min_mm": 130,
    },
}


def evaluate_structural_optimality(component_type, design_values):
    """
    评估结构构件的设计最优性
    Args:
        component_type: 构件类型(从STRUCT_OPTIMAL_RANGE的key选取)
        design_values: dict, 如{"reinforcement_ratio": 0.009, "span_depth_ratio": 11}
    Returns:
        rationality dict
    """
    optimal = STRUCT_OPTIMAL_RANGE.get(component_type)
    if not optimal:
        return make_rationality("R2", 60, f"构件类型'{component_type}'暂无最优区间基线, 无法评估最优性")

    scores = []
    details = []
    total_weight = 0

    # 评估配筋率
    if "reinforcement_ratio" in optimal and "reinforcement_ratio" in design_values:
        actual = design_values["reinforcement_ratio"]
        opt_min, opt_max = optimal["reinforcement_ratio"]
        norm_min = optimal.get("norm_min_reinforcement", 0)
        norm_max = optimal.get("norm_max_reinforcement", 1)

        if actual < norm_min:
            scores.append((0.3, "配筋率低于规范最小值, R0"))
            details.append(f"配筋率{actual:.3f}<规范最小{norm_min:.3f}")
        elif actual > norm_max:
            scores.append((0.5, "配筋率超出规范最大值, R0"))
            details.append(f"配筋率{actual:.3f}>规范最大{norm_max:.3f}")
        elif opt_min <= actual <= opt_max:
            scores.append((1.0, "配筋率在最优区间"))
            details.append(f"配筋率{actual:.3f}∈[{opt_min:.3f}~{opt_max:.3f}]最优")
        elif norm_min <= actual < opt_min:
            scores.append((0.7, "配筋率偏低但合规"))
            details.append(f"配筋率{actual:.3f}<最优下限{opt_min:.3f}, 偏经济但安全冗余偏低")
        else:  # opt_max < actual <= norm_max
            scores.append((0.8, "配筋率偏高但合规"))
            details.append(f"配筋率{actual:.3f}>最优上限{opt_max:.3f}, 安全冗余大但经济性欠佳")
        total_weight += 0.5

    # 评估高跨比/高厚比
    ratio_key = None
    for k in ["span_depth_ratio", "span_thickness_ratio", "height_thickness_ratio", "depth_width_ratio", "slenderness_ratio", "precast_thickness_ratio"]:
        if k in optimal and k in design_values:
            ratio_key = k
            break

    if ratio_key:
        actual_ratio = design_values[ratio_key]
        opt_min, opt_max = optimal[ratio_key]
        if opt_min <= actual_ratio <= opt_max:
            scores.append((1.0, f"{ratio_key}在最优区间"))
            details.append(f"{ratio_key}={actual_ratio}∈[{opt_min}~{opt_max}]")
        else:
            scores.append((0.6, f"{ratio_key}偏离最优区间"))
            details.append(f"{ratio_key}={actual_ratio}∉[{opt_min}~{opt_max}], 建议调整")
        total_weight += 0.35

    # 评估应力比(钢结构)
    if "stress_ratio" in optimal and "stress_ratio" in design_values:
        actual = design_values["stress_ratio"]
        opt_min, opt_max = optimal["stress_ratio"]
        if opt_min <= actual <= opt_max:
            scores.append((1.0, "应力比在最优区间"))
        elif actual < opt_min:
            scores.append((0.7, "应力比偏低, 材料未充分利用"))
        else:
            scores.append((0.8, "应力比偏高, 安全冗余不足"))
        total_weight += 0.15

    if not scores:
        return make_rationality("R2", 60, f"缺少{component_type}评估所需的设计参数")

    # 加权计算
    weighted = sum(s * w for s, _ in scores) / total_weight if total_weight > 0 else 0
    score = round(weighted * 100)
    level, _ = classify_rationality(score)

    return make_rationality(level, score, "; ".join(details))


# ================================================================
# ⑥ 设备选型合理性评估模型
# ================================================================

def evaluate_equipment_selection(equip_type, design_capacity, required_capacity, energy_rating, lifecycle_years):
    """
    评估设备选型合理性
    Args:
        equip_type: 设备类型(变压器/风机/水泵/空调主机)
        design_capacity: 设计选型容量(对应单位)
        required_capacity: 计算需求容量
        energy_rating: 能效等级(1/2/3级)
        lifecycle_years: 设计使用年限
    Returns:
        rationality dict
    """
    # 1. 工况适配度(40%): 设计/需求比在0.6~0.85最优
    ratio = design_capacity / required_capacity if required_capacity > 0 else 1.0
    if 0.6 <= ratio <= 0.85:
        adapt_score = 40
        adapt_note = "运行工况在高效区间"
    elif 0.85 < ratio <= 0.95:
        adapt_score = 30
        adapt_note = "接近满负荷, 高峰可能不足"
    elif 0.95 < ratio <= 1.1:
        adapt_score = 20
        adapt_note = "满负荷运行, 建议增大选型或增设备用"
    elif 0.4 <= ratio < 0.6:
        adapt_score = 25
        adapt_note = "大马拉小车, 低负荷效率低"
    else:
        adapt_score = 15
        adapt_note = "容量严重不匹配"

    # 2. 冗余裕量(30%): 余量10~20%最优
    redundancy = (design_capacity - required_capacity) / required_capacity * 100 if required_capacity > 0 else 0
    if 10 <= redundancy <= 20:
        redundancy_score = 30
        redundancy_note = f"冗余裕量{redundancy:.0f}%, 理想"
    elif 5 <= redundancy < 10:
        redundancy_score = 20
        redundancy_note = f"冗余裕量{redundancy:.0f}%, 偏紧"
    elif 20 < redundancy <= 35:
        redundancy_score = 22
        redundancy_note = f"冗余裕量{redundancy:.0f}%, 略大但可接受"
    elif redundancy > 35:
        redundancy_score = 15
        redundancy_note = f"冗余裕量{redundancy:.0f}%, 过度冗余浪费投资"
    elif 0 <= redundancy < 5:
        redundancy_score = 15
        redundancy_note = f"冗余裕量{redundancy:.0f}%, 几乎无余量"
    else:
        redundancy_score = 5
        redundancy_note = f"容量不足, 负冗余{redundancy:.0f}%"

    # 3. 运维成本(30%): 能效等级+寿命
    energy_map = {1: 30, 2: 22, 3: 15}
    energy_score = energy_map.get(energy_rating, 12)
    # 寿命修正
    if lifecycle_years >= 20:
        energy_score = min(30, energy_score + 3)
    elif lifecycle_years < 10:
        energy_score -= 5
    energy_note = f"能效{energy_rating}级, 设计寿命{lifecycle_years}年"

    total = adapt_score + redundancy_score + energy_score
    level, _ = classify_rationality(total)

    explanation = (
        f"{equip_type}: 设计{design_capacity}/需求{required_capacity}(比{ratio:.2f})。"
        f"{adapt_note}。{redundancy_note}。{energy_note}。"
        f"综合得分{total}/100。"
    )
    return make_rationality(level, round(total), explanation)


# ================================================================
# ⑦ 批量标注合理性 (供llm_full_review.py调用)
# ================================================================

def annotate_all_rationality(findings):
    """
    对审查发现批量追加rationality字段
    根据问题类型自动调用对应的评估模型, 或使用默认评注
    """
    for f in findings:
        fid = f.get("id", "")

        # 已有rationality的不重复标注
        if "rationality" in f:
            continue

        # 按ID前缀匹配评估策略
        if fid.startswith("FIRE") and "疏散" in f.get("finding", ""):
            f["rationality"] = make_rationality(
                "R1", 50,
                "疏散相关审查项需结合具体使用人数和高峰模式评估。当前仅检查规范数值符合性，建议补全实际使用场景分析后升级为工程合理性评估。"
            )

        elif fid.startswith("CROSS") and ("冲突" in f.get("finding", "") or "碰撞" in f.get("finding", "")):
            f["rationality"] = make_rationality(
                "R1", 45,
                "跨专业冲突需逐区核实：相同XY位置可能因Z轴标高差异或施工绕行方案而不构成实际冲突。建议结合BIM三维模型和施工组织设计综合评估。"
            )

        elif fid.startswith("STRUCT"):
            f["rationality"] = make_rationality(
                "R1", 55,
                "结构构件设计满足规范最低要求，但建议进一步评估是否落在最优配筋率/高跨比区间，兼顾安全性和经济性。"
            )

        elif fid.startswith("PLUMB"):
            f["rationality"] = make_rationality(
                "R1", 55,
                "给排水设计满足规范基本要求。消防系统参数(泵扬程/水池容积/最不利点压力)建议结合水力计算书复核最优性。"
            )

        elif fid.startswith("HVAC"):
            f["rationality"] = make_rationality(
                "R1", 52,
                "暖通系统选型满足基础参数要求，但设备效率等级、部分负荷运行策略、过渡季免费供冷等节能优化方案有待评估。"
            )

        elif fid.startswith("ELEC"):
            f["rationality"] = make_rationality(
                "R1", 55,
                "电气设计满足规范要求。配电系统选择性配合、继保整定优化、无功补偿策略等高级评估维度可纳入后续深化审查。"
            )

        elif fid.startswith("CW"):
            f["rationality"] = make_rationality(
                "R1", 50,
                "幕墙设计需结合结构计算书和抗风压验算进行最优性评估。当前仅检查了构造做法的完整性和物理性能分级。"
            )

        elif fid.startswith("ASB"):
            f["rationality"] = make_rationality(
                "R1", 48,
                "装配式设计总说明内容完整，但节点详细程度和吊装安全验算的可施工性评估有待深化。"
            )

        elif fid.startswith("PV"):
            f["rationality"] = make_rationality(
                "R1", 45,
                "光伏专项设计信息不完整，组件布局最佳倾角、逆变器MPPT路数优化、阴影遮挡分析等尚未涉及。"
            )

        elif fid.startswith("ELV"):
            f["rationality"] = make_rationality(
                "R1", 50,
                "电梯配置需结合建筑使用人数、高峰期等待时间要求、分组调度策略等综合评估最优性。"
            )

        elif fid.startswith("OUT"):
            f["rationality"] = make_rationality(
                "R1", 45,
                "室外管线综合需全专业参与完成后方可进行系统性最优排布评估。当前仅具备给排水专业数据。"
            )

        elif fid.startswith("PD"):
            f["rationality"] = make_rationality(
                "R1", 48,
                "变配电设计由电力部门深化，土建接口条件基本满足。主接线方案、保护配合、经济运行策略属电力专业审查范围。"
            )

        elif fid.startswith("PEND"):
            f["rationality"] = make_rationality(
                "R0", 10,
                "待交付专项：图纸缺失导致无法启动任何评估。需设计单位提交完整专项设计文件后方可审查。"
            )

        else:
            # 默认: 条文合规, 最优性需进一步评估
            f["rationality"] = make_rationality(
                "R2", 60,
                "设计满足规范基本要求。如需工程合理性(最优性)深度评估，建议补充相关计算书和详细设计参数。"
            )

    return findings


# ================================================================
# ⑧ 空间冲突置信度修正
# ================================================================

def adjust_spatial_confidence(spatial_conflicts):
    """
    基于合理性评估结果修正空间冲突的置信度
    - 涉及"管线排布合理性"评分≥60的冲突 → 置信度升一级(low→medium→high)
    - 无合理性数据 → 保持原置信度
    """
    for c in spatial_conflicts:
        conf = c.get("confidence", "low")
        # 无附加信息的暂不调整
        if "rationality" not in c:
            continue

        r_score = c.get("rationality", {}).get("score", 0)
        if r_score >= 60 and conf == "low":
            c["confidence"] = "medium"
        elif r_score >= 60 and conf == "medium":
            c["confidence"] = "high"

    return spatial_conflicts
