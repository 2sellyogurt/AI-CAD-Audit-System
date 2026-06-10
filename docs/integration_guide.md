# 统一比例尺识别算法 - 集成指南

## 概述

本指南说明如何将 `UnifiedScaleRecognizer` 集成到现有的 AI 智能审图系统中，实现不同比例尺图纸的统一识别和坐标归一化。

## 模块位置

- 核心模块: `engine/unified_scale_recognizer.py`
- 设计文档: `docs/unified_scale_algorithm_design.md`
- 使用示例: `examples/scale_recognition_example.py`

## 核心功能

1. **多策略并行识别**: 5种识别策略，高可靠性
2. **置信度加权融合**: 智能融合多策略结果
3. **构件尺寸验证**: 使用标准构件尺寸反向验证
4. **多文件一致性验证**: 批量处理并验证一致性
5. **坐标归一化**: 统一转换为毫米单位

## 集成方案

### 方案一: 集成到 `OptimizedDxfParser`（推荐）

修改 `engine/optimized_dxf_parser.py`，在解析过程中自动应用比例尺识别。

#### 修改步骤

1. 在 `OptimizedDxfParser.__init__` 中添加比例尺识别器

```python
from engine.unified_scale_recognizer import UnifiedScaleRecognizer

class OptimizedDxfParser:
    def __init__(self, expand_blocks: bool = True, max_entities: int = 500000, 
                 auto_scale: bool = True):
        # ... 现有代码 ...
        self._auto_scale = auto_scale
        self._scale_recognizer = UnifiedScaleRecognizer() if auto_scale else None
        self._last_scale_result = None
```

2. 修改 `parse` 方法，添加比例尺识别和归一化

```python
def parse(self, dxf_path: str) -> Dict[str, Any]:
    # ... 现有代码 ...
    
    if self._auto_scale and self._scale_recognizer:
        try:
            # 读取 ezdxf doc
            import ezdxf
            doc = ezdxf.readfile(dxf_path)
            
            # 识别比例尺
            self._last_scale_result = self._scale_recognizer.recognize(
                doc=doc,
                texts=texts,
                entities=all_records,
                source_file=dxf_path
            )
            
            # 归一化实体
            entities = [
                self._scale_recognizer.normalize_entity(ent, self._last_scale_result.scale_factor)
                for ent in entities
            ]
            
            # 在结果中添加比例尺信息
            result["scale_info"] = self._last_scale_result.to_dict()
            
        except Exception as e:
            result["scale_info"] = {"error": str(e)}
    
    return result
```

3. 添加获取比例尺结果的方法

```python
def get_last_scale_result(self):
    """获取最后一次的比例尺识别结果"""
    return self._last_scale_result
```

### 方案二: 在 `step1_extract.py` 中集成

修改 `src/step1_extract.py`，在提取过程中应用比例尺识别。

#### 修改步骤

1. 在文件顶部添加导入

```python
from engine.unified_scale_recognizer import UnifiedScaleRecognizer
```

2. 在 `process_dxf` 函数中添加比例尺识别

```python
def process_dxf(dxf_path, output_dir, **kwargs):
    # ... 现有代码 ...
    
    # 比例尺识别（新增）
    scale_info = {}
    try:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        recognizer = UnifiedScaleRecognizer()
        
        # 构建简单的实体和文本格式
        simple_entities = []
        simple_texts = []
        
        # 这里可以从解析结果中提取
        # ...
        
        scale_result = recognizer.recognize(
            doc=doc,
            texts=simple_texts,
            entities=simple_entities,
            source_file=dxf_path
        )
        
        scale_info = scale_result.to_dict()
        
    except Exception as e:
        scale_info = {"error": str(e)}
    
    # 添加到输出数据
    data["scale_info"] = scale_info
    
    # ... 保存文件 ...
```

### 方案三: 在碰撞检测前统一比例尺

修改碰撞检测模块，在检测前统一所有图纸的比例尺。

