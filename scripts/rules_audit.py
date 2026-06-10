# -*- coding: utf-8 -*-
"""规则库数据摸底报告 - 正确解析嵌套结构"""
import json, os

config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
rules_dir = os.path.join(config_dir, 'rules')

print('=' * 80)
print('规则库数据摸底报告')
print('=' * 80)

total = 0
all_rules_map = {}

files = ['建筑.json', '结构.json', '给排水.json', '暖通.json', '电气.json', '消防.json', '通用.json']
for fname in files:
    fpath = os.path.join(rules_dir, fname)
    if not os.path.exists(fpath):
        print(f'\n{fname}: 文件不存在')
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    discipline = data.get('discipline', fname.replace('.json', ''))
    mandatory = data.get('mandatory_rules', [])
    recommended = data.get('recommended_rules', [])
    all_r = mandatory + recommended
    n = len(all_r)
    total += n

    str_count = sum(1 for r in all_r if isinstance(r, str))
    dict_rules = [r for r in all_r if isinstance(r, dict)]
    dn = len(dict_rules)

    has_bt = sum(1 for r in dict_rules if r.get('applicable_building_types'))
    has_mandatory = sum(1 for r in dict_rules if 'is_mandatory' in r)
    has_code = sum(1 for r in dict_rules if r.get('code_reference'))
    has_kw = sum(1 for r in dict_rules if r.get('keywords'))
    has_regex = sum(1 for r in dict_rules if r.get('regex'))
    has_id = sum(1 for r in dict_rules if r.get('rule_id'))

    gb96 = [r for r in dict_rules if '50096' in r.get('code_reference', '')]
    gb99 = [r for r in dict_rules if '50099' in r.get('code_reference', '')]

    ids = [r.get('rule_id', '') for r in dict_rules]
    dup_ids = [x for x in set(ids) if ids.count(x) > 1 and x]

    missing_fields = []
    for r in dict_rules:
        if not r.get('rule_id'):
            missing_fields.append('rule_id')
        if not r.get('discipline'):
            missing_fields.append('discipline')
        if not r.get('code_reference'):
            missing_fields.append('code_reference')
        if not r.get('keywords'):
            missing_fields.append('keywords')
        break

    print(f'\n【{fname}】{discipline}专业 共{n}条(强条:{len(mandatory)}, 推荐:{len(recommended)})')
    if str_count > 0:
        print(f'  ⚠ 字符串脏数据: {str_count}条')
    print(f'  字段完整性: rule_id={has_id}/{dn}  code_ref={has_code}/{dn}  keywords={has_kw}/{dn}  regex={has_regex}/{dn}')
    print(f'  building_type标注: {has_bt}/{dn}')
    if gb96:
        bt96 = sum(1 for r in gb96 if r.get('applicable_building_types'))
        print(f'  GB50096(住宅): {len(gb96)}条, 有building_type: {bt96}')
    if gb99:
        bt99 = sum(1 for r in gb99 if r.get('applicable_building_types'))
        print(f'  GB50099(中小学): {len(gb99)}条, 有building_type: {bt99}')
    if dup_ids:
        print(f'  ⚠ 重复rule_id: {dup_ids[:5]}')

    for r in dict_rules:
        rid = r.get('rule_id', '')
        if rid:
            all_rules_map[rid] = r

# 主rules.json
main_path = os.path.join(config_dir, 'rules.json')
if os.path.exists(main_path):
    with open(main_path, 'r', encoding='utf-8') as f:
        main_data = json.load(f)
    main_mandatory = main_data.get('mandatory_rules', [])
    main_recommended = main_data.get('recommended_rules', [])
    main_all = main_mandatory + main_recommended
    mn = len(main_all)
    dict_main = [r for r in main_all if isinstance(r, dict)]
    has_bt = sum(1 for r in dict_main if r.get('applicable_building_types'))
    print(f'\n【rules.json(主)】共{mn}条, 有building_type: {has_bt}/{len(dict_main)}')

# compliance_rules.json
comp_path = os.path.join(config_dir, 'compliance_rules.json')
if os.path.exists(comp_path):
    with open(comp_path, 'r', encoding='utf-8') as f:
        comp_data = json.load(f)
    comp_rules = comp_data.get('rules', [])
    cn = len(comp_rules)
    dict_comp = [r for r in comp_rules if isinstance(r, dict)]
    has_bt = sum(1 for r in dict_comp if r.get('applicable_building_types'))
    print(f'\n【compliance_rules.json】共{cn}条, 有building_type: {has_bt}/{len(dict_comp)}')

print(f'\n{"=" * 80}')
print(f'总计: {total}条规则(按专业拆分), 去重后唯一rule_id: {len(all_rules_map)}条')

# 输出需要标注building_type的规范
print('\n' + '=' * 80)
print('需要标注building_type的规范:')
bt_needed = {}
for rid, r in all_rules_map.items():
    code = r.get('code_reference', '')
    if not code:
        continue
    if '50096' in code or '住宅' in r.get('name', ''):
        bt_needed.setdefault('住宅', []).append(rid)
    elif '50099' in code or '中小学校' in r.get('name', ''):
        bt_needed.setdefault('中小学', []).append(rid)
    elif '50099' in code or '教学用房' in r.get('name', ''):
        bt_needed.setdefault('中小学', []).append(rid)

for bt, rids in bt_needed.items():
    print(f'  {bt}: {len(rids)}条 -> {rids[:5]}...')
