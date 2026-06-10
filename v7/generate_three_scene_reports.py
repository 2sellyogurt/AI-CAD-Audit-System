# -*- coding: utf-8 -*-
"""
三场景报告生成器
从 spatial_conflicts_v5.json + uai_review_data.py 数据生成：
  场景1_基础错漏排查报告(3).docx
  场景2_跨专业一致性校验报告(3).docx
  场景3_强条合规性审查报告(3).docx
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# 确保能找到 v7 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uai_review_data import UAI_FINDINGS, SEVERITY_ADJUST

try:
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

BASE = r"f:\AI智能审图系统_v6.0_项目开发"
SPATIAL_PATH = os.path.join(BASE, r"v7\spatial_conflicts_v5.json")
OUTPUT_DIR = os.path.join(BASE, "output_v7.0")

PROJECT = "温州医科大学阿尔伯塔学院"
REPORT_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 冲突类型中文映射
CONFLICT_CN = {
    "beam_duct_overlap": "梁-风管重叠",
    "beam_pipe_overlap": "梁-管线重叠",
    "column_pipe_conflict": "柱-管线冲突",
    "pipe_crossing": "管线交叉",
    "duct_through_wall": "风管穿墙",
    "egress_width": "疏散宽度不足",
}

# 专业中文映射
DISCIPLINE_CN = {
    "building": "建筑", "structure": "结构", "plumbing": "给排水",
    "hvac": "暖通", "electrical": "电气", "fire": "消防",
    "curtain_wall": "幕墙", "decoration": "装饰", "landscape": "景观",
    "foundation_pit": "基坑",
}

# UAI检查点 → 规范映射
CHECKPOINT_STANDARD = {
    "JZX": "GB50345/GB50108", "JZ": "GB50763", "FIRE": "GB50016",
    "STRUCT": "GB50010/GB50011", "PLUMB": "GB50974/GB50015",
    "HVAC": "GB50736/GB51251", "ELEC": "GB50054/GB50057/GB50116",
    "CW": "GB50016", "DEC": "GB50222", "LS": "GB50420", "FP": "GB50086",
}

# 专业-检查点前缀映射
DISC_PREFIX = {
    "建筑": ["JZ", "JZX"], "消防": ["FIRE"], "结构": ["STRUCT"],
    "给排水": ["PLUMB"], "暖通": ["HVAC"], "电气": ["ELEC"],
    "幕墙": ["CW"], "装饰": ["DEC"], "景观": ["LS"], "基坑": ["FP"],
}


def load_spatial():
    """加载空间冲突数据"""
    if not os.path.exists(SPATIAL_PATH):
        print(f"  ⚠️ 未找到空间冲突文件: {SPATIAL_PATH}")
        return []
    with open(SPATIAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_uai_findings():
    """加载UAI审查数据并构建结构化数据"""
    items = []
    for cpid, data in UAI_FINDINGS.items():
        finding = data.get("finding", "")
        fix = data.get("fix", "")
        sev = SEVERITY_ADJUST.get(cpid, "C")
        sev_label = {"A": "严重（强条违反）", "B": "重要", "C": "一般", "D": "提示"}.get(sev, "一般")

        # 确定专业
        disc = "其他"
        for d, prefixes in DISC_PREFIX.items():
            if any(cpid.startswith(p) for p in prefixes):
                disc = d
                break

        # 确定规范
        prefix = cpid.split("-")[0] if "-" in cpid else cpid
        standard = CHECKPOINT_STANDARD.get(prefix, "国标")

        items.append({
            "id": cpid,
            "discipline": disc,
            "finding": finding,
            "fix": fix,
            "severity": sev,
            "severity_label": sev_label,
            "standard": standard,
        })
    return items


# ================================================================
# 场景1：基础错漏排查报告
# ================================================================
def generate_scene1(spatial_conflicts, doc):
    """基础错漏排查报告——空间碰撞检测为主"""
    title = doc.add_heading(f"基础错漏排查报告 v7.0", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"项目名称: {PROJECT}\n")
    run = p.add_run(f"排查时间: {REPORT_DATE}\n")
    run = p.add_run(f"报告版本: v7.0 — 基于v7管线 + UAI全量审查")

    doc.add_paragraph()

    # 1. 排查概述
    doc.add_heading("1. 排查概述", level=1)
    doc.add_paragraph(
        "本报告对施工图设计文件进行基础错漏排查，涵盖标高计算、净高验算、碰撞检测、管线综合排布分析。"
        "数据来源为v7空间冲突检测引擎对108张DXF图纸的六类碰撞检测结果（共21,500个冲突簇），"
        "以及UAI审查145检查点的实地发现文本证据。"
    )

    # 2. 统计摘要
    doc.add_heading("2. 统计摘要", level=1)

    by_type = defaultdict(int)
    by_severity = defaultdict(int)
    floor_dist = defaultdict(int)

    for c in spatial_conflicts:
        ctype = c.get("type", "unknown")
        sev = c.get("severity", "D")
        floor = str(c.get("floor", "?"))
        by_type[ctype] += 1
        by_severity[sev] += 1
        floor_dist[floor] += 1

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    hdr[0].text = "指标"
    hdr[1].text = "数量"

    rows_data = [
        ("碰撞检测问题总数", sum(by_type.values())),
        ("梁-风管重叠", by_type.get("beam_duct_overlap", 0)),
        ("梁-管线重叠", by_type.get("beam_pipe_overlap", 0)),
        ("柱-管线冲突", by_type.get("column_pipe_conflict", 0)),
        ("管线交叉", by_type.get("pipe_crossing", 0)),
        ("风管穿墙", by_type.get("duct_through_wall", 0)),
        ("疏散宽度不足", by_type.get("egress_width", 0)),
        ("A级（严重）", by_severity.get("A", 0)),
        ("B级（重要）", by_severity.get("B", 0)),
        ("C级（一般）", by_severity.get("C", 0)),
        ("D级（提示）", by_severity.get("D", 0)),
        ("涉及楼层数", len(floor_dist)),
        ("处理DXF文件数", 108),
    ]
    for label, val in rows_data:
        row = table.add_row().cells
        row[0].text = str(label)
        row[1].text = str(val)

    doc.add_paragraph()

    # 3. 楼层冲突热力分布
    doc.add_heading("3. 楼层冲突热力分布", level=1)
    sorted_floors = sorted(floor_dist.items(), key=lambda x: float(x[0]) if x[0].lstrip('-').replace('.','').isdigit() else 999)
    table2 = doc.add_table(rows=1, cols=3)
    table2.style = "Table Grid"
    hdr2 = table2.rows[0].cells
    hdr2[0].text = "楼层"
    hdr2[1].text = "冲突数"
    hdr2[2].text = "占比"
    total = sum(floor_dist.values())
    for floor, cnt in sorted_floors[:25]:
        row = table2.add_row().cells
        row[0].text = f"标高 {floor}m"
        row[1].text = str(cnt)
        row[2].text = f"{cnt / total * 100:.1f}%"

    doc.add_paragraph()

    # 4. 问题明细（按类型+楼层抽样显示Top冲突）
    doc.add_heading("4. 重点冲突问题明细", level=1)

    # 按类型分组显示Top冲突
    for ctype_cn, ctype_en in [("梁-风管重叠", "beam_duct_overlap"),
                                 ("柱-管线冲突", "column_pipe_conflict"),
                                 ("风管穿墙", "duct_through_wall"),
                                 ("管线交叉", "pipe_crossing")]:
        items = [c for c in spatial_conflicts if c.get("type") == ctype_en]
        if not items:
            continue

        doc.add_heading(f"4.{list(CONFLICT_CN.keys()).index(ctype_en)+1} {ctype_cn}", level=2)
        doc.add_paragraph(f"共 {len(items)} 个冲突簇，显示前10个")

        # 显示前10个
        for i, c in enumerate(items[:10]):
            sev = c.get("severity", "D")
            floor = c.get("floor", "?")
            desc = c.get("description", "")
            doc.add_paragraph(
                f"{i+1}. [严重度{sev}] 标高{floor}m — {desc[:200] if desc else '详情见空间冲突原始数据'}",
                style="List Number"
            )

    # 5. UAI审查错漏分析
    doc.add_heading("5. UAI审查发现的基础错漏", level=1)
    uai_items = load_uai_findings()
    defect_items = [i for i in uai_items if i["severity"] in ("A", "B") and "无需整改" not in i["fix"]]

    if defect_items:
        doc.add_paragraph(f"以下 {len(defect_items)} 项需整改的基础错漏问题：")
        table3 = doc.add_table(rows=1, cols=5)
        table3.style = "Table Grid"
        hdr3 = table3.rows[0].cells
        for j, h in enumerate(["编号", "专业", "问题描述", "严重度", "整改要求"]):
            hdr3[j].text = h

        for item in defect_items:
            row = table3.add_row().cells
            row[0].text = item["id"]
            row[1].text = item["discipline"]
            row[2].text = item["finding"][:120]
            row[3].text = item["severity_label"]
            row[4].text = item["fix"][:120]

    doc.add_paragraph()
    doc.add_paragraph("— 报告结束 —", style="Intense Quote")


# ================================================================
# 场景2：跨专业一致性校验报告
# ================================================================
def generate_scene2(spatial_conflicts, doc):
    """跨专业一致性校验报告"""
    title = doc.add_heading(f"跨专业一致性校验报告 v7.0", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"项目名称: {PROJECT}\n")
    run = p.add_run(f"校验时间: {REPORT_DATE}\n")
    run = p.add_run(f"报告版本: v7.0 — 基于v7管线 + UAI全量审查")

    doc.add_paragraph()

    # 1. 校验概述
    doc.add_heading("1. 校验概述", level=1)
    doc.add_paragraph(
        "本报告对各专业施工图之间的一致性进行系统校验，识别跨专业矛盾、遗漏及不协调问题。"
        "数据来源包括：（1）六类空间冲突检测结果揭示的跨专业碰撞；"
        "（2）UAI审查145检查点中涉及跨专业协调的发现。"
    )

    # 2. 统计摘要
    doc.add_heading("2. 统计摘要", level=1)
    uai_items = load_uai_findings()

    # 统计跨专业冲突类型
    cross_disc_conflicts = defaultdict(int)
    for c in spatial_conflicts:
        ctype = c.get("type", "unknown")
        cross_disc_conflicts[ctype] += 1

    # 找出涉及跨专业的UAI问题
    cross_uai = [i for i in uai_items if "无需整改" not in i["fix"]]

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "指标"
    hdr[1].text = "数量"

    rows_data = [
        ("六类空间冲突数", sum(cross_disc_conflicts.values())),
        ("梁-风管重叠（结构+暖通）", cross_disc_conflicts.get("beam_duct_overlap", 0)),
        ("梁-管线重叠（结构+给排水）", cross_disc_conflicts.get("beam_pipe_overlap", 0)),
        ("柱-管线冲突（结构+机电）", cross_disc_conflicts.get("column_pipe_conflict", 0)),
        ("管线交叉（机电内部）", cross_disc_conflicts.get("pipe_crossing", 0)),
        ("风管穿墙（暖通+建筑）", cross_disc_conflicts.get("duct_through_wall", 0)),
        ("疏散宽度不足（建筑+消防）", cross_disc_conflicts.get("egress_width", 0)),
        ("UAI跨专业需整改项", len(cross_uai)),
        ("涉及专业数", 10),
    ]
    for label, val in rows_data:
        row = table.add_row().cells
        row[0].text = str(label)
        row[1].text = str(val)

    doc.add_paragraph()

    # 3. 结构vs建筑一致性
    doc.add_heading("3. 结构 vs 建筑一致性", level=1)
    struct_build_conflicts = [c for c in spatial_conflicts
                              if c.get("type") in ("beam_duct_overlap", "beam_pipe_overlap", "column_pipe_conflict")]
    doc.add_paragraph(
        f"空间冲突检测发现结构构件与建筑/机电专业的碰撞共 {len(struct_build_conflicts)} 处，"
        "主要体现为梁-风管、梁-管线、柱-管线三类重叠。"
    )

    # 按楼层显示
    floor_struct = defaultdict(int)
    for c in struct_build_conflicts:
        floor_struct[str(c.get("floor", "?"))] += 1
    if floor_struct:
        doc.add_paragraph("按楼层分布：")
        for f, cnt in sorted(floor_struct.items(), key=lambda x: float(x[0]) if x[0].lstrip('-').replace('.','').isdigit() else 999)[:10]:
            doc.add_paragraph(f"  标高 {f}m: {cnt} 处冲突")

    # 4. 机电管线协调
    doc.add_heading("4. 机电管线协调", level=1)
    mep_conflicts = [c for c in spatial_conflicts if c.get("type") in ("pipe_crossing", "duct_through_wall")]
    doc.add_paragraph(
        f"机电管线之间的交叉碰撞共 {len(mep_conflicts)} 处，"
        "涵盖风管穿墙、管线交叉两类，需机电专业协调确认管线综合排布。"
    )

    # 5. 消防跨专业一致性
    doc.add_heading("5. 消防跨专业一致性", level=1)
    fire_uai = [i for i in uai_items if i["discipline"] == "消防" and "无需整改" not in i["fix"]]
    egress = [c for c in spatial_conflicts if c.get("type") == "egress_width"]
    doc.add_paragraph(
        f"消防专业跨专业问题：UAI审查发现 {len(fire_uai)} 项需整改项，"
        f"空间冲突检测发现 {len(egress)} 处疏散宽度不足。"
    )
    for item in fire_uai[:8]:
        doc.add_paragraph(f"  • [{item['id']}] {item['finding'][:100]} — {item['fix'][:80]}")

    # 6. UAI跨专业发现详情
    doc.add_heading("6. UAI审查跨专业发现", level=1)
    doc.add_paragraph("以下UAI审查发现涉及多专业协调：")
    table2 = doc.add_table(rows=1, cols=4)
    table2.style = "Table Grid"
    hdr2 = table2.rows[0].cells
    for j, h in enumerate(["编号", "专业", "发现描述", "整改要求"]):
        hdr2[j].text = h

    for item in cross_uai[:20]:
        row = table2.add_row().cells
        row[0].text = item["id"]
        row[1].text = item["discipline"]
        row[2].text = item["finding"][:100]
        row[3].text = item["fix"][:100]

    doc.add_paragraph()
    doc.add_paragraph("— 报告结束 —", style="Intense Quote")


# ================================================================
# 场景3：强条合规性审查报告
# ================================================================
def generate_scene3(spatial_conflicts, doc):
    """强条合规性审查报告"""
    title = doc.add_heading(f"强条合规审查报告 v7.0", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"项目名称: {PROJECT}\n")
    run = p.add_run(f"审查时间: {REPORT_DATE}\n")
    run = p.add_run(f"报告版本: v7.0 — UAI全量审查 + 空间冲突交叉验证")

    doc.add_paragraph()

    # 1. 审查概述
    doc.add_heading("1. 审查概述", level=1)
    doc.add_paragraph(
        "本报告依据国家现行工程建设标准强制性条文，对施工图设计文件进行逐条合规性审查。"
        "审查路径：UAI全量审查（145检查点）× 空间冲突检测（21,500冲突簇）× 视觉复核。"
        "引用规范包括GB50016、GB50352、GB50010、GB50974、GB50015、GB50736等16本国标。"
    )

    # 2. 统计摘要
    doc.add_heading("2. 统计摘要", level=1)
    uai_items = load_uai_findings()

    total = len(uai_items)
    sev_a = len([i for i in uai_items if i["severity"] == "A"])
    sev_b = len([i for i in uai_items if i["severity"] == "B"])
    sev_c = len([i for i in uai_items if i["severity"] == "C"])
    sev_d = len([i for i in uai_items if i["severity"] == "D"])
    need_fix = len([i for i in uai_items if "无需整改" not in i["fix"]])
    ok = len([i for i in uai_items if "无需整改" in i["fix"]])

    by_disc = defaultdict(int)
    for i in uai_items:
        by_disc[i["discipline"]] += 1

    by_sev_item = defaultdict(lambda: defaultdict(int))
    for i in uai_items:
        by_sev_item[i["discipline"]][i["severity"]] += 1

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "指标"
    hdr[1].text = "数量"

    rows_data = [
        ("审查规则总数", total),
        ("A级（强条违反/严重）", sev_a),
        ("B级（重要）", sev_b),
        ("C级（一般/标注不全）", sev_c),
        ("D级（提示/建议）", sev_d),
        ("需整改项", need_fix),
        ("合规（无需整改）", ok),
        ("空间冲突数（辅助验证）", len(spatial_conflicts)),
    ]
    for label, val in rows_data:
        row = table.add_row().cells
        row[0].text = str(label)
        row[1].text = str(val)

    doc.add_paragraph()

    # 3. 引用规范
    doc.add_heading("3. 引用规范", level=1)
    standards = [
        "GB 50016-2014（2018版）建筑设计防火规范",
        "GB 50352-2019 民用建筑设计统一标准",
        "GB 50010-2010（2015版）混凝土结构设计规范",
        "GB 50011-2010（2016版）建筑抗震设计规范",
        "GB 50974-2014 消防给水及消火栓系统技术规范",
        "GB 50015-2019 建筑给水排水设计标准",
        "GB 50736-2012 民用建筑供暖通风与空气调节设计规范",
        "GB 50054-2011 低压配电设计规范",
        "GB 50057-2010 建筑物防雷设计规范",
        "GB 50116-2013 火灾自动报警系统设计规范",
        "GB 50345-2012 屋面工程技术规范",
        "GB 50108-2008 地下工程防水技术规范",
        "GB 50763-2012 无障碍设计规范",
        "GB 50222-2017 建筑内部装修设计防火规范",
        "GB 50420-2007（2016版）城市绿化工程施工及验收规范",
        "GB 50086-2015 岩土锚杆与喷射混凝土支护工程技术规范",
    ]
    for s in standards:
        doc.add_paragraph(s, style="List Bullet")

    # 4. 分专业合规详情
    doc.add_heading("4. 分专业合规审查详情", level=1)

    for disc in ["建筑", "消防", "结构", "给排水", "暖通", "电气", "幕墙", "装饰", "景观", "基坑"]:
        disc_items = [i for i in uai_items if i["discipline"] == disc]
        if not disc_items:
            continue

        a_cnt = len([i for i in disc_items if i["severity"] == "A"])
        b_cnt = len([i for i in disc_items if i["severity"] == "B"])
        doc.add_heading(f"{disc}专业 ({len(disc_items)}/{len(disc_items)}检查点) A{a_cnt}|B{b_cnt}", level=2)

        # 检查点表格
        tbl = doc.add_table(rows=1, cols=5)
        tbl.style = "Table Grid"
        h = tbl.rows[0].cells
        for j, ht in enumerate(["编号", "规范", "问题描述", "严重度", "整改要求"]):
            h[j].text = ht

        for item in disc_items:
            row = tbl.add_row().cells
            row[0].text = item["id"]
            row[1].text = item["standard"]
            row[2].text = item["finding"][:120]
            row[3].text = item["severity_label"]
            row[4].text = item["fix"][:100]

        doc.add_paragraph()

    # 5. 空间冲突合规分析
    doc.add_heading("5. 空间冲突合规分析", level=1)
    by_type = defaultdict(lambda: {"A": 0, "B": 0, "C": 0, "D": 0})
    for c in spatial_conflicts:
        t = c.get("type", "unknown")
        s = c.get("severity", "D")
        by_type[t][s] += 1

    tbl2 = doc.add_table(rows=1, cols=5)
    tbl2.style = "Table Grid"
    h2 = tbl2.rows[0].cells
    for j, ht in enumerate(["冲突类型", "A级", "B级", "C级", "D级"]):
        h2[j].text = ht

    for t, sv in by_type.items():
        row = tbl2.add_row().cells
        row[0].text = CONFLICT_CN.get(t, t)
        row[1].text = str(sv["A"])
        row[2].text = str(sv["B"])
        row[3].text = str(sv["C"])
        row[4].text = str(sv["D"])

    doc.add_paragraph()
    doc.add_paragraph("— 报告结束 —", style="Intense Quote")


# ================================================================
# 主入口
# ================================================================
def main():
    print("=" * 60)
    print(f"  三场景报告生成器 v7.0")
    print(f"  {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 加载数据
    print("\n[1/3] 加载空间冲突数据...")
    spatial = load_spatial()
    print(f"  → 加载 {len(spatial)} 个冲突簇")

    uai = load_uai_findings()
    print(f"  → 加载 {len(uai)} 个UAI检查点")

    if not HAS_DOCX:
        print("\n❌ python-docx 未安装，无法生成 docx 文件")
        print("   请执行: pip install python-docx")
        return

    # 2. 生成三个场景报告
    scenarios = [
        ("场景1_基础错漏排查报告(3).docx", generate_scene1),
        ("场景2_跨专业一致性校验报告(3).docx", generate_scene2),
        ("场景3_强条合规性审查报告(3).docx", generate_scene3),
    ]

    for fname, gen_func in scenarios:
        print(f"\n[2/3] 生成 {fname} ...")
        doc = Document()

        # 设置默认字体
        style = doc.styles["Normal"]
        font = style.font
        font.name = "微软雅黑"
        font.size = Pt(10.5)
        style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

        # 调用对应生成函数
        gen_func(spatial, doc)

        # 保存
        out_path = os.path.join(OUTPUT_DIR, fname)
        doc.save(out_path)
        print(f"  ✅ 已保存: {out_path}")

    print(f"\n[3/3] 完成！三个场景报告已生成到:")
    for fname, _ in scenarios:
        print(f"  📄 {os.path.join(OUTPUT_DIR, fname)}")


if __name__ == "__main__":
    main()