```python
from engine.unified_scale_recognizer import (
    UnifiedScaleRecognizer,
    MultiFileScaleValidator
)

def unified_collision_detection(dxf_files):
    """统一比例尺后的碰撞检测"""
    validator = MultiFileScaleValidator()
    recognizer = UnifiedScaleRecognizer()
    parser = OptimizedDxfParser()
    
    file_entities = {}
    file_scales = {}
    
    # 第一步: 识别所有文件的比例尺
    for dxf_file in dxf_files:
        result = parser.parse(dxf_file)
        entities = result["entities"]
        
        import ezdxf
        doc = ezdxf.readfile(dxf_file)
        scale_result = recognizer.recognize(
            doc=doc,
            texts=result["texts"],
            entities=entities,
            source_file=dxf_file
        )
        
        validator.add_file_result(dxf_file, scale_result)
        file_entities[dxf_file] = entities
        file_scales[dxf_file] = scale_result
    
    # 第二步: 验证一致性
    validation = validator.validate_consistency()
    
    # 第三步: 归一化到主导比例尺
    dominant_scale = validation["dominant_scale"]
    normalized_entities = {}
    
    for dxf_file, entities in file_entities.items():
        file_scale = file_scales[dxf_file].scale_factor
        norm_factor = dominant_scale / file_scale if file_scale > 0 else 1.0
        
        normalized = [
            recognizer.normalize_entity(ent, norm_factor)
            for ent in entities
        ]
        normalized_entities[dxf_file] = normalized
    
    # 第四步: 执行碰撞检测（使用归一化后的坐标）
    # ... 现有碰撞检测代码 ...
    
    return {
        "collision_results": ...,
        "scale_validation": validation,
        "normalized_entities": normalized_entities
    }
```

## 完整集成代码示例

下面是集成到现有系统的完整代码片段：

### 1. 增强版的 DXF 解析器

```python
# 在 engine/optimized_dxf_parser.py 中添加

class ScaledOptimizedDxfParser(OptimizedDxfParser):
    """带自动比例尺识别的 DXF 解析器"""
    
    def __init__(self, *args, auto_scale=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._auto_scale = auto_scale
        self._scale_recognizer = UnifiedScaleRecognizer() if auto_scale else None
        self._scale_result = None
    
    def parse_with_scale(self, dxf_path: str) -> Dict[str, Any]:
        """解析并自动归一化坐标"""
        result = self.parse(dxf_path)
        
        if not self._auto_scale:
            return result
        
        try:
            import ezdxf
            doc = ezdxf.readfile(dxf_path)
            
            self._scale_result = self._scale_recognizer.recognize(
                doc=doc,
                texts=result["texts"],
                entities=result["entities"],
                source_file=dxf_path
            )
            
            # 归一化
            result["entities"] = [
                self._scale_recognizer.normalize_entity(
                    ent, self._scale_result.scale_factor
                )
                for ent in result["entities"]
            ]
            
            result["scale_info"] = self._scale_result.to_dict()
            
        except Exception as e:
            result["scale_info"] = {"error": str(e)}
        
        return result
    
    def get_scale_result(self):
        """获取比例尺识别结果"""
        return self._scale_result
```

### 2. 批量处理工具

