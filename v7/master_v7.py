# -*- coding: utf-8 -*-
"""
v7.0 主控入口 — 一键串联全流程

使用:
  python master_v7.py                        # 完整流程（需DXF+LLM API Key）
  python master_v7.py --dry-run             # 干跑模式（无LLM调用，仅验证流程）
  python master_v7.py --review-only         # 仅启人工复核界面（用已有问题池）
  python master_v7.py --demo               # 演示模式（模拟数据+启动复核界面）

环境变量:
  ZHIPU_API_KEY   - 智谱API Key（文本+视觉默认Provider）
  DEEPSEEK_API_KEY - DeepSeek API Key（备用）
  OPENAI_API_KEY   - OpenAI API Key（复杂视觉检查）
"""

import sys, os, argparse, glob, json, time
from datetime import datetime

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from v7.llm import LLMFactory
from v7.checkpoints import CheckpointEngine
from v7.preprocessor import DrawingExtractor, StandardizationChecker
from v7.problem_pool import ProblemPool, UnifiedIssue, Provenance, DataSource
from v7.agents import (BuildingAgent, StructureAgent, HvacAgent, PlumbingAgent,
                       ElectricalAgent, FireAgent, FreeReviewAgent, ChiefAgent,
                       CurtainWallAgent, DecorationAgent, LandscapeAgent, FoundationPitAgent)
from v7.scheduler import AgentOrchestrator
from v7.audit import FalseNegativeAuditor
from v7.scanner import DrawingScanner
from v7.cross_drawing import CrossDrawingContext
from v7.conflict_diff import diff as conflict_diff_run
from v7.conflict_state_manager import ConflictStateManager, STATUS_WAIVED, STATUS_RESOLVED


