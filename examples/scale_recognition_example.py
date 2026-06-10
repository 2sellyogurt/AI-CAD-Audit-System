# 统一比例尺识别算法 - 使用示例

## 1. 简单使用示例

```python
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.unified_scale_recognizer import (
    UnifiedScaleRecognizer,
    MultiFileScaleValidator
)
from engine.optimized_dxf_parser import OptimizedDxfParser

def example_single_file():
    """单个文件比例尺识别示例"""
    dxf_file = "path/to/your/file.dxf"
    
    # 1. 解析 DXF
    parser = OptimizedDxfParser()
    parse_result = parser.parse(dxf_file)
    
    entities = parse_result["entities"]
    texts = parse_result["texts"]
    
    # 2. 识别比例尺
    recognizer = UnifiedScaleRecognizer()
    
    # 需要获取 ezdxf doc 对象（用于 $INSUNITS）
    import ezdxf
    doc = ezdxf.readfile(dxf_file)
    
    scale_result = recognizer.recognize(
        doc=doc,
        texts=texts,
        entities=entities,
        source_file=dxf_file
    )
    
    print(f"识别结果:")
    print(f"  比例因子: {scale_result.scale_factor}")
    print(f"  置信度: {scale_result.confidence:.2%}")
    print(f"  主要策略: {scale_result.primary_strategy.value}")
    print(f"  单位: {scale_result.unit_name}")
    print(f"  验证通过: {scale_result.validated}")
    print(f"  验证分数: {scale_result.validation_score:.2%}")
    
    # 3. 归一化实体坐标到毫米
    normalized_entities = []
    for ent in entities:
        normalized = recognizer.normalize_entity(ent, scale_result.scale_factor)
        normalized_entities.append(normalized)
    
    return scale_result, normalized_entities


def example_multi_file():
    """多文件比例尺一致性验证示例"""
    dxf_files = [
        "path/to/file1.dxf",
        "path/to/file2.dxf",
        "path/to/file3.dxf"
    ]
    
    validator = MultiFileScaleValidator()
    recognizer = UnifiedScaleRecognizer()
    parser = OptimizedDxfParser()
    
    import ezdxf
    
    for dxf_file in dxf_files:
        # 解析和识别
        parse_result = parser.parse(dxf_file)
        doc = ezdxf.readfile(dxf_file)
        
        scale_result = recognizer.recognize(
            doc=doc,
            texts=parse_result["texts"],
            entities=parse_result["entities"],
            source_file=dxf_file
        )
        
        validator.add_file_result(dxf_file, scale_result)
    
    # 验证一致性
    validation = validator.validate_consistency()
    
    print(f"多文件验证:")
    print(f"  一致性: {'通过' if validation['consistent'] else '不通过'}")
    print(f"  主导比例尺: {validation['dominant_scale']}")
    print(f"  文件数: {validation['file_count']}")
    
    if validation['warnings']:
        print("\n警告:")
        for w in validation['warnings']:
            print(f"  - {w}")
    
    if validation['outliers']:
        print("\n异常文件:")
        for outlier in validation['outliers']:
            print(f"  - {outlier['file']}: {outlier['scale']:.4f} (期望: {outlier['expected']:.4f}")
    
    return validation


if __name__ == "__main__":
    print("统一比例尺识别算法示例")
    print("=" * 50)
    print("\n请将示例代码中的路径替换为实际文件路径")
