# -*- coding: utf-8 -*-
"""DWG→DXF 批量转换器

支持三种转换路线：
  1. ODA File Converter（免费命令行工具，推荐）
  2. AutoCAD 后台命令行（需安装AutoCAD）
  3. 手动提示（需用户自行转换后放入DXF目录）

ODA File Converter 下载: https://www.opendesign.com/guestfiles/oda_file_converter
"""

import os
import subprocess
import logging
import glob
import time
from typing import Dict, List, Optional, Tuple
from .cad_utils import find_autocad, find_oda_converter, get_dwg_output_version

logger = logging.getLogger("v7.dwg_converter")


def convert_dwg_to_dxf_oda(dwg_path: str, output_dir: str, timeout: int = 300) -> bool:
    oda = find_oda_converter()
    if not oda:
        logger.warning("ODA File Converter未找到")
        return False

    os.makedirs(output_dir, exist_ok=True)
    input_dir = os.path.dirname(dwg_path)
    dwg_name = os.path.basename(dwg_path)

    try:
        cmd = [
            oda,
            input_dir,
            output_dir,
            get_dwg_output_version(), "DXF", "0", "1",
            f"*.dwg",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        base = os.path.splitext(dwg_name)[0]
        expected = os.path.join(output_dir, f"{base}.dxf")
        if os.path.exists(expected) and os.path.getsize(expected) > 0:
            logger.info(f"ODA转换成功: {dwg_name} → {os.path.basename(expected)}")
            return True
        else:
            alt = glob.glob(os.path.join(output_dir, "*.dxf"))
            if alt:
                logger.info(f"ODA转换成功(批量): {dwg_name} → {len(alt)}个DXF")
                return True
            logger.error(f"ODA转换失败: {dwg_name}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"ODA转换超时: {dwg_name}")
        return False
    except Exception as e:
        logger.error(f"ODA转换异常: {dwg_name}: {e}")
        return False


def convert_dwg_to_dxf_autocad(dwg_path: str, output_dir: str, timeout: int = 180) -> bool:
    acad = find_autocad()
    if not acad:
        logger.warning("AutoCAD未找到")
        return False

    os.makedirs(output_dir, exist_ok=True)
    abs_dwg = os.path.abspath(dwg_path).replace("\\", "/")
    base = os.path.splitext(os.path.basename(dwg_path))[0]
    abs_dxf = os.path.abspath(os.path.join(output_dir, f"{base}.dxf")).replace("\\", "/")

    scr_content = f"""FILEDIA 0
CMDDIA 0
_DXFOUT "{abs_dxf}" 2013
_CLOSE
Y
FILEDIA 1
CMDDIA 1
"""

    scr_path = os.path.join(output_dir, "_convert.scr")
    with open(scr_path, "w", encoding="utf-8-sig") as f:
        f.write(scr_content)

    try:
        result = subprocess.run(
            [acad, dwg_path, "/b", scr_path, "/nologo"],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if os.path.exists(abs_dxf) and os.path.getsize(abs_dxf) > 0:
            logger.info(f"AutoCAD转换成功: {os.path.basename(dwg_path)} → {os.path.basename(abs_dxf)}")
            return True
        else:
            logger.error(f"AutoCAD转换失败: {os.path.basename(dwg_path)}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"AutoCAD转换超时: {os.path.basename(dwg_path)}")
        return False
    except Exception as e:
        logger.error(f"AutoCAD转换异常: {e}")
        return False
    finally:
        try:
            os.remove(scr_path)
        except Exception as e:
            logger.debug(f"清理脚本文件失败: {e}")


def convert_dwg_batch(dwg_dir: str, output_dir: str,
                      method: str = "auto",
                      max_workers: int = 1,
                      timeout: int = 300) -> Tuple[int, int, List[str]]:
    dwg_files = glob.glob(os.path.join(dwg_dir, "**", "*.dwg"), recursive=True)
    dwg_files = [f for f in dwg_files if not os.path.basename(f).startswith("~$")]
    dwg_files.sort(key=lambda f: os.path.getsize(f))

    if not dwg_files:
        logger.warning(f"未找到DWG文件: {dwg_dir}")
        return 0, 0, []

    os.makedirs(output_dir, exist_ok=True)

    if method == "auto":
        oda = find_oda_converter()
        acad = find_autocad()
        if oda:
            method = "oda"
        elif acad:
            method = "autocad"
        else:
            logger.error("未找到ODA File Converter或AutoCAD，无法自动转换DWG")
            logger.error("请安装ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter")
            logger.error("或手动将DWG转为DXF放入输出目录")
            return 0, len(dwg_files), []

    success = 0
    failed = 0
    dxf_outputs = []

    for i, dwg in enumerate(dwg_files):
        name = os.path.basename(dwg)
        file_mb = os.path.getsize(dwg) / (1024 * 1024)
        logger.info(f"[{i+1}/{len(dwg_files)}] 转换: {name} ({file_mb:.1f}MB)")

        if method == "oda":
            ok = convert_dwg_to_dxf_oda(dwg, output_dir, timeout=timeout)
        elif method == "autocad":
            ok = convert_dwg_to_dxf_autocad(dwg, output_dir, timeout=timeout)
        else:
            ok = False

        if ok:
            success += 1
            base = os.path.splitext(name)[0]
            dxf_out = os.path.join(output_dir, f"{base}.dxf")
            if os.path.exists(dxf_out):
                dxf_outputs.append(dxf_out)
        else:
            failed += 1

    logger.info(f"DWG→DXF转换完成: 成功{success}, 失败{failed}, 总计{len(dwg_files)}")
    return success, failed, dxf_outputs


def check_dwg_version(dwg_path: str) -> Optional[str]:
    try:
        with open(dwg_path, "rb") as f:
            header = f.read(6)
            if header[:4] != b"AC10":
                return None
            versions = {
                b"24": "AC1024 (R2010)",
                b"27": "AC1027 (R2013)",
                b"30": "AC1030 (R2015)",
                b"32": "AC1032 (R2018)",
                b"33": "AC1033 (R2019)",
                b"34": "AC1034 (R2020)",
                b"35": "AC1035 (R2021)",
                b"36": "AC1036 (R2022)",
                b"37": "AC1037 (R2023)",
                b"38": "AC1038 (R2024)",
            }
            ver = header[4:6].decode("ascii", errors="ignore")
            ver_key = header[4:6]
            return versions.get(ver_key, f"AC10{ver}")
    except Exception as e:
        logger.debug(f"读取DWG版本失败: {e}")
        return None


def scan_dwg_folder(dwg_dir: str) -> List[Dict]:
    results = []
    dwg_files = glob.glob(os.path.join(dwg_dir, "**", "*.dwg"), recursive=True)
    dwg_files = [f for f in dwg_files if not os.path.basename(f).startswith("~$")]

    for dwg in dwg_files:
        name = os.path.basename(dwg)
        size_mb = os.path.getsize(dwg) / (1024 * 1024)
        version = check_dwg_version(dwg)
        results.append({
            "file": name,
            "path": dwg,
            "size_mb": round(size_mb, 2),
            "dwg_version": version,
            "rel_path": os.path.relpath(dwg, dwg_dir),
        })

    results.sort(key=lambda x: -x["size_mb"])
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 示例用法：从命令行参数读取路径，或提示用户输入
    if len(sys.argv) >= 3:
        dwg_dir = sys.argv[1]
        out_dir = sys.argv[2]
    else:
        print("用法: python dwg_converter.py <dwg目录> <输出目录>")
        print("示例: python dwg_converter.py ./图纸 ./DXF输出")
        sys.exit(1)

    print("=" * 60)
    print("DWG文件夹扫描")
    print("=" * 60)
    scan = scan_dwg_folder(dwg_dir)
    total_mb = sum(s["size_mb"] for s in scan)
    print(f"DWG文件: {len(scan)}个, 总计{total_mb:.1f}MB")
    for s in scan[:10]:
        print(f"  {s['size_mb']:>8.1f}MB  {s['dwg_version'] or 'N/A':<20}  {s['rel_path'][:60]}")
    if len(scan) > 10:
        print(f"  ... 共{len(scan)}个文件")

    print(f"\nDWG→DXF转换: {dwg_dir} → {out_dir}")
    print("=" * 60)
    ok, fail, _ = convert_dwg_batch(dwg_dir, out_dir, method="auto")
    print(f"\n结果: 成功{ok}, 失败{fail}")