```python
# 创建 src/batch_scale_normalizer.py

import os
import json
from pathlib import Path
from engine.unified_scale_recognizer import (
    UnifiedScaleRecognizer,
    MultiFileScaleValidator
)
from engine.optimized_dxf_parser import OptimizedDxfParser
import ezdxf


def batch_normalize_scales(input_dir: str, output_dir: str):
    """
    批量归一化图纸比例尺
    
    Args:
        input_dir: 输入 DXF 目录
        output_dir: 输出 JSON 目录
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    recognizer = UnifiedScaleRecognizer()
    validator = MultiFileScaleValidator()
    parser = OptimizedDxfParser()
    
    dxf_files = list(input_path.glob("*.dxf"))
    results = {}
    
    print(f"发现 {len(dxf_files)} 个 DXF 文件")
    
    # 第一步: 识别所有比例尺
    for dxf_file in dxf_files:
        print(f"处理: {dxf_file.name}")
        
        parse_result = parser.parse(str(dxf_file))
        
        try:
            doc = ezdxf.readfile(str(dxf_file))
            scale_result = recognizer.recognize(
                doc=doc,
                texts=parse_result["texts"],
                entities=parse_result["entities"],
                source_file=str(dxf_file)
            )
            
            validator.add_file_result(str(dxf_file), scale_result)
            results[str(dxf_file)] = {
                "parse_result": parse_result,
                "scale_result": scale_result
            }
            
        except Exception as e:
            print(f"  错误: {e}")
            continue
    
    # 第二步: 验证一致性
    validation = validator.validate_consistency()
    dominant_scale = validation["dominant_scale"]
    
    print(f"\n一致性验证: {'通过' if validation['consistent'] else '不通过'}")
    print(f"主导比例尺: {dominant_scale}")
    
    if validation["warnings"]:
        print("\n警告:")
        for w in validation["warnings"]:
            print(f"  - {w}")
    
    # 第三步: 归一化并保存
    for dxf_file, data in results.items():
        file_scale = data["scale_result"].scale_factor
        norm_factor = dominant_scale / file_scale if file_scale > 0 else 1.0
        
        normalized_entities = [
            recognizer.normalize_entity(ent, norm_factor)
            for ent in data["parse_result"]["entities"]
        ]
        
        # 构建输出数据
        output_data = {
            "original_scale": data["scale_result"].to_dict(),
            "dominant_scale": dominant_scale,
            "normalization_factor": norm_factor,
            "entities": normalized_entities,
            "texts": data["parse_result"]["texts"]
        }
        
        # 保存
        output_file = output_path / (Path(dxf_file).stem + "_normalized.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"已保存: {output_file.name}")
    
    # 保存验证报告
    report_file = output_path / "scale_validation_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)
    
    print(f"\n完成！验证报告已保存到: {report_file}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python batch_scale_normalizer.py <input_dir> <output_dir>")
        sys.exit(1)
    
    batch_normalize_scales(sys.argv[1], sys.argv[2])
```

## 测试与验证

### 单元测试

```python
# 创建 tests/test_unified_scale.py

import unittest
from engine.unified_scale_recognizer import UnifiedScaleRecognizer

class TestUnifiedScaleRecognizer(unittest.TestCase):
    
    def test_basic_recognition(self):
        """测试基础识别功能"""
        recognizer = UnifiedScaleRecognizer()
        
        # 构造测试数据
        test_entities = [
            {
                "type": "CIRCLE",
                "center": (0, 0, 0),
                "radius": 50  # 假设真实直径是 100mm
            }
        ]
        
        # 这里需要完整的测试用例
        pass

if __name__ == "__main__":
    unittest.main()
```

### 实际图纸测试

1. 准备不同比例尺的测试图纸
2. 运行比例尺识别
3. 验证识别结果是否正确
4. 检查归一化后的坐标是否合理

## 注意事项

1. **性能考虑**: 比例尺识别会增加一些处理时间，对超大文件可以选择性禁用
2. **置信度阈值**: 建议设置置信度阈值，低于阈值时提示人工确认
3. **备份原始数据**: 在归一化前保存原始坐标，方便回退
4. **人工审核**: 关键项目建议人工审核比例尺识别结果

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 识别结果置信度低 | 图纸信息不完整 | 检查是否有 $INSUNITS、比例标注、标准图框 |
| 多文件不一致 | 不同图纸确实用了不同比例 | 选择主导比例尺统一，或保持各自比例 |
| 归一化后坐标异常 | 识别的比例尺错误 | 人工检查并修正比例尺 |
| 性能慢 | 文件过大 | 禁用部分策略，或使用采样识别 |

## 后续优化方向

1. 支持用户自定义标准构件尺寸库
2. 添加机器学习模型辅助识别
3. 支持更多图框标准（不限于 A0-A4）
4. 增加更多已知构件类型
5. 优化大文件处理性能
