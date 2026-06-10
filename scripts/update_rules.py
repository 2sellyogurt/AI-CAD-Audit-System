# -*- coding: utf-8 -*-
"""
规则库更新脚本 - 将提取的规范条文更新到项目的规则库中

功能：
1. 读取提取的规范条文
2. 过滤掉不是真正规范条文的规则
3. 按专业分类
4. 更新到对应的规则文件中
5. 更新规则索引
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil


class RuleUpdater:
    """规则库更新器"""
    
    def __init__(self, extracted_rules_path: str, rules_dir: str):
        """
        初始化更新器
        
        Args:
            extracted_rules_path: 提取的规则文件路径
            rules_dir: 规则库目录
        """
        self.extracted_rules_path = Path(extracted_rules_path)
        self.rules_dir = Path(rules_dir)
        
    def load_extracted_rules(self) -> List[Dict[str, Any]]:
        """
        加载提取的规则
        
        Returns:
            规则列表
        """
        try:
            with open(self.extracted_rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            return rules
        except Exception as e:
            print(f"加载提取的规则时出错: {e}")
            return []
    
    def filter_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤规则，移除不是真正规范条文的规则
        
        Args:
            rules: 原始规则列表
            
        Returns:
            过滤后的规则列表
        """
        filtered_rules = []
        
        # 需要过滤的模式
        filter_patterns = [
            r'^公司',  # 公司名称
            r'^目录',  # 目录
            r'^第[一二三四五六七八九十百千]+章',  # 章节标题
            r'^第[一二三四五六七八九十百千]+节',  # 节标题
            r'^附录',  # 附录
            r'^参考文献',  # 参考文献
            r'^索引',  # 索引
            r'^封面',  # 封面
            r'^前言',  # 前言
            r'^后记',  # 后记
            r'^致谢',  # 致谢
        ]
        
        # 需要保留的关键词
        keep_keywords = [
            '条', '款', '项', '规定', '要求', '标准', '规范', '细则',
            '应', '不应', '不得', '必须', '严禁', '宜', '不宜',
            '可', '可以', '不应', '不得', '禁止', '允许',
            '检查', '检验', '验收', '测试', '检测',
            '安装', '施工', '建造', '建设', '工程',
            '设计', '规划', '方案', '图纸',
            '质量', '安全', '环保', '消防', '节能',
            '材料', '设备', '构件', '部件',
            '尺寸', '规格', '参数', '指标',
            '温度', '湿度', '压力', '强度',
            '高度', '宽度', '长度', '面积', '体积',
            '间距', '距离', '净距', '净高',
            '防水', '防潮', '防火', '防雷', '防爆',
            '通风', '采光', '照明', '采暖',
            '给水', '排水', '供暖', '供气',
            '电气', '电力', '配电', '照明',
            '消防', '灭火', '报警', '疏散',
            '结构', '基础', '地基', '桩基',
            '混凝土', '钢筋', '钢材', '木材',
            '砌体', '砌筑', '抹灰', '装饰',
            '门窗', '幕墙', '屋面', '地面',
            '地下', '地上', '屋顶', '墙体',
        ]
        
        for rule in rules:
            title = rule.get('name', '')
            content = rule.get('description', '')
            
            # 检查是否需要过滤
            should_filter = False
            for pattern in filter_patterns:
                if re.match(pattern, title):
                    should_filter = True
                    break
            
            if should_filter:
                continue
            
            # 检查是否包含保留关键词
            has_keep_keyword = False
            for keyword in keep_keywords:
                if keyword in title or keyword in content:
                    has_keep_keyword = True
                    break
            
            # 如果没有保留关键词，但内容较长，也保留
            if not has_keep_keyword and len(content) < 50:
                continue
            
            # 过滤掉内容太短的规则
            if len(content) < 20:
                continue
            
            filtered_rules.append(rule)
        
        return filtered_rules
    
    def categorize_rules(self, rules: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        将规则按专业分类
        
        Args:
            rules: 规则列表
            
        Returns:
            按专业分类的规则字典
        """
        categorized = {
            '建筑': [],
            '结构': [],
            '暖通': [],
            '给排水': [],
            '电气': [],
            '消防': [],
            '通用': []
        }
        
        # 专业关键词映射
        discipline_keywords = {
            '建筑': ['建筑', '房屋', '住宅', '民用', '公共', '商业', '办公', '学校', '医院', '酒店'],
            '结构': ['结构', '混凝土', '钢筋', '基础', '地基', '桩基', '框架', '剪力墙', '钢结构'],
            '暖通': ['暖通', '通风', '空调', '供暖', '采暖', '制冷', '暖气', '散热器', '风机盘管'],
            '给排水': ['给排水', '给水', '排水', '管道', '水暖', '水泵', '水箱', '阀门', '水表'],
            '电气': ['电气', '电力', '配电', '照明', '弱电', '强电', '电缆', '电线', '开关', '插座'],
            '消防': ['消防', '防火', '灭火', '疏散', '报警', '喷淋', '消火栓', '灭火器', '防火门'],
            '安全': ['安全', '施工安全', '职业安全', '安全生产', '安全防护', '安全设施'],
            '质量': ['质量', '验收', '检验', '检测', '质量管理', '质量控制'],
            '监理': ['监理', '监督', '检查', '监理规范', '监理细则']
        }
        
        for rule in rules:
            title = rule.get('name', '')
            content = rule.get('description', '')
            category = rule.get('source', {}).get('category', '通用')
            
            # 根据内容判断专业
            discipline = '通用'
            max_score = 0
            
            for disc, keywords in discipline_keywords.items():
                score = 0
                for keyword in keywords:
                    if keyword in title:
                        score += 3
                    if keyword in content:
                        score += 1
                
                if score > max_score:
                    max_score = score
                    discipline = disc
            
            # 如果得分太低，使用默认分类
            if max_score < 2:
                discipline = category if category in categorized else '通用'
            
            # 更新规则的专业字段
            rule['discipline'] = discipline
            
            # 添加到对应的分类中
            if discipline in categorized:
                categorized[discipline].append(rule)
            else:
                categorized['通用'].append(rule)
        
        return categorized
    
    def load_existing_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        加载现有的规则库
        
        Returns:
            按专业分类的现有规则字典
        """
        existing_rules = {}
        
        # 读取规则索引
        index_path = self.rules_dir / '_index.json'
        if index_path.exists():
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
            
            # 读取每个专业的规则文件
            for discipline, info in index.get('disciplines', {}).items():
                rule_file = self.rules_dir / info['file']
                if rule_file.exists():
                    with open(rule_file, 'r', encoding='utf-8') as f:
                        rule_data = json.load(f)
                        existing_rules[discipline] = rule_data.get('mandatory_rules', [])
        
        return existing_rules
    
    def merge_rules(self, existing_rules: Dict[str, List[Dict[str, Any]]], 
                   new_rules: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        合并现有规则和新规则
        
        Args:
            existing_rules: 现有规则
            new_rules: 新规则
            
        Returns:
            合并后的规则
        """
        merged_rules = {}
        
        # 合并所有专业的规则
        all_disciplines = set(list(existing_rules.keys()) + list(new_rules.keys()))
        
        for discipline in all_disciplines:
            existing = existing_rules.get(discipline, [])
            new = new_rules.get(discipline, [])
            
            # 创建现有规则的ID集合，用于去重
            existing_ids = {rule.get('rule_id') for rule in existing}
            
            # 合并规则，避免重复
            merged = existing.copy()
            for rule in new:
                if rule.get('rule_id') not in existing_ids:
                    merged.append(rule)
                    existing_ids.add(rule.get('rule_id'))
            
            merged_rules[discipline] = merged
        
        return merged_rules
    
    def update_rule_files(self, merged_rules: Dict[str, List[Dict[str, Any]]]):
        """
        更新规则文件
        
        Args:
            merged_rules: 合并后的规则
        """
        # 备份现有规则文件
        backup_dir = self.rules_dir / 'backup'
        backup_dir.mkdir(exist_ok=True)
        
        # 备份所有规则文件
        for rule_file in self.rules_dir.glob('*.json'):
            if rule_file.name != '_index.json':
                backup_path = backup_dir / f"{rule_file.stem}_backup.json"
                shutil.copy2(rule_file, backup_path)
                print(f"已备份规则文件: {rule_file.name} -> {backup_path.name}")
        
        # 更新每个专业的规则文件
        for discipline, rules in merged_rules.items():
            rule_file = self.rules_dir / f"{discipline}.json"
            
            # 读取现有文件结构
            if rule_file.exists():
                with open(rule_file, 'r', encoding='utf-8') as f:
                    rule_data = json.load(f)
            else:
                rule_data = {
                    "discipline": discipline,
                    "rule_count": 0,
                    "mandatory_rules": []
                }
            
            # 更新规则数据
            rule_data['mandatory_rules'] = rules
            rule_data['rule_count'] = len(rules)
            
            # 保存更新后的规则文件
            with open(rule_file, 'w', encoding='utf-8') as f:
                json.dump(rule_data, f, ensure_ascii=False, indent=2)
            
            print(f"已更新规则文件: {rule_file.name} ({len(rules)} 条规则)")
    
    def update_rule_index(self, merged_rules: Dict[str, List[Dict[str, Any]]]):
        """
        更新规则索引
        
        Args:
            merged_rules: 合并后的规则
        """
        index_path = self.rules_dir / '_index.json'
        
        # 读取现有索引
        if index_path.exists():
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
        else:
            index = {
                "version": "7.0.0",
                "description": "规则库索引，按专业拆分",
                "total_rules": 0,
                "disciplines": {}
            }
        
        # 更新索引信息
        total_rules = 0
        for discipline, rules in merged_rules.items():
            rule_count = len(rules)
            total_rules += rule_count
            
            # 更新专业信息
            index['disciplines'][discipline] = {
                "file": f"{discipline}.json",
                "rule_count": rule_count
            }
        
        index['total_rules'] = total_rules
        
        # 保存更新后的索引
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        print(f"已更新规则索引: {index_path.name} (总计 {total_rules} 条规则)")
    
    def update_rules(self) -> Dict[str, Any]:
        """
        更新规则库
        
        Returns:
            更新结果统计
        """
        print("开始更新规则库...")
        
        # 加载提取的规则
        extracted_rules = self.load_extracted_rules()
        print(f"已加载 {len(extracted_rules)} 条提取的规则")
        
        # 过滤规则
        filtered_rules = self.filter_rules(extracted_rules)
        print(f"过滤后剩余 {len(filtered_rules)} 条规则")
        
        # 分类规则
        categorized_rules = self.categorize_rules(filtered_rules)
        for discipline, rules in categorized_rules.items():
            print(f"  {discipline}: {len(rules)} 条规则")
        
        # 加载现有规则
        existing_rules = self.load_existing_rules()
        print(f"已加载现有规则库")
        
        # 合并规则
        merged_rules = self.merge_rules(existing_rules, categorized_rules)
        
        # 更新规则文件
        self.update_rule_files(merged_rules)
        
        # 更新规则索引
        self.update_rule_index(merged_rules)
        
        # 统计结果
        total_new = sum(len(rules) for rules in categorized_rules.values())
        total_merged = sum(len(rules) for rules in merged_rules.values())
        
        return {
            "extracted_rules": len(extracted_rules),
            "filtered_rules": len(filtered_rules),
            "new_rules": total_new,
            "total_rules": total_merged,
            "disciplines": {discipline: len(rules) for discipline, rules in categorized_rules.items()}
        }


def main():
    """主函数"""
    extracted_rules_path = r"F:\AI智能审图系统_v6.0_项目开发\output\norms\extracted_rules.json"
    rules_dir = r"F:\AI智能审图系统_v6.0_项目开发\config\rules"
    
    updater = RuleUpdater(extracted_rules_path, rules_dir)
    result = updater.update_rules()
    
    print("\n更新完成:")
    print(f"  提取的规则数: {result['extracted_rules']}")
    print(f"  过滤后的规则数: {result['filtered_rules']}")
    print(f"  新增规则数: {result['new_rules']}")
    print(f"  总规则数: {result['total_rules']}")
    
    print("\n各专业规则数:")
    for discipline, count in result['disciplines'].items():
        print(f"  {discipline}: {count}")


if __name__ == '__main__':
    main()