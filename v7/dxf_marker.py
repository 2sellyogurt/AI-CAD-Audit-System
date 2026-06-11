# -*- coding: utf-8 -*-
"""冲突标记写入器 —— 在源DXF中标注冲突位置（圆+引线+文字）"""
import os, sys, json
from collections import defaultdict

import ezdxf
from ezdxf.math import Vec3

COLORS = {
    "A": 1,   # 红色
    "B": 2,   # 黄色
    "C": 5,   # 蓝色
}


class DXFMarker:
    def __init__(self, conflicts_json_path: str, output_dir: str = None):
        with open(conflicts_json_path, "r", encoding="utf-8") as f:
            self.conflicts = json.load(f)
        self.output_dir = output_dir or os.path.dirname(conflicts_json_path)

    def mark_all(self, dxf_dir: str):
        available = {os.path.splitext(f)[0]: f for f in os.listdir(dxf_dir) if f.endswith(".dxf")}
        files_conflicts = defaultdict(list)
        for c in self.conflicts:
            involved = c.get("involved", "")
            parts = involved.replace(":", "|").split("|")
            for p in parts:
                tokens = p.strip().split()
                for token in tokens:
                    token = token.strip()
                    if "." in token and "dxf" in token.lower():
                        name = token
                    elif token.endswith(".dxf"):
                        name = token
                    else:
                        if token in available:
                            name = available[token]
                        else:
                            continue
                    if name not in files_conflicts:
                        files_conflicts[name] = []
                    files_conflicts[name].append(c)

        for fname, confs in files_conflicts.items():
            fpath = os.path.join(dxf_dir, fname)
            if not os.path.exists(fpath):
                continue
            seen = set()
            unique = []
            for c in confs:
                key = (c.get("type"), c.get("description","")[:80])
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            self._mark_dxf(fpath, unique, fname)

    def _mark_dxf(self, dxf_path: str, conflicts: list, fname: str):
        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
        except Exception as e:
            print(f"  !! 无法打开 {fname}: {e}")
            return

        marker_layer = "_CONFLICT_MARKERS"
        if marker_layer not in doc.layers:
            doc.layers.add(name=marker_layer, color=1)

        for i, c in enumerate(conflicts):
            severity = c.get("severity", "B")
            color = COLORS.get(severity, 2)
            ctype = c.get("type", "unknown")
            desc = c.get("description", "")[:80]
            std = c.get("std", "")[:60]

            coords = c.get("cad_coords", c.get("coords", {}))
            cx = coords.get("x", 0)
            cy = coords.get("y", 0)
            desc_text = desc
            for part in desc.split("区域"):
                desc_text = part
                break

            label = f"[{severity}] {ctype}"

            msp.add_circle(
                center=(cx, cy, 0),
                radius=800,
                dxfattribs={"layer": marker_layer, "color": color}
            )

            text_y = cy + 1200
            msp.add_text(
                label,
                dxfattribs={
                    "layer": marker_layer, "color": color,
                    "height": 400, "style": "Standard"
                }
            ).set_placement((cx - 300, text_y, 0))

            text_y -= 500
            msp.add_text(
                desc_text[:60],
                dxfattribs={
                    "layer": marker_layer, "color": 7,
                    "height": 300, "style": "Standard"
                }
            ).set_placement((cx - 200, text_y, 0))

            if std:
                text_y -= 400
                msp.add_text(
                    std[:60],
                    dxfattribs={
                        "layer": marker_layer, "color": 8,
                        "height": 250, "style": "Standard"
                    }
                ).set_placement((cx - 200, text_y, 0))

        out_path = os.path.join(self.output_dir, fname.replace(".dxf", "_marked.dxf"))
        doc.saveas(out_path)
        print(f"  [{fname[:40]}] → {len(conflicts)} 标记 → {os.path.basename(out_path)}")


if __name__ == "__main__":
    import sys
    conflicts_json = sys.argv[1] if len(sys.argv) > 1 else "spatial_conflicts_v5.json"
    dxf_dir = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\azyp\Desktop\医科大图纸DXF"
    marker = DXFMarker(conflicts_json)
    marker.mark_all(dxf_dir)
    print("done")