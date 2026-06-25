# -*- coding: utf-8 -*-
"""
三场景报告生成器 - 已迁移到共享模块
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report_generation.scene_reports import generate_all_scenes, CONFLICT_CN, DISCIPLINE_CN
from uai_review_data import UAI_FINDINGS, SEVERITY_ADJUST

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
OUTPUT_DIR = os.path.join(BASE, "output_v7.0")


def main():
    spatial_path = os.path.join(BASE, r"v7\spatial_conflicts_v5.json")
    
    if os.path.exists(spatial_path):
        with open(spatial_path, "r", encoding="utf-8") as f:
            spatial_conflicts = json.load(f)
    else:
        spatial_conflicts = []
    
    issues = []
    for disc, findings in UAI_FINDINGS.items():
        for finding in findings:
            issues.append({
                "id": finding.get("id", ""),
                "severity": finding.get("severity", "B"),
                "discipline": disc,
                "description": finding.get("finding", ""),
            })
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = generate_all_scenes(OUTPUT_DIR, issues, spatial_conflicts,
                                  os.environ.get("V7_PROJECT_NAME", "施工图审查项目"))
    
    print(f"生成报告完成:")
    for scene, path in results.items():
        print(f"  {scene}: {path}")


if __name__ == "__main__":
    main()