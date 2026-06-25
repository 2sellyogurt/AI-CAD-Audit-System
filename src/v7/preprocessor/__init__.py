# -*- coding: utf-8 -*-
"""v7.preprocessor — 图纸预处理工具包

使用延迟导入策略：ezdxf 等重量级依赖仅在真正调用时才导入，
确保即使未安装 ezdxf 也不会导致整个包导入失败。
"""


def __getattr__(name):
    """延迟导入：按需加载子模块，避免 ezdxf 缺失时整体崩溃。"""
    _LAZY_MAP = {
        # name -> (module, attributes)
        "StandardizationChecker": ("v7.preprocessor.standardization_checker", ["StandardizationChecker", "StandardizationResult", "AnnotationRule"]),
        "StandardizationResult": ("v7.preprocessor.standardization_checker", ["StandardizationChecker", "StandardizationResult", "AnnotationRule"]),
        "AnnotationRule": ("v7.preprocessor.standardization_checker", ["StandardizationChecker", "StandardizationResult", "AnnotationRule"]),
        "DrawingExtractor": ("v7.preprocessor.drawing_extractor", ["DrawingExtractor", "DrawingInfo", "TextEntity"]),
        "DrawingInfo": ("v7.preprocessor.drawing_extractor", ["DrawingExtractor", "DrawingInfo", "TextEntity"]),
        "TextEntity": ("v7.preprocessor.drawing_extractor", ["DrawingExtractor", "DrawingInfo", "TextEntity"]),
        "find_autocad": ("v7.preprocessor.cad_printer", ["find_autocad", "print_drawing_autocad", "print_alternative_pillow"]),
        "print_drawing_autocad": ("v7.preprocessor.cad_printer", ["find_autocad", "print_drawing_autocad", "print_alternative_pillow"]),
        "print_alternative_pillow": ("v7.preprocessor.cad_printer", ["find_autocad", "print_drawing_autocad", "print_alternative_pillow"]),
        "EnhancedFrameDetector": ("v7.preprocessor.enhanced_frame_detector", ["EnhancedFrameDetector"]),
        "TitleBlockExtractor": ("v7.preprocessor.title_block_extractor", ["TitleBlockExtractor"]),
        "convert_dwg_batch": ("v7.preprocessor.dwg_converter", ["convert_dwg_batch", "scan_dwg_folder"]),
        "scan_dwg_folder": ("v7.preprocessor.dwg_converter", ["convert_dwg_batch", "scan_dwg_folder"]),
        "split_dxf_by_frames": ("v7.preprocessor.dwg_subset_splitter", ["split_dxf_by_frames", "split_dxf_by_layouts"]),
        "split_dxf_by_layouts": ("v7.preprocessor.dwg_subset_splitter", ["split_dxf_by_frames", "split_dxf_by_layouts"]),
    }

    if name in _LAZY_MAP:
        import importlib
        mod_path, attrs = _LAZY_MAP[name]
        try:
            mod = importlib.import_module(mod_path)
            # 缓存到当前模块，后续直接访问
            for attr in attrs:
                globals()[attr] = getattr(mod, attr)
            return globals()[name]
        except ImportError as e:
            raise ImportError(
                f"无法导入 '{name}': {e}。"
                f"请安装依赖: pip install ezdxf"
            ) from e

    raise AttributeError(f"module 'v7.preprocessor' has no attribute '{name}'")


# 显式导出列表（供 from v7.preprocessor import DrawingExtractor 等语法使用）
__all__ = [
    "StandardizationChecker", "StandardizationResult", "AnnotationRule",
    "DrawingExtractor", "DrawingInfo", "TextEntity",
    "find_autocad", "print_drawing_autocad", "print_alternative_pillow",
    "EnhancedFrameDetector", "TitleBlockExtractor",
    "convert_dwg_batch", "scan_dwg_folder",
    "split_dxf_by_frames", "split_dxf_by_layouts",
]
