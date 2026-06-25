# -*- coding: utf-8 -*-
"""图纸智能拆分与标注 主控管线

完整工作流：
  阶段1: DWG文件夹扫描 → 版本识别、文件统计
  阶段2: DWG→DXF批量转换（ODA/AutoCAD）
  阶段3: 图框检测 → 每份DXF内的图纸数量识别
  阶段4: 子图拆分 → 按图框范围拆分为独立DXF
  阶段5: 图签提取 → 标题栏元数据解析
  阶段6: 结构化输出 → JSON/Excel/CSV

使用:
  python drawing_pipeline.py                              # 完整流程
  python drawing_pipeline.py --scan-only                  # 仅扫描统计
  python drawing_pipeline.py --dxf-dir <path>             # 跳过DWG转换，直接用DXF
  python drawing_pipeline.py --no-split                   # 只检测不拆分
  python drawing_pipeline.py --output <dir>               # 指定输出目录
"""

import sys
import os
import argparse
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("v7.drawing_pipeline")


def setup_args():
    p = argparse.ArgumentParser(description="图纸智能拆分与标注管线")
    p.add_argument("--dwg-dir", default=None,
                   help="DWG源文件目录（必填）")
    p.add_argument("--dxf-dir", default=None,
                   help="DXF文件目录（如已有DXF可跳过转换）")
    p.add_argument("--output", default="", help="输出目录（默认: output_v7.0/split_annotated/）")
    p.add_argument("--scan-only", action="store_true", help="仅扫描统计，不拆分")
    p.add_argument("--no-convert", action="store_true", help="跳过DWG→DXF转换")
    p.add_argument("--no-split", action="store_true", help="只检测不拆分")
    p.add_argument("--no-text-verify", action="store_true",
                   help="禁用图框文字语义验证（默认开启）")
    p.add_argument("--tolerance", type=float, default=0.15,
                   help="图框尺寸容差（默认0.15）")
    p.add_argument("--split-margin", type=float, default=50.0,
                   help="图框拆分边界容差mm（默认50）")
    p.add_argument("--convert-method", default="auto",
                   choices=["auto", "oda", "autocad", "none"],
                   help="DWG转换方法")
    return p.parse_args()


def scan_dwg_folder(dwg_dir: str) -> Dict[str, Any]:
    from v7.preprocessor.dwg_converter import scan_dwg_folder as _scan
    results = _scan(dwg_dir)
    summary = {
        "total_files": len(results),
        "total_size_mb": round(sum(r["size_mb"] for r in results), 1),
        "max_file_mb": round(max((r["size_mb"] for r in results), default=0), 1),
        "by_extension": {},
        "files": results,
    }
    for r in results:
        ext = os.path.splitext(r["file"])[1].lower()
        summary["by_extension"][ext] = summary["by_extension"].get(ext, 0) + 1
    return summary


def detect_frames_batch(dxf_dir: str, text_verify: bool, tolerance: float) -> Dict[str, Any]:
    from v7.preprocessor.enhanced_frame_detector import EnhancedFrameDetector
    import glob

    detector = EnhancedFrameDetector(
        text_verify=text_verify,
        tolerance=tolerance,
    )
    dxf_files = sorted(glob.glob(os.path.join(dxf_dir, "*.dxf")),
                       key=lambda f: os.path.getsize(f))

    total_sheets = 0
    multi_sheet_count = 0
    single_sheet_count = 0
    empty_count = 0
    details = []

    for dxf in dxf_files:
        name = os.path.basename(dxf)
        file_mb = os.path.getsize(dxf) / (1024 * 1024)
        try:
            result = detector.detect_all(dxf)
            result["file_size_mb"] = round(file_mb, 1)
            details.append(result)

            sheets = result["total_sheets"]
            total_sheets += sheets
            if sheets > 1:
                multi_sheet_count += 1
            elif sheets == 1:
                single_sheet_count += 1
            else:
                empty_count += 1

            logger.info(f"  {name[:50]:<50} | {sheets:>3}张 | {result['detection_method']}")
        except Exception as e:
            logger.error(f"检测失败: {name}: {e}")
            details.append({
                "file": name, "file_size_mb": round(file_mb, 1),
                "total_sheets": 0, "detection_method": "error",
                "_error": str(e),
            })
            empty_count += 1

    return {
        "dxf_count": len(dxf_files),
        "total_sheets": total_sheets,
        "multi_sheet_files": multi_sheet_count,
        "single_sheet_files": single_sheet_count,
        "empty_files": empty_count,
        "details": details,
    }


