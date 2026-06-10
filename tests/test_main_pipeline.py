import importlib.util
import os
import sys
import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _load_src_module(name, filename):
    filepath = os.path.join(SRC_DIR, filename)
    if not os.path.exists(filepath):
        pytest.skip(f"Source file not found: {filepath}")
    spec = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_import_master():
    mod = _load_src_module("master", "master.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "parse_args")
    assert hasattr(mod, "STEPS")
    assert len(mod.STEPS) == 7


def test_import_step1():
    mod = _load_src_module("step1_extract", "step1_extract.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "process_dxf")
    assert hasattr(mod, "extract_dxf_texts")
    assert hasattr(mod, "extract_elevations")
    assert hasattr(mod, "infer_discipline")
    assert hasattr(mod, "infer_building")


def test_import_step2():
    mod = _load_src_module("step2_compliance", "step2_compliance.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "parse_args")


def test_import_step3():
    mod = _load_src_module("step3_defect", "step3_defect.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "parse_args")


def test_import_step4():
    mod = _load_src_module("step4_cross_check", "step4_cross_check.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "parse_args")


def test_import_step5():
    mod = _load_src_module("step5_engineering", "step5_engineering.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "parse_args")


def test_import_step6():
    mod = _load_src_module("step6_bim", "step6_bim.py")
    assert hasattr(mod, "main")
    assert hasattr(mod, "parse_args")
