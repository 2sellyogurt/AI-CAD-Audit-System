# -*- coding: utf-8 -*-
"""验证报告真实性 - 递归提取BLOCK内文字"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ezdxf

dxf_dir = r'C:\Users\azyp\Desktop\医科大图纸DXF'

def extract_all_texts(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    texts = []
    
    def extract_from_entity(e):
        dtype = e.dxftype()
        if dtype in ('TEXT', 'MTEXT'):
            txt = e.dxf.text if dtype == 'TEXT' else e.text
            if txt:
                txt = txt.replace('\\P', '\n').replace('\\A1;', '')
                for line in txt.split('\n'):
                    line = line.strip()
                    if line and len(line) > 1:
                        texts.append(line)
        elif dtype == 'ATTRIB':
            txt = e.dxf.text
            if txt and len(txt.strip()) > 1:
                texts.append(txt.strip())
    
    for e in msp:
        extract_from_entity(e)
        if e.dxftype() == 'INSERT':
            try:
                block = doc.blocks.get(e.dxf.name)
                if block:
                    for be in block:
                        extract_from_entity(be)
            except:
                pass
    
    return texts

def search_in_texts(texts, keywords):
    found = []
    for t in texts:
        for kw in keywords:
            if kw in t:
                found.append(t)
                break
    return found

print("=" * 80)
print("DXF图纸数据验证（含BLOCK递归提取）")
print("=" * 80)

files_to_check = [
    ('建筑-教学实验楼', '02-1教学实验楼平顶地面图_113330.dxf', {
        '窗台': ['窗台', 'CQ'],
        '楼梯/踏步': ['楼梯', '踏步', 'LT'],
        '走道': ['走道', '走廊', '通道'],
        '栏杆': ['栏杆', '栏板', '护栏', '扶手'],
        '女儿墙': ['女儿墙'],
        '教室': ['教室', '实验室'],
        '无障碍/坡道': ['无障碍', '盲道', '坡道'],
        '防水': ['防水', '防潮'],
        '净高': ['净高', '层高'],
        '采光': ['采光', '窗地比'],
    }),
    ('给排水-教学实验楼', '水施-教学实验楼_111990.dxf', {
        '消火栓': ['消火栓', 'XHS'],
        '喷淋/喷头': ['喷淋', '喷头', '喷洒'],
        '消防': ['消防'],
        '给水': ['给水', 'GS'],
        '排水': ['排水', 'PS', '污水'],
        '阀门': ['阀门', '阀'],
        '管径DN': ['DN', '管径'],
        '套管': ['套管'],
    }),
    ('电气-教学实验楼', '电气-温医大123号教学实验楼平面图20251111.dxf', {
        '配电箱': ['配电箱', 'PDX', '配电'],
        '照明/灯具': ['照明', '灯具', '灯'],
        '应急照明': ['应急', '疏散指示', '安全出口'],
        '火灾报警': ['报警', '探测器', '烟感', '温感'],
        '防雷/接地': ['防雷', '接地', '引下线'],
        '桥架': ['桥架', '线槽'],
        '线缆': ['mm²', '截面', 'BV', 'YJV'],
    }),
    ('结构-教学实验楼', '温医大教学实验楼结构施工图.dxf', {
        '箍筋': ['箍筋', 'φ', 'Φ', '加密'],
        '配筋/钢筋': ['配筋', '钢筋', '纵筋', '受力'],
        '混凝土强度': ['C20', 'C25', 'C30', 'C35', 'C40'],
        '框架柱': ['框架柱', 'KZ', '柱截面'],
        '框架梁': ['框架梁', 'KL', 'KL(', '梁截面'],
        '保护层': ['保护层'],
        '基础': ['基础', '独立基础'],
        '楼板/板厚': ['楼板', '板厚', '现浇', '叠合'],
        '层高/标高': ['层高', '标高'],
        '抗震': ['抗震', '设防'],
    }),
    ('建筑总说明', '温医大阿尔伯塔学院建筑总说明_t3.dxf', {
        '窗台': ['窗台'],
        '楼梯': ['楼梯', '踏步'],
        '栏杆': ['栏杆', '扶手'],
        '无障碍': ['无障碍', '坡道'],
        '防水': ['防水'],
        '节能': ['节能', '保温'],
        '消防': ['消防', '防火'],
    }),
    ('结构总说明', '0结构设计说明20251114.dxf', {
        '箍筋': ['箍筋', 'φ', 'Φ'],
        '混凝土': ['C20', 'C25', 'C30', 'C35'],
        '抗震': ['抗震', '设防烈度'],
        '钢筋': ['钢筋', 'HRB', 'HPB'],
        '保护层': ['保护层'],
        '基础': ['基础'],
    }),
    ('给排水总图', 'SS-01给排水布置总平面图_t3_t3_t3.dxf', {
        '消火栓': ['消火栓'],
        '喷淋': ['喷淋', '喷头'],
        '消防': ['消防'],
        '给水': ['给水'],
        '排水': ['排水'],
        '化粪池': ['化粪池'],
    }),
    ('电气总说明', '电气总设计说明_t3.dxf', {
        '配电': ['配电'],
        '防雷': ['防雷'],
        '接地': ['接地'],
        '线缆': ['线缆', '电缆', '截面'],
        '火灾报警': ['报警', '探测器'],
        '应急照明': ['应急', '疏散'],
    }),
]

for label, fname, kw_dict in files_to_check:
    fpath = os.path.join(dxf_dir, fname)
    print(f"\n{'─' * 60}")
    print(f"【{label}】{fname}")
    if not os.path.exists(fpath):
        print("  文件不存在!")
        continue
    texts = extract_all_texts(fpath)
    print(f"  提取文字总数: {len(texts)}")
    
    for kw_label, keywords in kw_dict.items():
        results = search_in_texts(texts, keywords)
        if results:
            unique = list(dict.fromkeys(results))[:5]
            print(f"  ✓ {kw_label}: {unique}")
        else:
            print(f"  ✗ {kw_label}: 未找到")

print(f"\n{'=' * 80}")
print("验证完成")
