# -*- coding: utf-8 -*-
"""
规范条文提取脚本 - 从Word文档中提取建筑监理规范条文

功能：
1. 读取指定目录下的所有.doc/.docx文件
2. 提取规范条文内容
3. 清理格式和编码问题
4. 结构化为JSON格式
5. 更新到项目的规则库中
"""

import os
import re
import json
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import win32com.client
import pythoncom


class NormExtractor:
    """规范条文提取器"""
    
    def __init__(self, source_dir: str, output_dir: str):
        """
        初始化提取器
        
        Args:
            source_dir: 源文件目录
            output_dir: 输出目录
        """
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def convert_doc_to_docx(self, doc_path: Path) -> Optional[Path]:
        """
        将.doc文件转换为.docx文件
        
        Args:
            doc_path: .doc文件路径
            
        Returns:
            转换后的.docx文件路径，如果转换失败则返回None
        """
        try:
            # 初始化COM组件
            pythoncom.CoInitialize()
            
            # 创建Word应用程序对象
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            
            # 打开.doc文件
            doc = word.Documents.Open(str(doc_path))
            
            # 创建临时文件路径
            temp_dir = Path(tempfile.gettempdir())
            docx_path = temp_dir / f"{doc_path.stem}.docx"
            
            # 另存为.docx格式
            doc.SaveAs2(str(docx_path), FileFormat=16)  # 16表示docx格式
            
            # 关闭文档和Word应用程序
            doc.Close()
            word.Quit()
            
            return docx_path
            
        except Exception as e:
            print(f"转换文件 {doc_path} 时出错: {e}")
            return None
        finally:
            # 释放COM组件
            pythoncom.CoUninitialize()
    
    def extract_from_docx(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        从docx文件中提取规范条文
        
        Args:
            file_path: docx文件路径
            
        Returns:
            提取的规范条文列表
        """
        try:
            doc = Document(file_path)
            norms = []
            
            current_norm = None
            current_content = []
            
            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if not text:
                    continue
                
                # 检测是否是新的规范条文（通常以数字开头或包含"条"、"款"等关键词）
                if self._is_new_norm_start(text):
                    # 保存之前的规范条文
                    if current_norm and current_content:
                        current_norm['content'] = '\n'.join(current_content)
                        norms.append(current_norm)
                    
                    # 开始新的规范条文
                    current_norm = {
                        'source_file': file_path.name,
                        'title': text,
                        'content': '',
                        'category': self._extract_category(text),
                        'keywords': self._extract_keywords(text)
                    }
                    current_content = []
                elif current_norm:
                    current_content.append(text)
            
            # 保存最后一个规范条文
            if current_norm and current_content:
                current_norm['content'] = '\n'.join(current_content)
                norms.append(current_norm)
            
            return norms
            
        except Exception as e:
            print(f"读取文件 {file_path} 时出错: {e}")
            return []
    
    def _is_new_norm_start(self, text: str) -> bool:
        """
        判断是否是新规范条文的开始
        
        Args:
            text: 文本内容
            
        Returns:
            是否是新规范条文的开始
        """
        # 检测模式：数字开头、包含"条"、"款"、"第"等关键词
        patterns = [
            r'^\d+[\.\、]',  # 数字开头
            r'^第[一二三四五六七八九十百千]+条',  # "第X条"
            r'^[一二三四五六七八九十百千]+[\、\.]',  # 中文数字开头
            r'^\d+\.\d+',  # 数字编号
            r'^[A-Z]\.',  # 字母编号
        ]
        
        for pattern in patterns:
            if re.match(pattern, text):
                return True
        
        # 检查是否包含关键术语
        keywords = ['条', '款', '项', '规定', '要求', '标准', '规范', '细则']
        for keyword in keywords:
            if keyword in text and len(text) < 100:  # 标题通常较短
                return True
        
        return False
    
    def _extract_category(self, text: str) -> str:
        """
        提取规范条文的类别
        
        Args:
            text: 文本内容
            
        Returns:
            类别名称
        """
        categories = {
            '建筑': ['建筑', '房屋', '住宅', '民用'],
            '结构': ['结构', '混凝土', '钢筋', '基础', '地基'],
            '暖通': ['暖通', '通风', '空调', '供暖', '采暖'],
            '给排水': ['给排水', '给水', '排水', '管道', '水暖'],
            '电气': ['电气', '电力', '配电', '照明', '弱电'],
            '消防': ['消防', '防火', '灭火', '疏散', '报警'],
            '安全': ['安全', '施工安全', '职业安全'],
            '质量': ['质量', '验收', '检验', '检测'],
            '监理': ['监理', '监督', '检查']
        }
        
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return '通用'
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 文本内容
            
        Returns:
            关键词列表
        """
        # 移除标点符号和特殊字符
        clean_text = re.sub(r'[^\w\s]', ' ', text)
        
        # 分词（简单的基于空格的分词）
        words = clean_text.split()
        
        # 过滤常见停用词
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        
        keywords = []
        for word in words:
            if word not in stop_words and len(word) > 1:
                keywords.append(word)
        
        return keywords[:10]  # 最多返回10个关键词
    
    def clean_norms(self, norms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        清理规范条文数据
        
        Args:
            norms: 原始规范条文列表
            
        Returns:
            清理后的规范条文列表
        """
        cleaned_norms = []
        
        for norm in norms:
            # 清理标题
            norm['title'] = self._clean_text(norm['title'])
            
            # 清理内容
            norm['content'] = self._clean_text(norm['content'])
            
            # 移除空内容
            if not norm['content'].strip():
                continue
            
            # 标准化格式
            norm['content'] = self._normalize_content(norm['content'])
            
            cleaned_norms.append(norm)
        
        return cleaned_norms
    
    def _clean_text(self, text: str) -> str:
        """
        清理文本内容
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        # 移除多余空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # 标准化引号
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        return text.strip()
    
    def _normalize_content(self, content: str) -> str:
        """
        标准化内容格式
        
        Args:
            content: 原始内容
            
        Returns:
            标准化后的内容
        """
        # 分割成句子
        sentences = re.split(r'([。！？])', content)
        
        # 重新组合句子
        normalized = []
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]
            
            sentence = sentence.strip()
            if sentence:
                normalized.append(sentence)
        
        return '\n'.join(normalized)
    
    def convert_to_rules(self, norms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将规范条文转换为规则格式
        
        Args:
            norms: 规范条文列表
            
        Returns:
            规则列表
        """
        rules = []
        
        for i, norm in enumerate(norms):
            rule = {
                "rule_id": f"norm_{i+1:03d}",
                "name": norm['title'],
                "discipline": norm['category'],
                "keywords": norm['keywords'],
                "check_type": "any",
                "evidence_required": 2,
                "description": norm['content'],
                "is_mandatory": True,
                "code_reference": f"监理规范-{norm['source_file']}",
                "code_version": "监理规范",
                "status": "现行",
                "regex": self._generate_regex(norm['title']),
                "source": {
                    "file": norm['source_file'],
                    "category": norm['category']
                }
            }
            rules.append(rule)
        
        return rules
    
    def _generate_regex(self, title: str) -> str:
        """
        生成正则表达式
        
        Args:
            title: 规范条文标题
            
        Returns:
            正则表达式
        """
        # 提取数字和关键术语
        numbers = re.findall(r'\d+\.?\d*', title)
        keywords = re.findall(r'[\u4e00-\u9fa5]+', title)
        
        # 构建正则表达式
        regex_parts = []
        
        if numbers:
            regex_parts.append('|'.join(numbers))
        
        if keywords:
            regex_parts.append('|'.join(keywords[:3]))
        
        if regex_parts:
            return '|'.join(regex_parts)
        
        return title[:20]  # 如果无法生成，使用标题前20个字符
    
    def process_all_files(self) -> Dict[str, Any]:
        """
        处理所有文件
        
        Returns:
            处理结果统计
        """
        all_norms = []
        processed_files = 0
        error_files = []
        
        # 查找所有.doc和.docx文件
        for file_path in self.source_dir.glob('*.doc*'):
            print(f"处理文件: {file_path.name}")
            
            try:
                # 对于.doc文件，需要先转换为.docx
                if file_path.suffix.lower() == '.doc':
                    print(f"  转换.doc文件为.docx: {file_path.name}")
                    docx_path = self.convert_doc_to_docx(file_path)
                    if docx_path:
                        norms = self.extract_from_docx(docx_path)
                        all_norms.extend(norms)
                        processed_files += 1
                        # 删除临时文件
                        docx_path.unlink()
                    else:
                        error_files.append(file_path.name)
                    continue
                
                # 跳过临时文件
                if file_path.name.startswith('~$'):
                    continue
                
                norms = self.extract_from_docx(file_path)
                all_norms.extend(norms)
                processed_files += 1
                
            except Exception as e:
                print(f"  处理文件 {file_path.name} 时出错: {e}")
                error_files.append(file_path.name)
        
        # 清理数据
        cleaned_norms = self.clean_norms(all_norms)
        
        # 转换为规则格式
        rules = self.convert_to_rules(cleaned_norms)
        
        # 保存结果
        self._save_results(cleaned_norms, rules)
        
        return {
            "processed_files": processed_files,
            "total_norms": len(cleaned_norms),
            "total_rules": len(rules),
            "error_files": error_files
        }
    
    def _save_results(self, norms: List[Dict[str, Any]], rules: List[Dict[str, Any]]):
        """
        保存处理结果
        
        Args:
            norms: 规范条文列表
            rules: 规则列表
        """
        # 保存规范条文
        norms_file = self.output_dir / 'extracted_norms.json'
        with open(norms_file, 'w', encoding='utf-8') as f:
            json.dump(norms, f, ensure_ascii=False, indent=2)
        
        # 保存规则
        rules_file = self.output_dir / 'extracted_rules.json'
        with open(rules_file, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        
        print(f"已保存 {len(norms)} 条规范条文到: {norms_file}")
        print(f"已保存 {len(rules)} 条规则到: {rules_file}")


def main():
    """主函数"""
    source_dir = r"C:\Users\azyp\Desktop\AI\Coze 审图工作流配置手册\规范"
    output_dir = r"F:\AI智能审图系统_v6.0_项目开发\output\norms"
    
    extractor = NormExtractor(source_dir, output_dir)
    result = extractor.process_all_files()
    
    print("\n处理完成:")
    print(f"  处理文件数: {result['processed_files']}")
    print(f"  提取规范条文数: {result['total_norms']}")
    print(f"  生成规则数: {result['total_rules']}")
    
    if result['error_files']:
        print(f"  处理失败的文件: {', '.join(result['error_files'])}")


if __name__ == '__main__':
    main()