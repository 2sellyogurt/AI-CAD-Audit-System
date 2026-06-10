# -*- coding: utf-8 -*-
"""图层标注工具 - Web GUI

功能：
1. 扫描DXF文件，识别未识别的图层
2. 提供Web界面供用户人工标注
3. 标注结果保存到 learned_mappings.json
4. 支持批量标注和单个标注
5. 支持打开DXF图纸查看
6. 支持SVG图层预览

用法：
  python tools/layer_annotator.py --dxf "path/to/file.dxf" --port 8080
"""

import argparse
import json
import math
import os
import subprocess
import sys
import webbrowser
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.geometry_extractor import GeometryExtractor
from engine.layer_mapper import LayerMapper
from engine.dxf_renderer import DxfRenderer


DISCIPLINE_OPTIONS = [
    {"value": "建筑", "label": "建筑", "categories": ["墙", "柱", "门", "楼梯", "栏杆", "屋顶", "家具", "立面", "幕墙", "装饰", "吊顶", "地面", "降板", "防水", "挡烟", "消防分区", "总图", "标注", "轴线", "房间", "填充", "投影", "标识"]},
    {"value": "结构", "label": "结构", "categories": ["梁", "板", "柱", "基础", "钢筋", "钢结构", "标注"]},
    {"value": "给排水", "label": "给排水", "categories": ["给水", "排水", "消防", "雨水", "洁具", "管道标注"]},
    {"value": "暖通", "label": "暖通", "categories": ["风管", "风口", "水管", "设备", "标注"]},
    {"value": "电气", "label": "电气", "categories": ["桥架", "照明", "动力", "弱电", "烟感", "电梯", "标注"]},
    {"value": "通用", "label": "通用", "categories": ["图纸", "参照", "视口", "协同", "节点", "范围", "其他"]},
]