def split_dxf_batch(dxf_dir: str, output_dir: str,
                    text_verify: bool, tolerance: float,
                    split_margin: float,
                    pre_detected_frames: Dict[str, Dict] = None) -> Dict[str, Any]:
    from v7.preprocessor.dwg_subset_splitter import split_dxf_by_frames, split_single_dxf, split_dxf_by_layouts
    import glob

    if pre_detected_frames is None:
        from v7.preprocessor.enhanced_frame_detector import EnhancedFrameDetector
        detector = EnhancedFrameDetector(
            text_verify=text_verify,
            tolerance=tolerance,
        )

    dxf_files = sorted(glob.glob(os.path.join(dxf_dir, "*.dxf")),
                       key=lambda f: os.path.getsize(f))

    total_split = 0
    total_original = 0
    split_details = []

    for dxf in dxf_files:
        name = os.path.basename(dxf)
        file_mb = os.path.getsize(dxf) / (1024 * 1024)

        entry = pre_detected_frames.get(name) if pre_detected_frames else None
        if entry is None:
            try:
                if pre_detected_frames is None:
                    frames = detector.detect_frames(dxf)
                    layouts = None
                else:
                    frames = []
                    layouts = None
            except Exception as e:
                logger.error(f"图框检测失败: {name}: {e}")
                frames = []
                layouts = None
        else:
            frames = entry.get("frames", [])
            layouts = entry.get("layouts", [])
            method = entry.get("method", "single")

        if layouts and len(layouts) > 1:
            sub_files = split_dxf_by_layouts(dxf, output_dir, layout_names=layouts)
            split_details.append({
                "file": name, "file_size_mb": round(file_mb, 1),
                "frames": 0, "layouts": len(layouts),
                "split_count": len(sub_files),
                "split_method": "layout",
                "split_files": [os.path.basename(f) for f in sub_files],
            })
            total_split += len(sub_files)
            total_original += 1
        elif len(frames) > 1:
            sub_files = split_dxf_by_frames(dxf, frames, output_dir, margin=split_margin)
            split_details.append({
                "file": name, "file_size_mb": round(file_mb, 1),
                "frames": len(frames), "layouts": 0,
                "split_count": len(sub_files),
                "split_method": "frame",
                "split_files": [os.path.basename(f) for f in sub_files],
            })
            total_split += len(sub_files)
            total_original += 1
        else:
            sub_files = split_single_dxf(dxf, output_dir)
            split_details.append({
                "file": name, "file_size_mb": round(file_mb, 1),
                "frames": len(frames), "layouts": len(layouts) if layouts else 0,
                "split_count": len(sub_files),
                "split_method": "single",
                "split_files": [os.path.basename(f) for f in sub_files],
            })
            if sub_files:
                total_split += 1
                total_original += 1

    return {
        "original_files": total_original,
        "split_files": total_split,
        "details": split_details,
    }