def run_dry_run(args):
    """干跑模式：验证所有模块可导入+数据流可跑通，不调用LLM。"""
    print("=" * 60)
    print("  v7.0 干跑测试（无LLM调用）")
    print("=" * 60)

    t0 = time.time()

    # 1. 加载检查点
    print("\n[1/6] 加载检查点引擎...")
    engine = CheckpointEngine()
    print(f"  加载: {engine.total_count} 个检查点")
    for cp in engine.all_checkpoints:
        print(f"    [{cp.id}] {cp.name} (type={cp.check_type.value}, route={cp.route.value}→resolved={engine.resolve_route(cp).value})")

    # 2. 测试DXF提取
    print("\n[2/6] 图纸预处理...")
    extractor = DrawingExtractor()
    checker = StandardizationChecker()

    dxf_files = glob.glob(os.path.join(args.dxf_dir, "*.dxf"))
    if dxf_files:
        for f in dxf_files[:3]:
            info = extractor.process_drawing(f)
            print(f"  {info.readable_name}: discipline={info.discipline}, {len(info.text_entities)} text entities")
            if info.text_content:
                std_result = checker.check(info.text_content, info.discipline)
                print(f"    标准化校验: {std_result.passed_checks}/{std_result.total_checks} 通过")
    else:
        print("  未找到DXF文件，使用模拟数据")
        print("  分类规则测试: ", end="")
        tests = [("建施-01", "building"), ("结施-01", "structure"), ("水施-01", "plumbing")]
        for name, exp in tests:
            assert extractor.classify(name) == exp
        print("OK")

    # 3. 创建Agent集群
    print("\n[3/6] 创建Agent集群...")
    orch = AgentOrchestrator()
    orch.create_all_agents()
    for aid, agent in orch.agents.items():
        prompt = agent.build_system_prompt()
        print(f"  [{aid}] {agent.config.role_title} - 人格Prompt {len(prompt)}字")
    print(f"  共 {len(orch.agents)} 个Agent就绪")

    # 4. 创建问题池（模拟数据）
    print("\n[4/6] 创建统一问题池...")
    pool = ProblemPool()
    from v7.preprocessor import DrawingInfo
    from v7.preprocessor import TextEntity
    from v7.agents.base_agent import AgentReport
    from v7.checkpoints import CheckResult
    sim_drawings = [
        DrawingInfo("建施-01.dxf", "建施-01.dxf", "building",
                    text_entities=[TextEntity("T1", "疏散门 M1 宽度 800mm", 1000, 2000, 0, "", "TEXT", "建施-01.dxf")],
                    text_content="疏散门 M1 宽度 800mm\n楼梯梯段净宽 1050mm"),
    ]
    building = orch.agents.get("building")
    if building and sim_drawings:
        building._report = AgentReport(agent_id="building", agent_name="建筑工程师Agent")
        checkpoints = engine.list_by_discipline("building")
        for d in sim_drawings:
            for cp in checkpoints[:3]:
                from v7.checkpoints import CheckResult
                sim_result = CheckResult(
                    checkpoint_id=cp.id, checkpoint_name=cp.name,
                    verdict="不合规", confidence="high", severity=cp.severity.value,
                    standard_code=cp.standard_code, standard_clause=cp.standard_clause,
                    route_used="text", model_used="dry-run", discipline=cp.discipline.value
                )
                pool.add_from_checkpoint(sim_result, d.text_entities[0] if d.text_entities else None, agent_name="建筑Agent")
    print(f"  问题池: {len(pool._issues)} 个模拟问题")

    # 5. 总工汇总
    print("\n[5/6] 总工Agent汇总...")
    chief = ChiefAgent(pool)
    chief_report = chief.execute()
    print(f"  {chief_report.summary}")
    if chief_report.markdown_report:
        report_path = os.path.join(args.output_dir, "dry_run_report.md")
        os.makedirs(args.output_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(chief_report.markdown_report)
        print(f"  报告已保存: {report_path}")

    # 6. 审计抽样
    print("\n[6/6] 假阴性审计...")
    auditor = FalseNegativeAuditor(sample_rate=0.5, threshold=0.001, checkpoint_engine=engine, problem_pool=pool)
    audit_report = auditor.audit()
    print(f"  抽样: {audit_report.sample_size}/{audit_report.total_passed}, 假阴性率: {audit_report.false_negative_rate:.2%}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  干跑完成，耗时 {elapsed:.1f} 秒")
    print(f"  所有9个模块验证通过 ✓")
    print(f"{'='*60}")
    return pool


def run_full(args):
    """完整模式：三阶段管线（扫描→智能审查→汇总审计）。"""
    print("=" * 60)
    print("  v7.0 三阶段智能审查流程")
    print("=" * 60)
    t0 = time.time()

    factory = LLMFactory()
    print(f"  LLM配置: text={factory.get_text_adapter().config.model}, vision={factory.get_vision_adapter().config.model}")

    # === 阶段0: 预处理（含缓存） ===
    print("\n[0] 图纸预处理...")
    extractor = DrawingExtractor()
    dxf_files = glob.glob(os.path.join(args.dxf_dir, "*.dxf"))
    if not dxf_files:
        print("  错误: 未找到DXF文件")
        return None
    print(f"  找到 {len(dxf_files)} 个DXF文件")

    drawings = []
    png_dir = os.path.join(args.output_dir, "png")
    for f in dxf_files:
        info = extractor.process_drawing(f, png_output_dir=png_dir)
        drawings.append(info)
        png_status = "✓" if info.png_path else "✗"
        print(f"    {info.readable_name} → {info.discipline} ({len(info.text_entities)} entities, PNG:{png_status})")

    merged_text = "\n\n=====\n\n".join(
        f"【{getattr(d, 'readable_name', '')}】\n{getattr(d, 'text_content', '') or ''}"
        for d in drawings
    )

    # === 阶段1: 图纸扫描 ===
    print("\n[1] 图纸智能扫描...")
    scanner = DrawingScanner(llm_factory=factory)
    scan = scanner.scan(merged_text)
    print(f"  建筑类型: {scan.building_type}")
    print(f"  风险等级: {scan.risk_level}")
    print(f"  涉及专业: {scan.relevant_disciplines}")
    print(f"  跳过专业: {scan.suggested_skip_disciplines}")
    print(f"  优先标签: {scan.priority_tags}")
    print(f"  需视觉审查: {scan.visual_required}")
    print(f"  扫描耗时: {scan.scan_time_ms:.0f}ms")
    if scan.notes:
        print(f"  扫描备注: {scan.notes[:200]}")

    # === 阶段2: 智能审查 ===
    print(f"\n[2] 智能Agent审查（仅激活相关专业+优先检查点）...")
    engine = CheckpointEngine()
    print(f"  {engine.total_count} 个检查点已加载，按扫描结果智能筛选")

    pool = ProblemPool()
    orch = AgentOrchestrator()
    orch.create_all_agents()

    image_paths = {}
    for d in drawings:
        pngs = list(d.png_paths) if d.png_paths else ([d.png_path] if d.png_path else [])
        if pngs:
            image_paths[d.readable_name] = pngs

    report = orch.execute_smart(drawings, problem_pool=pool,
                                image_paths=image_paths, scan_result=scan)
    print(f"  审查完成: {report.total_issues} 个问题, "
          f"{len(report.agent_reports)} 个Agent参与, "
          f"{len(report.failed_agents)} 个失败")

    # === 阶段3: 汇总+审计 ===
    print("\n[3] 跨图纸上下文分析...")
    cross_ctx = CrossDrawingContext()
    for d in drawings:
        cross_ctx.add_drawing(d.readable_name, d.discipline, d.text_content or "")
    cross_summary = cross_ctx.get_context_summary()
    print(f"  {cross_summary}")
    cross_issues = cross_ctx.analyze()
    if cross_issues:
        print(f"  发现 {len(cross_issues)} 个跨图纸一致性问题：")
        for ci in cross_issues:
            print(f"    [{ci.severity}] {ci.issue_type}: {ci.description[:80]}...")
            pool.add_issue(UnifiedIssue(
                issue_id=ci.issue_id,
                checkpoint_id="CROSS_DRAWING",
                checkpoint_name=f"跨图纸一致性-{ci.issue_type}",
                discipline="cross",
                professional="跨专业",
                description=ci.description,
                suggestion=ci.suggestion,
                severity=ci.severity,
                confidence="high",
                drawing_name=f"{ci.drawing_a} vs {ci.drawing_b}",
                route_used="dual",
                provenance=Provenance(
                    data_source=DataSource(type="cross_drawing", file=ci.drawing_a,
                                           raw_text=ci.evidence_a, extract_method="regex_compare"),
                ),
                create_time=datetime.now().isoformat(),
            ))
    else:
        print(f"  未发现跨图纸一致性问题")

    print("\n[4] 总工汇总...")
    chief = ChiefAgent(pool)
    chief_report = chief.execute(project_name=args.project_name,
                                 coverage_stats=report.coverage_stats())
    print(f"  {chief_report.summary}")

    report_path = os.path.join(args.output_dir, "review_report.md")
    os.makedirs(args.output_dir, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(chief_report.markdown_report)
    print(f"  报告: {report_path}")

    print("\n[5] 假阴性审计...")
    compliant = pool.get_compliant_results()
    print(f"  合规记录: {len(compliant)} 条可供抽样审计")
    if compliant:
        auditor = FalseNegativeAuditor(checkpoint_engine=engine, problem_pool=pool)
        audit_report = auditor.audit()
        print(f"  审计: {audit_report.sample_size}样本, 假阴性率: {audit_report.false_negative_rate:.2%}")
    else:
        print(f"  审计: 无合规记录（全量不合规或首次审查）")

    if args.conflict_diff:
        run_conflict_diff_stage(args)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  总耗时: {elapsed:.1f} 秒 ({elapsed/60:.1f} 分钟)")
    print(f"  问题数: {len(pool._issues)}")
    print(f"  扫描+审查+汇总阶段完成")
    print(f"{'='*60}")
    return pool


def run_demo(args):
    """演示模式：用模拟数据运行全流程 + 启动复核界面。"""
    print("=" * 60)
    print("  v7.0 演示模式")
    print("=" * 60)

    engine = CheckpointEngine()
    pool = ProblemPool()

    # 创建模拟问题
    demo_data = [
        ("JZ-001", "疏散门净宽度检查", "疏散门M1宽度标注800mm，不满足≥900mm要求", "A",
         "建施-01.dxf", "A轴/3轴", "将疏散门宽度增加至≥900mm",
         "GB50016-2014(2018)", "5.5.30",
         "_.ZOOM _C 12345,67890,0 5000\n_.CIRCLE 12345,67890,0 1000"),
        ("JZ-002", "楼梯梯段净宽检查", "楼梯梯段净宽标注1050mm，不满足≥1100mm要求", "A",
         "建施-02.dxf", "C轴/1-2轴", "增加楼梯梯段宽度至≥1100mm",
         "GB50352-2019", "6.8.3", ""),
        ("JZ-003", "窗台防护措施检查", "窗台高度850mm，低于900mm未标注防护措施", "B",
         "建施-01.dxf", "B轴/5轴", "窗台低于900mm处增设防护栏杆",
         "GB50352-2019", "6.11.6", ""),
        ("JZ-004", "无障碍卫生间检查", "未标注无障碍卫生间", "B",
         "建施-03.dxf", "", "增设无障碍卫生间或厕位",
         "GB50763-2012", "3.5.1", ""),
        ("JZ-005", "防火墙门窗洞口间距检查", "防火墙两侧窗洞口间距标注1800mm，不满足≥2000mm", "A",
         "建施-04.dxf", "防火墙两侧", "调整门窗洞口位置或增设防火挑檐",
         "GB50016-2014(2018)", "6.1.3", ""),
        ("STRUCT-001", "梁截面尺寸检查", "梁KL2截面标注200×400，不满足最小截面要求", "B",
         "结施-01.dxf", "2层①-②轴", "调整梁截面至≥250×500",
         "GB50010-2010(2015)", "11.3.5", ""),
        ("PLUMB-001", "消火栓布置检查", "消火栓间距标注35m，不满足≤30m要求", "B",
         "水施-01.dxf", "走廊", "增设消火栓使间距≤30m",
         "GB50974-2014", "7.4.6", ""),
    ]

    for i, (cpid, name, desc, sev, dwg, loc, sug, std, clause, script) in enumerate(demo_data):
        issue = UnifiedIssue(
            issue_id=f"DEMO-{i+1:03d}",
            checkpoint_id=cpid, checkpoint_name=name,
            professional="建筑" if cpid.startswith("JZ") else ("结构" if cpid.startswith("S") else "给排水"),
            description=desc, severity=sev, suggestion=sug,
            standard_code=std, standard_clause=clause,
            drawing_name=dwg, location=loc,
            cad_script=script,
            route_used="dual" if sev == "A" else "text",
            provenance=Provenance(
                data_source=DataSource(type="dxf_text", file=dwg, raw_text=desc[:50], extract_method="ezdxf_parse"),
                verification=type('v',(),{'is_dual_verified':sev=='A','to_dict':lambda:{"is_dual_verified":sev=='A'}})()
            ),
            create_time=datetime.now().isoformat(),
        )
        issue.provenance = Provenance(
            data_source=DataSource(type="dxf_text", file=dwg, raw_text=desc[:50], extract_method="ezdxf_parse"),
        )
        if sev == "A":
            issue.provenance.verification.is_dual_verified = True
        pool.add_issue(issue)

    print(f"  创建 {len(pool._issues)} 个模拟问题")
    print(f"    A级: {pool.count_by_severity().get('A',0)}, B级: {pool.count_by_severity().get('B',0)}")
    print(f"    双路径验证: {pool.count_dual_verified()}")

    chief = ChiefAgent(pool)
    chief_report = chief.execute()
    os.makedirs(args.output_dir, exist_ok=True)
    path = os.path.join(args.output_dir, "demo_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(chief_report.markdown_report)
    print(f"  报告: {path}")

    if args.ui:
        print(f"\n  启动人工复核界面: http://localhost:{args.port}")
        from v7.review_ui import run_server
        run_server(pool, "演示项目", args.port, args.output_dir)
    else:
        stats = pool.stats()
        print(f"\n  跳过UI（加 --ui 启动复核界面）")
        print(f"  人工复核界面: python master_v7.py --demo --ui --port 8080")

    return pool


def run_conflict_diff_stage(args):
    print(f"\n[冲突差异比对] 持久化状态管理")
    state_manager = ConflictStateManager(project_name=args.project or "default")
    cur = args.conflict_diff
    prev = args.conflict_prev
    if not os.path.exists(cur):
        print(f"  跳过: 当前冲突文件不存在 ({cur})")
        return
    if prev and not os.path.exists(prev):
        print(f"  警告: 历史基线文件不存在 ({prev})，将以无基线模式运行")

    out = args.conflict_output or cur.replace(".json", "_diff.json")
    conflict_diff_run(cur, prev, out, state_manager=state_manager)

    if args.conflict_show_status:
        summary = state_manager.summary()
        print(f"\n  状态库路径: {summary['cache_file']}")
        print(f"  总记录: {summary['total']}")
        waived = summary['by_status'].get(STATUS_WAIVED, 0)
        resolved = summary['by_status'].get(STATUS_RESOLVED, 0)
        print(f"  已豁免: {waived} | 已解决: {resolved}")


def run_conflict_status(args):
    state_manager = ConflictStateManager(project_name=args.project or "default")
    summary = state_manager.summary()
    print(f"项目: {summary['project']}")
    print(f"缓存文件: {summary['cache_file']}")
    print(f"总记录: {summary['total']}")
    print(f"状态分布: {summary['by_status']}")
    if args.conflict_status_detail and os.path.exists(args.conflict_status_detail):
        with open(args.conflict_status_detail, "r", encoding="utf-8") as f:
            cur = json.load(f)
        from v7.conflict_state_manager import make_key
        cur_keys = {make_key(c) for c in cur}
        for status in [STATUS_WAIVED, STATUS_RESOLVED]:
            items = state_manager.list_by_status(status)
            if items:
                print(f"\n{status} ({len(items)}条):")
                for key, entry in items:
                    active = "✓" if key in cur_keys else "✗"
                    print(f"  {active} {key[:100]}")
                    if entry.get("note"):
                        print(f"    {entry['note']}")


def main():
    parser = argparse.ArgumentParser(description="v7.0 AI审图系统主控入口")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式（无LLM）")
    parser.add_argument("--demo", action="store_true", help="演示模式（模拟数据）")
    parser.add_argument("--review-only", help="仅启动复核界面（指定问题池JSON路径）")
    parser.add_argument("--ui", action="store_true", help="启动复核Web界面")
    parser.add_argument("--dxf-dir", default="./input", help="DXF目录")
    parser.add_argument("--output-dir", default="./output_v7.0", help="输出目录")
    parser.add_argument("--port", type=int, default=8080, help="Web端口")
    parser.add_argument("--project", default=None, help="项目名称（用于状态库隔离）")
    parser.add_argument("--conflict-diff", default=None,
                        help="启用冲突差异比对，指定当前冲突JSON路径")
    parser.add_argument("--conflict-prev", default=None,
                        help="冲突比对的历史基线JSON路径")
    parser.add_argument("--conflict-output", default=None,
                        help="冲突差异比对的输出JSON路径")
    parser.add_argument("--conflict-show-status", action="store_true",
                        help="比对后显示持久化状态库概况")
    parser.add_argument("--conflict-status", action="store_true",
                        help="仅查看冲突状态库（不执行审查）")
    parser.add_argument("--conflict-status-detail", default=None,
                        help="显示状态详情时对照的当前冲突JSON")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if args.conflict_status:
        run_conflict_status(args)
        return

    if args.review_only:
        pool = ProblemPool()
        if os.path.exists(args.review_only):
            import json as _json
            with open(args.review_only, "r", encoding="utf-8") as f:
                data = _json.load(f)
            for item in data.get("issues", []):
                issue = UnifiedIssue(**{k: v for k, v in item.items()
                    if k in UnifiedIssue.__dataclass_fields__})
                pool.add_issue(issue)
            print(f"从 {args.review_only} 加载 {len(pool._issues)} 个问题")
        from v7.review_ui import run_server
        run_server(pool, "审查项目", args.port, args.output_dir)
        return

    if args.demo:
        run_demo(args)
    elif args.dry_run:
        run_dry_run(args)
    else:
        if not os.environ.get("ZHIPU_API_KEY") and not os.environ.get("DEEPSEEK_API_KEY"):
            print("⚠️  未检测到LLM API Key环境变量")
            print("  请设置: ZHIPU_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY")
            print("  或用 --dry-run 干跑模式 / --demo 演示模式\n")
            return 1
        run_full(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