class AnnotationData:
    def __init__(self, dxf_path: str):
        self.dxf_path = os.path.abspath(dxf_path)
        self.dxf_dir = os.path.dirname(self.dxf_path)
        self.unknown_layers: List[Dict[str, Any]] = []
        self.all_components: List[Dict[str, Any]] = []
        self.learned_mappings: Dict[str, Dict[str, Any]] = {}
        self._load_existing_mappings()
        self._scan_dxf()

    def _load_existing_mappings(self):
        knowledge_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "layer_knowledge"
        )
        knowledge_file = os.path.join(knowledge_dir, "learned_mappings.json")
        if os.path.exists(knowledge_file):
            try:
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    self.learned_mappings = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.learned_mappings = {}

    def _save_mappings(self):
        knowledge_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "layer_knowledge"
        )
        os.makedirs(knowledge_dir, exist_ok=True)
        knowledge_file = os.path.join(knowledge_dir, "learned_mappings.json")
        try:
            with open(knowledge_file, "w", encoding="utf-8") as f:
                json.dump(self.learned_mappings, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[错误] 保存映射失败: {e}")

    def _scan_dxf(self):
        print(f"[扫描] 正在分析DXF文件: {self.dxf_path}")
        extractor = GeometryExtractor()
        result = extractor.extract_from_dxf(self.dxf_path)
        components = result.get("components", [])
        self.all_components = components

        mapper = LayerMapper(enable_intelligence=False)
        layer_counter: Counter = Counter()
        for comp in components:
            layer = comp.get("layer", "")
            layer_counter[layer] += 1

        unknown_layers = []
        for layer, count in layer_counter.most_common():
            if layer in self.learned_mappings:
                continue
            info = mapper.classify(layer)
            if info.get("discipline") == "未知":
                sample_components = [
                    c for c in components if c.get("layer", "") == layer
                ][:10]
                sample_types = list(set(c.get("type", "") for c in sample_components))
                unknown_layers.append({
                    "layer_name": layer,
                    "component_count": count,
                    "sample_types": sample_types,
                    "samples": sample_components,
                })

        self.unknown_layers = unknown_layers
        print(f"[扫描] 完成: {len(components)}个组件, {len(unknown_layers)}个未识别图层")

    def get_layer_svg(self, layer_name: str, width: int = 400, height: int = 300) -> str:
        layer_comps = [c for c in self.all_components if c.get("layer", "") == layer_name]
        if not layer_comps:
            return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"><text x="50%" y="50%" text-anchor="middle" fill="#999">无数据</text></svg>'

        all_points = []
        for comp in layer_comps:
            if "start_point" in comp:
                sp = comp["start_point"]
                if len(sp) >= 2:
                    all_points.append((sp[0], sp[1]))
            if "end_point" in comp:
                ep = comp["end_point"]
                if len(ep) >= 2:
                    all_points.append((ep[0], ep[1]))
            if "center" in comp:
                cp = comp["center"]
                if len(cp) >= 2:
                    all_points.append((cp[0], cp[1]))
            if "insert_point" in comp:
                ip = comp["insert_point"]
                if len(ip) >= 2:
                    all_points.append((ip[0], ip[1]))
            if "vertices" in comp:
                for v in comp["vertices"]:
                    if len(v) >= 2:
                        all_points.append((v[0], v[1]))

        if not all_points:
            return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"><text x="50%" y="50%" text-anchor="middle" fill="#999">无几何数据</text></svg>'

        min_x = min(p[0] for p in all_points)
        max_x = max(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)

        range_x = max_x - min_x if max_x > min_x else 1
        range_y = max_y - min_y if max_y > min_y else 1

        padding = 20
        scale_x = (width - 2 * padding) / range_x
        scale_y = (height - 2 * padding) / range_y
        scale = min(scale_x, scale_y)

        def transform(x: float, y: float) -> Tuple[float, float]:
            tx = padding + (x - min_x) * scale
            ty = height - padding - (y - min_y) * scale
            return (tx, ty)

        svg_elements = []
        for comp in layer_comps[:200]:
            comp_type = comp.get("type", "")
            if comp_type == "LINE" and "start_point" in comp and "end_point" in comp:
                sp = comp["start_point"]
                ep = comp["end_point"]
                if len(sp) >= 2 and len(ep) >= 2:
                    sx, sy = transform(sp[0], sp[1])
                    ex, ey = transform(ep[0], ep[1])
                    svg_elements.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#333" stroke-width="1"/>')
            elif comp_type == "CIRCLE" and "center" in comp and "radius" in comp:
                cp = comp["center"]
                r = comp["radius"]
                if len(cp) >= 2:
                    cx, cy = transform(cp[0], cp[1])
                    svg_elements.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r*scale:.1f}" fill="none" stroke="#333" stroke-width="1"/>')
            elif comp_type == "LWPOLYLINE" and "vertices" in comp:
                vertices = comp["vertices"]
                if len(vertices) >= 2:
                    points = []
                    for v in vertices:
                        if len(v) >= 2:
                            tx, ty = transform(v[0], v[1])
                            points.append(f"{tx:.1f},{ty:.1f}")
                    if points:
                        svg_elements.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#333" stroke-width="1"/>')

        svg_content = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:#fafafa;border:1px solid #ddd;border-radius:4px">'
        svg_content += ''.join(svg_elements)
        svg_content += '</svg>'
        return svg_content

    def annotate(self, layer_name: str, discipline: str, category: str) -> bool:
        if not layer_name or not discipline:
            return False
        self.learned_mappings[layer_name] = {
            "discipline": discipline,
            "category": category or "其他",
            "confidence": 0.9,
        }
        self._save_mappings()
        self.unknown_layers = [
            l for l in self.unknown_layers if l["layer_name"] != layer_name
        ]
        return True

    def batch_annotate(self, annotations: List[Dict[str, str]]) -> int:
        count = 0
        for ann in annotations:
            layer_name = ann.get("layer_name", "")
            discipline = ann.get("discipline", "")
            category = ann.get("category", "其他")
            if layer_name and discipline:
                self.learned_mappings[layer_name] = {
                    "discipline": discipline,
                    "category": category,
                    "confidence": 0.9,
                }
                count += 1
        if count > 0:
            self._save_mappings()
            annotated_names = {a["layer_name"] for a in annotations if a.get("discipline")}
            self.unknown_layers = [
                l for l in self.unknown_layers if l["layer_name"] not in annotated_names
            ]
        return count

    def get_layer_preview_base64(self, layer_name: str) -> str:
        renderer = DxfRenderer(width=800, height=600, bg_color="#1a1a2e", line_color="#e0e0e0", text_color="#4fc3f7")
        return renderer.render_to_base64(self.dxf_path, layer_filter=[layer_name])

    def get_full_preview_base64(self) -> str:
        renderer = DxfRenderer(width=1200, height=900, bg_color="#1a1a2e", line_color="#e0e0e0", text_color="#4fc3f7")
        return renderer.render_to_base64(self.dxf_path)

    def open_dxf_file(self) -> bool:
        try:
            if sys.platform == "win32":
                os.startfile(self.dxf_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.dxf_path])
            else:
                subprocess.Popen(["xdg-open", self.dxf_path])
            return True
        except Exception as e:
            print(f"[错误] 打开DXF文件失败: {e}")
            return False