def extract_metadata_batch(dxf_dir: str, output_dir: str,
                           text_verify: bool, tolerance: float,
                           pre_detected_frames: Dict[str, Dict] = None) -> Dict[str, Any]:
    from v7.preprocessor.title_block_extractor import TitleBlockExtractor
    import glob

    detector = None
    if pre_detected_frames is None:
        from v7.preprocessor.enhanced_frame_detector import EnhancedFrameDetector
        detector = EnhancedFrameDetector(
            text_verify=text_verify,
            tolerance=tolerance,
        )

    extractor = TitleBlockExtractor()
    dxf_files = sorted(glob.glob(os.path.join(dxf_dir, "*.dxf")),
                       key=lambda f: os.path.getsize(f))

    all_metadata = []
    for dxf in dxf_files:
        name = os.path.basename(dxf)
        file_mb = os.path.getsize(dxf) / (1024 * 1024)

        entry = pre_detected_frames.get(name) if pre_detected_frames else None
        if entry is None:
            try:
                if detector is not None:
                    frames = detector.detect_frames(dxf)
                else:
                    frames = None
            except Exception as e:
                logger.debug(f"图框检测失败: {dxf}, {e}")
                frames = None
        else:
            frames = entry.get("frames", None)
            if not frames:
                frames = None

        try:
            data = extractor.extract(dxf, frames=frames)
            data["file_size_mb"] = round(file_mb, 1)
            all_metadata.append(data)
            logger.info(f"  元数据: {name[:40]:<40} | 图框{data.get('frame_count',0)} | "
                        f"图号={data.get('drawing_no','')[:15]} | 图名={data.get('drawing_name','')[:20]}")
        except Exception as e:
            logger.error(f"元数据提取失败: {name}: {e}")

    json_path = os.path.join(output_dir, "metadata.json")
    xlsx_path = os.path.join(output_dir, "metadata.xlsx")

    extractor.to_json(all_metadata, json_path)

    try:
        extractor.to_excel(all_metadata, xlsx_path)
    except Exception as e:
        logger.warning(f"Excel导出失败: {e}")

    return {
        "total_files": len(all_metadata),
        "json_path": json_path,
        "xlsx_path": xlsx_path if os.path.exists(xlsx_path) else "",
        "metadata": all_metadata,
    }


def _build_frame_map(detection: Dict) -> Dict[str, Dict]:
    """从检测结果构建 文件名→{frames, layouts, method} 的映射"""
    frame_map = {}
    if not detection or "details" not in detection:
        return frame_map
    for detail in detection["details"]:
        fname = detail.get("file", "")
        entry = {
            "frames": [],
            "layouts": detail.get("layout_names", []),
            "method": detail.get("detection_method", "single"),
        }
        for fd in detail.get("model_space_frame_details", []):
            if fd.get("x_min") is not None:
                entry["frames"].append((
                    fd.get("name", "?"),
                    fd["x_min"], fd["y_min"],
                    fd["x_max"], fd["y_max"],
                ))
        if entry["frames"] or entry["layouts"]:
            frame_map[fname] = entry
    return frame_map


def print_summary(scan: Dict, detection: Dict, split_result: Dict,
                  metadata_result: Dict, elapsed: float):
    print("\n" + "=" * 70)
    print("  图纸智能拆分与标注 - 完成报告")
    print("=" * 70)
    print(f"  总耗时: {elapsed:.0f}s ({elapsed/60:.1f}分钟)")
    print()

    if scan:
        print(f"  [阶段1] DWG文件夹扫描")
        print(f"    文件数: {scan['total_files']}个, 总大小: {scan['total_size_mb']:.1f}MB")
        print()

    if detection:
        print(f"  [阶段3] 图框检测")
        print(f"    DXF文件: {detection['dxf_count']}个")
        print(f"    图纸总张数: {detection['total_sheets']}张")
        print(f"    多图纸文件: {detection['multi_sheet_files']}个")
        print(f"    单图纸文件: {detection['single_sheet_files']}个")
        print()

    if split_result:
        layout_splits = sum(1 for d in split_result.get("details", [])
                           if d.get("split_method") == "layout")
        frame_splits = sum(1 for d in split_result.get("details", [])
                          if d.get("split_method") == "frame")
        print(f"  [阶段4] 子图拆分")
        print(f"    原始DXF: {split_result['original_files']}个")
        print(f"    拆分后子DXF: {split_result['split_files']}个")
        if layout_splits:
            print(f"    布局拆分: {layout_splits}个文件")
        if frame_splits:
            print(f"    图框拆分: {frame_splits}个文件")
        print()

    if metadata_result:
        print(f"  [阶段5] 图签元数据")
        print(f"    提取文件: {metadata_result['total_files']}个")
        if metadata_result.get("json_path"):
            print(f"    JSON: {metadata_result['json_path']}")
        if metadata_result.get("xlsx_path"):
            print(f"    Excel: {metadata_result['xlsx_path']}")
        print()

    print("=" * 70)


