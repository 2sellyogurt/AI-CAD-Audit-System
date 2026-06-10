# -*- coding: utf-8 -*-
"""规则库数据清洗 + 建筑类型标注 + 索引生成

功能:
  1. 清洗: 移除字符串脏数据、统一字段格式、补全缺失字段、去重
  2. 标注: 按规范编号自动标注 applicable_building_types
  3. 索引: 生成 _index.json 总索引 + 按专业分索引

规则:
  - 修改前自动备份到 config/rules/backup/
  - 不修改 compliance_rules.json（由 ComplianceRuleEngine 独立管理）
  - 仅处理 config/rules/*.json 按专业拆分的规则库
"""
import json
import os
import re
import copy
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, 'config', 'rules')
BACKUP_DIR = os.path.join(RULES_DIR, 'backup')
INDEX_PATH = os.path.join(RULES_DIR, '_index.json')
MAIN_RULES_PATH = os.path.join(PROJECT_ROOT, 'config', 'rules.json')

DISCIPLINE_FILES = ['建筑.json', '结构.json', '给排水.json', '暖通.json', '电气.json', '消防.json', '通用.json']

BUILDING_TYPE_RULES = {
    '住宅': {
        'code_patterns': ['GB 50096', 'GB50096', 'GB 55038', 'GB55038'],
        'name_patterns': ['住宅卧室', '住宅层高', '住宅楼板', '住宅阳台', '住宅日照', '住宅采光', '住宅通风', '住宅噪声', '住宅隔声', '住宅设计'],
    },
    '中小学': {
        'code_patterns': ['GB 50099', 'GB50099'],
        'name_patterns': ['中小学校', '教学用房走道', '教学用房的门', '普通教室', '科学教室', '实验室的净高', '教学楼'],
    },
    '医院': {
        'code_patterns': ['GB 51039', 'GB51039', 'GB 50333', 'GB50333', 'GB 51011', 'GB51011'],
        'name_patterns': ['医院', '病房', '手术室', '诊室', '医疗', '卫生院'],
    },
    '商业': {
        'code_patterns': ['GB 50016-2014 第5.3.4', 'GB 50016-2014 第5.3.3'],
        'name_patterns': ['营业厅', '商铺', '超市', '商场'],
    },
    '办公': {
        'code_patterns': ['GB 50016-2014 第5.3.1'],
        'name_patterns': ['办公楼', '办公用房'],
    },
    '幼儿园': {
        'code_patterns': ['GB 50084', 'GB50084'],
        'name_patterns': ['幼儿园', '托儿所'],
    },
    '工业': {
        'code_patterns': ['GB 50016-2014 第3.1', 'GB 50016-2014 第3.2', 'GB 50016-2014 第3.3', 'GB 50016-2014 第3.4'],
        'name_patterns': ['厂房', '仓库', '工业建筑'],
    },
}

STANDARD_FIELDS = {
    'rule_id': '',
    'name': '',
    'discipline': '',
    'keywords': [],
    'check_type': 'any',
    'evidence_required': 2,
    'description': '',
    'is_mandatory': False,
    'code_reference': '',
    'code_version': 'GB',
    'status': '现行',
    'regex': '',
    'applicable_building_types': [],
}


def backup_file(fpath):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    basename = os.path.basename(fpath)
    backup_path = os.path.join(BACKUP_DIR, f'{basename}.{ts}.bak')
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return backup_path


def infer_building_type(rule):
    code_ref = rule.get('code_reference', '')
    name = rule.get('name', '')
    desc = rule.get('description', '')
    text = f'{code_ref} {name} {desc}'

    for bt, patterns in BUILDING_TYPE_RULES.items():
        for cp in patterns['code_patterns']:
            if cp in code_ref:
                return [bt]
        for np in patterns['name_patterns']:
            if np in name:
                return [bt]

    if '住宅' in name and ('卧室' in name or '阳台' in name or '层高' in name):
        return ['住宅']

    return []


def clean_rule(rule, discipline):
    if not isinstance(rule, dict):
        return None

    cleaned = {}
    for field, default in STANDARD_FIELDS.items():
        val = rule.get(field, default)
        if val is None:
            val = default
        cleaned[field] = val

    if not cleaned['discipline']:
        cleaned['discipline'] = discipline

    if not cleaned['rule_id']:
        return None

    if isinstance(cleaned['keywords'], str):
        cleaned['keywords'] = [cleaned['keywords']]

    if not cleaned['applicable_building_types']:
        bt = infer_building_type(cleaned)
        if bt:
            cleaned['applicable_building_types'] = bt

    for extra_key in ['check_type', 'evidence_required', 'code_version', 'status']:
        if extra_key in rule:
            cleaned[extra_key] = rule[extra_key]

    for key in rule:
        if key not in cleaned and key not in ('source',):
            cleaned[key] = rule[key]

    return cleaned