annotation_data: AnnotationData = None


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI智能审图 - 图层标注工具</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; }
.header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 24px; margin-bottom: 5px; }
.header p { font-size: 14px; opacity: 0.8; }
.header-actions { display: flex; gap: 10px; }
.container { max-width: 1400px; margin: 20px auto; padding: 0 20px; }
.stats { display: flex; gap: 15px; margin-bottom: 20px; }
.stat-card { flex: 1; background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
.stat-card .number { font-size: 32px; font-weight: bold; color: #667eea; }
.stat-card .label { font-size: 14px; color: #666; margin-top: 5px; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px; }
.btn-primary { background: #667eea; color: white; }
.btn-primary:hover { background: #5a6fd6; }
.btn-success { background: #4caf50; color: white; }
.btn-success:hover { background: #43a047; }
.btn-warning { background: #ff9800; color: white; }
.btn-warning:hover { background: #f57c00; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-outline { background: transparent; border: 1px solid #667eea; color: #667eea; }
.btn-outline:hover { background: #667eea; color: white; }
.table-container { background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); overflow: hidden; }
.table-header { padding: 15px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
.table-header h2 { font-size: 18px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f8f9fa; font-weight: 600; color: #555; }
tr:hover { background: #f8f9fa; }
select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.badge-line { background: #e3f2fd; color: #1976d2; }
.badge-poly { background: #e8f5e9; color: #388e3c; }
.badge-circle { background: #fff3e0; color: #f57c00; }
.badge-insert { background: #f3e5f5; color: #7b1fa2; }
.badge-unknown { background: #fafafa; color: #999; }
.preview-cell { padding: 8px; }
.preview-cell svg { display: block; }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
.modal-content { background: white; width: 600px; max-width: 90%; margin: 50px auto; border-radius: 10px; padding: 25px; max-height: 80vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.modal-header h3 { font-size: 18px; }
.close { font-size: 24px; cursor: pointer; color: #999; }
.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
.form-group select, .form-group input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.form-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
.toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; color: white; font-size: 14px; z-index: 2000; animation: slideIn 0.3s ease; }
.toast-success { background: #4caf50; }
.toast-error { background: #f44336; }
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
.progress-bar { width: 100%; height: 8px; background: #eee; border-radius: 4px; overflow: hidden; margin-top: 10px; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); transition: width 0.3s; }
.layer-preview { margin: 15px 0; text-align: center; }
.layer-info { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 6px; }
.layer-info-item { font-size: 13px; }
.layer-info-item .label { color: #666; }
.layer-info-item .value { font-weight: 500; }
</style>
</head>
<body>
<div class="header">
    <div>
        <h1>🏗️ AI智能审图 - 图层标注工具</h1>
        <p>对系统未能识别的图层进行人工标注，提升构件识别率</p>
    </div>
    <div class="header-actions">
        <button class="btn btn-warning" onclick="openDxfFile()">📂 打开DXF图纸</button>
        <button class="btn btn-primary" onclick="showFullPreview()">🖼️ 查看完整图纸</button>
    </div>
</div>

<div class="container">
    <div class="stats">
        <div class="stat-card">
            <div class="number" id="totalLayers">0</div>
            <div class="label">未识别图层</div>
        </div>
        <div class="stat-card">
            <div class="number" id="annotatedCount">0</div>
            <div class="label">已标注</div>
        </div>
        <div class="stat-card">
            <div class="number" id="progressPercent">0%</div>
            <div class="label">完成进度</div>
            <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
        </div>
    </div>

    <div class="table-container">
        <div class="table-header">
            <h2>未识别图层列表</h2>
            <div>
                <button class="btn btn-primary" onclick="openBatchModal()">批量标注</button>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>
                    <th>图层名</th>
                    <th>组件数量</th>
                    <th>构件类型</th>
                    <th>图层预览</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody id="layerTable"></tbody>
        </table>
    </div>
</div>

<div class="modal" id="annotateModal">
    <div class="modal-content">
        <div class="modal-header">
            <h3>标注图层</h3>
            <span class="close" onclick="closeModal()">&times;</span>
        </div>
        <div class="layer-preview" id="modalPreview"></div>
        <div class="layer-info" id="modalInfo"></div>
        <div class="form-group">
            <label>图层名称</label>
            <input type="text" id="modalLayerName" readonly style="background:#f5f5f5">
        </div>
        <div class="form-group">
            <label>专业分类</label>
            <select id="modalDiscipline" onchange="updateCategories()">
                <option value="">请选择专业</option>
            </select>
        </div>
        <div class="form-group">
            <label>构件分类</label>
            <select id="modalCategory">
                <option value="">请选择分类</option>
            </select>
        </div>
        <div class="form-actions">
            <button class="btn btn-outline" onclick="closeModal()">取消</button>
            <button class="btn btn-success" onclick="submitAnnotation()">确认标注</button>
        </div>
    </div>
</div>

<div class="modal" id="batchModal">
    <div class="modal-content">
        <div class="modal-header">
            <h3>批量标注</h3>
            <span class="close" onclick="closeBatchModal()">&times;</span>
        </div>
        <div class="form-group">
            <label>已选中 <span id="batchCount">0</span> 个图层</label>
        </div>
        <div class="form-group">
            <label>专业分类</label>
            <select id="batchDiscipline" onchange="updateBatchCategories()">
                <option value="">请选择专业</option>
            </select>
        </div>
        <div class="form-group">
            <label>构件分类</label>
            <select id="batchCategory">
                <option value="">请选择分类</option>
            </select>
        </div>
        <div class="form-actions">
            <button class="btn btn-outline" onclick="closeBatchModal()">取消</button>
            <button class="btn btn-success" onclick="submitBatchAnnotation()">批量标注</button>
        </div>
    </div>
</div>

<div class="modal" id="fullPreviewModal">
    <div class="modal-content" style="width:90%;max-width:1400px">
        <div class="modal-header">
            <h3>📐 完整图纸预览</h3>
            <span class="close" onclick="closeFullPreview()">&times;</span>
        </div>
        <div style="text-align:center;overflow:auto;max-height:75vh">
            <img id="fullPreviewImg" src="" alt="加载中..." style="max-width:100%;border:1px solid #ddd;border-radius:4px">
        </div>
    </div>
</div>

<script>
let layers = [];
let disciplineOptions = DISCIPLINE_OPTIONS_PLACEHOLDER;

async function loadLayers() {
    const resp = await fetch('/api/layers');
    const data = await resp.json();
    layers = data.layers;
    renderTable();
    updateStats();
}

function renderTable() {
    const tbody = document.getElementById('layerTable');
    tbody.innerHTML = layers.map((l, i) => `
        <tr>
            <td><input type="checkbox" class="layer-check" value="${l.layer_name}" onchange="updateSelection()"></td>
            <td><strong>${l.layer_name}</strong></td>
            <td>${l.component_count.toLocaleString()}</td>
            <td>${l.sample_types.map(t => `<span class="badge badge-${t === 'LINE' ? 'line' : t === 'LWPOLYLINE' ? 'poly' : t === 'CIRCLE' ? 'circle' : t === 'INSERT' ? 'insert' : 'unknown'}">${t}</span>`).join(' ')}</td>
            <td class="preview-cell"><div id="preview-${i}" style="width:200px;height:80px;overflow:hidden;background:#fafafa;border:1px solid #eee;border-radius:4px"></div></td>
            <td>
                <button class="btn btn-primary btn-sm" onclick="openModal('${l.layer_name}', ${i})">标注</button>
            </td>
        </tr>
    `).join('');

    layers.forEach((l, i) => {
        loadPreview(l.layer_name, i);
    });
}

async function loadPreview(layerName, index) {
    try {
        const resp = await fetch('/api/layer_svg?layer=' + encodeURIComponent(layerName));
        const data = await resp.json();
        const container = document.getElementById(`preview-${index}`);
        if (container) {
            container.innerHTML = data.svg;
        }
    } catch (e) {
        console.error('加载预览失败:', e);
    }
}

function updateStats() {
    const total = layers.length;
    const annotated = parseInt(localStorage.getItem('annotatedCount') || '0');
    const percent = total > 0 ? Math.round(annotated / (total + annotated) * 100) : 0;
    document.getElementById('totalLayers').textContent = total;
    document.getElementById('annotatedCount').textContent = annotated;
    document.getElementById('progressPercent').textContent = percent + '%';
    document.getElementById('progressFill').style.width = percent + '%';
}

function populateDisciplines(selectId) {
    const select = document.getElementById(selectId);
    select.innerHTML = '<option value="">请选择专业</option>';
    disciplineOptions.forEach(d => {
        select.innerHTML += `<option value="${d.value}">${d.label}</option>`;
    });
}

function updateCategories() {
    const disc = document.getElementById('modalDiscipline').value;
    const catSelect = document.getElementById('modalCategory');
    catSelect.innerHTML = '<option value="">请选择分类</option>';
    const option = disciplineOptions.find(d => d.value === disc);
    if (option) {
        option.categories.forEach(c => {
            catSelect.innerHTML += `<option value="${c}">${c}</option>`;
        });
    }
}

function updateBatchCategories() {
    const disc = document.getElementById('batchDiscipline').value;
    const catSelect = document.getElementById('batchCategory');
    catSelect.innerHTML = '<option value="">请选择分类</option>';
    const option = disciplineOptions.find(d => d.value === disc);
    if (option) {
        option.categories.forEach(c => {
            catSelect.innerHTML += `<option value="${c}">${c}</option>`;
        });
    }
}

async function openModal(layerName, index) {
    document.getElementById('modalLayerName').value = layerName;
    document.getElementById('modalDiscipline').value = '';
    document.getElementById('modalCategory').innerHTML = '<option value="">请选择分类</option>';
    populateDisciplines('modalDiscipline');

    const layer = layers.find(l => l.layer_name === layerName);
    if (layer) {
        document.getElementById('modalInfo').innerHTML = `
            <div class="layer-info-item"><span class="label">图层名：</span><span class="value">${layer.layer_name}</span></div>
            <div class="layer-info-item"><span class="label">组件数量：</span><span class="value">${layer.component_count.toLocaleString()}</span></div>
            <div class="layer-info-item"><span class="label">构件类型：</span><span class="value">${layer.sample_types.join(', ')}</span></div>
            <div class="layer-info-item"><span class="label">DXF文件：</span><span class="value" style="word-break:break-all;font-size:11px">${decodeURIComponent("${encodeURIComponent(annotation_data.dxf_path)}")}</span></div>
        `;

        try {
            const resp = await fetch('/api/layer_preview?layer=' + encodeURIComponent(layerName));
            const data = await resp.json();
            if (data.base64) {
                document.getElementById('modalPreview').innerHTML = '<img src="data:image/png;base64,' + data.base64 + '" style="max-width:100%;border:1px solid #ddd;border-radius:4px">';
            } else {
                document.getElementById('modalPreview').innerHTML = '<p style="color:#999">预览加载失败</p>';
            }
        } catch (e) {
            document.getElementById('modalPreview').innerHTML = '<p style="color:#999">预览加载失败</p>';
        }
    }

    document.getElementById('annotateModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('annotateModal').style.display = 'none';
}

function openBatchModal() {
    const checked = document.querySelectorAll('.layer-check:checked');
    if (checked.length === 0) {
        showToast('请先选择要标注的图层', 'error');
        return;
    }
    document.getElementById('batchCount').textContent = checked.length;
    populateDisciplines('batchDiscipline');
    document.getElementById('batchCategory').innerHTML = '<option value="">请选择分类</option>';
    document.getElementById('batchModal').style.display = 'block';
}

function closeBatchModal() {
    document.getElementById('batchModal').style.display = 'none';
}

function toggleSelectAll() {
    const checked = document.getElementById('selectAll').checked;
    document.querySelectorAll('.layer-check').forEach(c => c.checked = checked);
}

function updateSelection() {
    const checked = document.querySelectorAll('.layer-check:checked');
}

async function openDxfFile() {
    try {
        const resp = await fetch('/api/open_dxf', { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            showToast('已打开DXF图纸', 'success');
        } else {
            showToast('打开失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        showToast('打开失败', 'error');
    }
}

async function showFullPreview() {
    document.getElementById('fullPreviewModal').style.display = 'block';
    document.getElementById('fullPreviewImg').src = '';
    document.getElementById('fullPreviewImg').alt = '正在加载...';
    try {
        const resp = await fetch('/api/full_preview');
        const data = await resp.json();
        if (data.base64) {
            document.getElementById('fullPreviewImg').src = 'data:image/png;base64,' + data.base64;
            document.getElementById('fullPreviewImg').alt = '完整图纸预览';
        } else {
            document.getElementById('fullPreviewImg').alt = '加载失败';
        }
    } catch (e) {
        document.getElementById('fullPreviewImg').alt = '加载失败: ' + e.message;
    }
}

function closeFullPreview() {
    document.getElementById('fullPreviewModal').style.display = 'none';
}

async function submitAnnotation() {
    const layerName = document.getElementById('modalLayerName').value;
    const discipline = document.getElementById('modalDiscipline').value;
    const category = document.getElementById('modalCategory').value;
    if (!discipline) {
        showToast('请选择专业分类', 'error');
        return;
    }
    const resp = await fetch('/api/annotate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({layer_name: layerName, discipline, category})
    });
    const data = await resp.json();
    if (data.success) {
        showToast('标注成功: ' + layerName, 'success');
        const prev = parseInt(localStorage.getItem('annotatedCount') || '0');
        localStorage.setItem('annotatedCount', prev + 1);
        closeModal();
        loadLayers();
    } else {
        showToast('标注失败', 'error');
    }
}

async function submitBatchAnnotation() {
    const discipline = document.getElementById('batchDiscipline').value;
    const category = document.getElementById('batchCategory').value;
    if (!discipline) {
        showToast('请选择专业分类', 'error');
        return;
    }
    const checked = document.querySelectorAll('.layer-check:checked');
    const annotations = Array.from(checked).map(c => ({
        layer_name: c.value, discipline, category
    }));
    const resp = await fetch('/api/batch_annotate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({annotations})
    });
    const data = await resp.json();
    if (data.success) {
        showToast(`批量标注成功: ${data.count}个图层`, 'success');
        const prev = parseInt(localStorage.getItem('annotatedCount') || '0');
        localStorage.setItem('annotatedCount', prev + data.count);
        closeBatchModal();
        loadLayers();
    } else {
        showToast('批量标注失败', 'error');
    }
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

loadLayers();
</script>
</body>
</html>"""


class AnnotationHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._serve_html()
        elif parsed.path == "/api/layers":
            self._serve_layers()
        elif parsed.path == "/api/layer_svg":
            self._serve_layer_svg(parsed)
        elif parsed.path == "/api/layer_preview":
            self._serve_layer_preview(parsed)
        elif parsed.path == "/api/full_preview":
            self._serve_full_preview()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/annotate":
            self._handle_annotate()
        elif parsed.path == "/api/batch_annotate":
            self._handle_batch_annotate()
        elif parsed.path == "/api/open_dxf":
            self._handle_open_dxf()
        else:
            self.send_error(404)

    def _serve_html(self):
        html = HTML_TEMPLATE.replace(
            "DISCIPLINE_OPTIONS_PLACEHOLDER",
            json.dumps(DISCIPLINE_OPTIONS, ensure_ascii=False)
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_layers(self):
        data = {
            "layers": annotation_data.unknown_layers,
            "total": len(annotation_data.unknown_layers),
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _serve_layer_svg(self, parsed):
        params = parse_qs(parsed.query)
        layer_name = params.get("layer", [""])[0]
        svg = annotation_data.get_layer_svg(layer_name)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"svg": svg}, ensure_ascii=False).encode("utf-8"))

    def _serve_layer_preview(self, parsed):
        params = parse_qs(parsed.query)
        layer_name = params.get("layer", [""])[0]
        b64 = annotation_data.get_layer_preview_base64(layer_name)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"base64": b64, "mime": "image/png"}, ensure_ascii=False).encode("utf-8"))

    def _serve_full_preview(self):
        b64 = annotation_data.get_full_preview_base64()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"base64": b64, "mime": "image/png"}, ensure_ascii=False).encode("utf-8"))

    def _handle_annotate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            success = annotation_data.annotate(
                data.get("layer_name", ""),
                data.get("discipline", ""),
                data.get("category", ""),
            )
            self._json_response({"success": success})
        except Exception as e:
            self._json_response({"success": False, "error": str(e)})

    def _handle_batch_annotate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            annotations = data.get("annotations", [])
            count = annotation_data.batch_annotate(annotations)
            self._json_response({"success": True, "count": count})
        except Exception as e:
            self._json_response({"success": False, "error": str(e)})

    def _handle_open_dxf(self):
        success = annotation_data.open_dxf_file()
        self._json_response({"success": success})

    def _json_response(self, data: Dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="图层标注工具 - Web GUI")
    parser.add_argument("--dxf", required=True, help="DXF文件路径")
    parser.add_argument("--port", type=int, default=8080, help="Web服务端口（默认8080）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    if not os.path.exists(args.dxf):
        print(f"[错误] DXF文件不存在: {args.dxf}")
        return 1

    global annotation_data
    annotation_data = AnnotationData(args.dxf)

    if not annotation_data.unknown_layers:
        print("[完成] 没有未识别的图层，无需标注")
        return 0

    server = HTTPServer(("0.0.0.0", args.port), AnnotationHandler)
    print(f"[启动] 图层标注工具已启动: http://localhost:{args.port}")
    print(f"[信息] DXF文件: {annotation_data.dxf_path}")
    print(f"[信息] 未识别图层: {len(annotation_data.unknown_layers)}个")
    print(f"[信息] 按 Ctrl+C 停止服务")

    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[停止] 图层标注工具已停止")
        server.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
