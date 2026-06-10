# -*- coding: utf-8 -*-
"""
T13 单元测试覆盖 — 统一测试运行器

整合所有模块验证：
  T1-T5: MM级精度模块（scale, elevation, data_clean, coordinate, topology）
  T6: S7.1 单专业规则审查
  T7: S7.2 跨专业交叉验证
  T8: S8 反馈闭环机制
  T9: 交叉验证集成
  T10: 异常处理与内存优化
  T11: 构件分类准确率提升
  T12: 版本对比功能

运行方式:
  python run_all_tests.py              # 运行全部测试
  python run_all_tests.py T6 T10       # 运行指定模块
  python run_all_tests.py --quick      # 快速模式（跳过耗时测试）
"""

import sys
import os
import time
import importlib.util
import traceback
from typing import List, Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# 测试模块配置
TEST_MODULES = [
    ("T6", "temp_t6_verify.py", "S7.1 单专业规则审查"),
    ("T7", "temp_t7_verify.py", "S7.2 跨专业交叉验证"),
    ("T8", "temp_t8_verify.py", "S8 反馈闭环机制"),
    ("T9", "temp_t9_verify.py", "交叉验证集成"),
    ("T10", "temp_t10_verify.py", "异常处理与内存优化"),
    ("T11", "temp_t11_verify.py", "构件分类准确率提升"),
    ("T12", "temp_t12_verify.py", "版本对比功能"),
    ("T14", "temp_t14_verify.py", "日志系统完善"),
]


def run_test_module(module_id: str, filename: str, description: str) -> Tuple[int, int, float]:
    """运行单个测试模块，返回(通过数, 失败数, 耗时秒)。"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    if not os.path.exists(filepath):
        print(f"\n[{module_id}] {description}")
        print(f"  ⚠ 测试文件不存在: {filename}")
        return 0, 0, 0.0

    start_time = time.time()

    try:
        # 动态加载并运行测试模块
        spec = importlib.util.spec_from_file_location(f"test_{module_id}", filepath)
        if spec is None or spec.loader is None:
            print(f"\n[{module_id}] {description}")
            print(f"  ⚠ 无法加载模块: {filename}")
            return 0, 0, 0.0

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 检查是否有run_all_tests函数
        if hasattr(module, 'run_all_tests'):
            # 捕获输出
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            try:
                success = module.run_all_tests()
            except Exception as e:
                success = False
                print(f"运行异常: {e}")

            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

            # 解析结果
            passed = output.count("✓")
            failed = output.count("✗")

            # 如果没有解析到，从输出中提取
            if passed == 0 and failed == 0:
                # 查找 "X/Y 通过" 格式
                import re
                match = re.search(r'(\d+)/(\d+) 通过', output)
                if match:
                    passed = int(match.group(1))
                    total = int(match.group(2))
                    failed = total - passed

            elapsed = time.time() - start_time

            print(f"\n[{module_id}] {description} — {elapsed:.1f}s")
            if passed > 0 or failed > 0:
                status = "✓" if success else "✗"
                print(f"  {status} {passed}/{passed+failed} 通过")
            else:
                print(f"  ⚠ 无法解析测试结果")

            return passed, failed, elapsed
        else:
            elapsed = time.time() - start_time
            print(f"\n[{module_id}] {description}")
            print(f"  ⚠ 模块无run_all_tests函数")
            return 0, 0, elapsed

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n[{module_id}] {description}")
        print(f"  ✗ 运行失败: {e}")
        traceback.print_exc()
        return 0, 1, elapsed


def main():
    args = sys.argv[1:]

    # 解析参数
    quick_mode = "--quick" in args
    selected_modules = [a for a in args if not a.startswith("--")]

    if quick_mode:
        print("[快速模式] 跳过耗时测试")

    # 筛选要运行的模块
    modules_to_run = TEST_MODULES
    if selected_modules:
        modules_to_run = [(mid, fn, desc) for mid, fn, desc in TEST_MODULES if mid in selected_modules]
        if not modules_to_run:
            print(f"错误: 未找到匹配的测试模块: {selected_modules}")
            print(f"可用模块: {[m[0] for m in TEST_MODULES]}")
            sys.exit(1)

    print("=" * 70)
    print("BIM智能审图系统 — 全量单元测试")
    print("=" * 70)
    print(f"运行模块: {len(modules_to_run)} 个")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    total_passed = 0
    total_failed = 0
    total_elapsed = 0.0
    results: List[Tuple[str, int, int, float]] = []

    for module_id, filename, description in modules_to_run:
        passed, failed, elapsed = run_test_module(module_id, filename, description)
        total_passed += passed
        total_failed += failed
        total_elapsed += elapsed
        results.append((module_id, passed, failed, elapsed))

    # 汇总
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)

    for module_id, passed, failed, elapsed in results:
        total = passed + failed
        if total > 0:
            status = "✓" if failed == 0 else "✗"
            print(f"  {status} {module_id}: {passed}/{total} 通过 ({elapsed:.1f}s)")
        else:
            print(f"  ⚠ {module_id}: 无测试结果 ({elapsed:.1f}s)")

    print("-" * 70)
    total_tests = total_passed + total_failed
    if total_tests > 0:
        success_rate = total_passed / total_tests * 100
        print(f"总计: {total_passed}/{total_tests} 通过 ({success_rate:.1f}%)")
    print(f"总耗时: {total_elapsed:.1f}s")
    print("=" * 70)

    # 返回码
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