def main():
    args = setup_args()

    if args.no_text_verify:
        args.text_verify = False
    else:
        args.text_verify = True  # 默认开启

    project_output = os.path.join(_parent, "output_v7.0")
    output_dir = args.output or os.path.join(project_output, "split_annotated")
    os.makedirs(output_dir, exist_ok=True)

    # 校验：未提供路径时给出明确提示
    missing = []
    if not args.no_convert and args.convert_method != "none" and not args.dwg_dir:
        missing.append("--dwg-dir（DWG源文件目录）")
    if not args.dxf_dir:
        missing.append("--dxf-dir（DXF文件目录）")
    if missing:
        print(f"错误：缺少必填参数 {', '.join(missing)}")
        print("用法: python drawing_pipeline.py --dwg-dir <路径> --dxf-dir <路径>")
        sys.exit(1)

    t_start = time.time()

    scan = None
    detection = None
    split_result = None
    metadata_result = None

    print("=" * 70)
    print("  图纸智能拆分与标注管线 v1.0")
    print(f"  DWG源: {args.dwg_dir}")
    print(f"  DXF目录: {args.dxf_dir}")
    print(f"  输出: {output_dir}")
    print("=" * 70)

    if not args.no_convert and args.convert_method != "none":
        from v7.preprocessor.dwg_converter import scan_dwg_folder, convert_dwg_batch

        print("\n[阶段1] DWG文件夹扫描...")
        scan = scan_dwg_folder(args.dwg_dir)
        logger.info(f"DWG文件: {scan['total_files']}个, 总计{scan['total_size_mb']:.1f}MB")

        print("\n[阶段2] DWG→DXF转换...")
        ok, fail, _ = convert_dwg_batch(
            args.dwg_dir, args.dxf_dir,
            method=args.convert_method,
        )
        logger.info(f"转换结果: 成功{ok}, 失败{fail}")
    else:
        logger.info("跳过DWG→DXF转换")

    if args.scan_only:
        if detection is None:
            print("\n[阶段3] 图框检测...")
            detection = detect_frames_batch(args.dxf_dir, args.text_verify, args.tolerance)
        print_summary(scan, detection, split_result, metadata_result, time.time() - t_start)
        return 0

    print("\n[阶段3] 图框检测...")
    detection = detect_frames_batch(args.dxf_dir, args.text_verify, args.tolerance)
    logger.info(f"检测完成: {detection['total_sheets']}张图纸, "
                f"{detection['multi_sheet_files']}个多图文件")

    if not args.no_split:
        print("\n[阶段4] 子图拆分...")
        split_output = os.path.join(output_dir, "split_dxf")
        pre_frames = _build_frame_map(detection)
        split_result = split_dxf_batch(
            args.dxf_dir, split_output,
            args.text_verify, args.tolerance, args.split_margin,
            pre_detected_frames=pre_frames,
        )
        logger.info(f"拆分完成: {split_result['split_files']}个子DXF")
    else:
        logger.info("跳过子图拆分（--no-split）")

    print("\n[阶段5] 图签元数据提取...")
    metadata_dir = split_output if not args.no_split and split_result else args.dxf_dir
    pre_frames_meta = _build_frame_map(detection)
    metadata_result = extract_metadata_batch(
        metadata_dir, output_dir,
        args.text_verify, args.tolerance,
        pre_detected_frames=pre_frames_meta,
    )
    logger.info(f"元数据提取完成: {metadata_result['total_files']}个文件")

    final_report = {
        "timestamp": datetime.now().isoformat(),
        "source": args.dwg_dir,
        "dxf_dir": args.dxf_dir,
        "output_dir": output_dir,
        "elapsed_seconds": round(time.time() - t_start, 1),
        "scan": scan,
        "detection": detection,
        "split": split_result,
        "metadata": {
            "total_files": metadata_result["total_files"],
            "json_path": metadata_result.get("json_path", ""),
            "xlsx_path": metadata_result.get("xlsx_path", ""),
        } if metadata_result else None,
    }

    report_path = os.path.join(output_dir, "pipeline_report.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2, default=str)

    print_summary(scan, detection, split_result, metadata_result, time.time() - t_start)
    print(f"\n完整报告: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())