def process_discipline_file(fpath, discipline):
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    mandatory_raw = data.get('mandatory_rules', [])
    recommended_raw = data.get('recommended_rules', [])

    all_raw = mandatory_raw + recommended_raw
    str_count = sum(1 for r in all_raw if isinstance(r, str))

    cleaned_mandatory = []
    cleaned_recommended = []
    seen_ids = set()
    dup_count = 0

    for rule in mandatory_raw:
        c = clean_rule(rule, discipline)
        if c is None:
            continue
        if c['rule_id'] in seen_ids:
            dup_count += 1
            continue
        seen_ids.add(c['rule_id'])
        c['is_mandatory'] = True
        cleaned_mandatory.append(c)

    for rule in recommended_raw:
        c = clean_rule(rule, discipline)
        if c is None:
            continue
        if c['rule_id'] in seen_ids:
            dup_count += 1
            continue
        seen_ids.add(c['rule_id'])
        c['is_mandatory'] = False
        cleaned_recommended.append(c)

    data['mandatory_rules'] = cleaned_mandatory
    data['recommended_rules'] = cleaned_recommended
    data['rule_count'] = len(cleaned_mandatory) + len(cleaned_recommended)
    data['last_cleaned'] = datetime.now().isoformat()

    return data, {
        'str_removed': str_count,
        'dup_removed': dup_count,
        'final_count': len(cleaned_mandatory) + len(cleaned_recommended),
        'mandatory_count': len(cleaned_mandatory),
        'bt_annotated': sum(1 for r in cleaned_mandatory + cleaned_recommended if r.get('applicable_building_types')),
    }


def generate_index(all_data):
    index = {
        'version': '2.0.0',
        'generated_at': datetime.now().isoformat(),
        'total_rules': 0,
        'disciplines': {},
        'building_type_stats': defaultdict(int),
        'mandatory_stats': defaultdict(int),
        'code_reference_index': defaultdict(list),
    }

    for disc, data in all_data.items():
        mandatory = data.get('mandatory_rules', [])
        recommended = data.get('recommended_rules', [])
        all_rules = mandatory + recommended
        count = len(all_rules)
        index['total_rules'] += count
        index['disciplines'][disc] = {
            'file': f'{disc}.json',
            'rule_count': count,
            'mandatory_count': len(mandatory),
            'recommended_count': len(recommended),
        }
        index['mandatory_stats'][disc] = len(mandatory)

        for r in all_rules:
            bts = r.get('applicable_building_types', [])
            if not bts:
                index['building_type_stats']['通用'] += 1
            else:
                for bt in bts:
                    index['building_type_stats'][bt] += 1

            code_ref = r.get('code_reference', '')
            if code_ref:
                std_match = re.match(r'(GB\s+\d+[\-\d]*)', code_ref)
                if std_match:
                    std_num = std_match.group(1).strip()
                    index['code_reference_index'][std_num].append(r['rule_id'])

    index['building_type_stats'] = dict(index['building_type_stats'])
    index['code_reference_index'] = {k: v for k, v in sorted(index['code_reference_index'].items())}

    return index


def main():
    print('=' * 80)
    print('规则库数据清洗 + 建筑类型标注 + 索引生成')
    print('=' * 80)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    all_data = {}
    total_stats = {'str_removed': 0, 'dup_removed': 0, 'bt_annotated': 0, 'final_count': 0}

    for fname in DISCIPLINE_FILES:
        fpath = os.path.join(RULES_DIR, fname)
        if not os.path.exists(fpath):
            print(f'\n{fname}: 文件不存在，跳过')
            continue

        discipline = fname.replace('.json', '')
        backup_path = backup_file(fpath)
        print(f'\n【{fname}】备份 -> {os.path.basename(backup_path)}')

        cleaned_data, stats = process_discipline_file(fpath, discipline)
        all_data[discipline] = cleaned_data

        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

        print(f'  清洗: 移除字符串{stats["str_removed"]}条, 去重{stats["dup_removed"]}条')
        print(f'  结果: {stats["final_count"]}条(强条:{stats["mandatory_count"]})')
        print(f'  标注: {stats["bt_annotated"]}条有building_type')

        for k in total_stats:
            total_stats[k] += stats[k]

    print(f'\n{"=" * 80}')
    print(f'清洗汇总:')
    print(f'  移除字符串脏数据: {total_stats["str_removed"]}条')
    print(f'  去重: {total_stats["dup_removed"]}条')
    print(f'  最终规则数: {total_stats["final_count"]}条')
    print(f'  building_type已标注: {total_stats["bt_annotated"]}条')

    print(f'\n生成索引文件...')
    index = generate_index(all_data)
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f'  索引已写入: {INDEX_PATH}')
    print(f'  总规则数: {index["total_rules"]}')
    print(f'  建筑类型分布: {index["building_type_stats"]}')

    if os.path.exists(MAIN_RULES_PATH):
        print(f'\n同步主rules.json的building_type...')
        with open(MAIN_RULES_PATH, 'r', encoding='utf-8') as f:
            main_data = json.load(f)
        backup_file(MAIN_RULES_PATH)

        bt_map = {}
        for disc_data in all_data.values():
            for r in disc_data.get('mandatory_rules', []) + disc_data.get('recommended_rules', []):
                rid = r.get('rule_id', '')
                bts = r.get('applicable_building_types', [])
                if rid and bts:
                    bt_map[rid] = bts

        updated = 0
        for section in ['mandatory_rules', 'recommended_rules']:
            for r in main_data.get(section, []):
                if isinstance(r, dict) and not r.get('applicable_building_types'):
                    rid = r.get('rule_id', '')
                    if rid in bt_map:
                        r['applicable_building_types'] = bt_map[rid]
                        updated += 1

        with open(MAIN_RULES_PATH, 'w', encoding='utf-8') as f:
            json.dump(main_data, f, ensure_ascii=False, indent=2)
        print(f'  主rules.json更新了{updated}条building_type')

    print(f'\n{"=" * 80}')
    print('完成！')


if __name__ == '__main__':
    main()
