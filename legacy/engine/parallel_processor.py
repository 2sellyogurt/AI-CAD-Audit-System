# -*- coding: utf-8 -*-
"""
并行处理器

提供多进程并行处理能力，优化CPU密集型任务性能

主要功能：
1. 并行碰撞检测
2. 并行规则检查
3. 并行数据处理
4. 异步IO处理

使用方式：
    processor = ParallelProcessor()
    
    # 并行处理任务
    results = processor.parallel_map(process_function, data_list)
    
    # 异步IO处理
    results = await processor.async_map(async_function, data_list)
"""

from __future__ import annotations

import os
import time
import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial

T = TypeVar('T')
R = TypeVar('R')


@dataclass
class ProcessingStats:
    """处理统计信息"""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_time: float = 0.0
    parallel_speedup: float = 1.0


class ParallelProcessor:
    """
    并行处理器

    提供多进程和多线程并行处理能力

    使用方式：
        processor = ParallelProcessor(max_workers=4)
        
        # 并行处理任务
        results = processor.parallel_map(process_function, data_list)
        
        # 异步IO处理
        results = processor.async_run(async_function, data_list)
    """

    def __init__(self, 
                 max_workers: Optional[int] = None,
                 use_processes: bool = True,
                 chunk_size: int = 100):
        """
        初始化并行处理器

        Args:
            max_workers: 最大工作进程/线程数，默认为CPU核心数
            use_processes: 是否使用多进程（True）或多线程（False）
            chunk_size: 任务分块大小
        """
        self._max_workers = max_workers or os.cpu_count() or 4
        self._use_processes = use_processes
        self._chunk_size = chunk_size
        
        # 统计信息
        self._stats = ProcessingStats()
        
        # 执行器
        self._executor = None

    def parallel_map(self, 
                     func: Callable[[T], R], 
                     data_list: List[T],
                     timeout: Optional[float] = None) -> List[R]:
        """
        并行映射函数

        Args:
            func: 要执行的函数
            data_list: 数据列表
            timeout: 超时时间（秒）

        Returns:
            List[R]: 结果列表
        """
        if not data_list:
            return []
        
        start_time = time.time()
        
        # 重置统计信息
        self._stats = ProcessingStats(total_tasks=len(data_list))
        
        # 分块处理
        chunks = self._split_into_chunks(data_list)
        
        results = []
        
        # 选择执行器
        executor_class = ProcessPoolExecutor if self._use_processes else ThreadPoolExecutor
        
        with executor_class(max_workers=self._max_workers) as executor:
            # 提交所有任务
            future_to_chunk = {}
            for chunk_idx, chunk in enumerate(chunks):
                future = executor.submit(self._process_chunk, func, chunk, chunk_idx)
                future_to_chunk[future] = chunk_idx
            
            # 收集结果
            chunk_results = {}
            for future in as_completed(future_to_chunk, timeout=timeout):
                chunk_idx = future_to_chunk[future]
                try:
                    chunk_result = future.result()
                    chunk_results[chunk_idx] = chunk_result
                    self._stats.completed_tasks += len(chunk_result)
                except Exception as e:
                    self._stats.failed_tasks += 1
                    # 记录错误但继续处理
                    print(f"警告: 块 {chunk_idx} 处理失败: {e}")
                    chunk_results[chunk_idx] = []
            
            # 按顺序合并结果
            for chunk_idx in sorted(chunk_results.keys()):
                results.extend(chunk_results[chunk_idx])
        
        # 更新统计信息
        self._stats.total_time = time.time() - start_time
        
        # 计算加速比
        if self._stats.total_time > 0:
            # 估算串行时间（假设线性扩展）
            estimated_serial_time = self._stats.total_time * self._max_workers
            self._stats.parallel_speedup = estimated_serial_time / self._stats.total_time
        
        return results

    def _process_chunk(self, func: Callable[[T], R], chunk: List[T], chunk_idx: int) -> List[R]:
        """处理单个数据块"""
        results = []
        for item in chunk:
            try:
                result = func(item)
                results.append(result)
            except Exception as e:
                # 记录错误但继续处理
                print(f"警告: 块 {chunk_idx} 中的任务处理失败: {e}")
                results.append(None)
        return results

    def _split_into_chunks(self, data_list: List[T]) -> List[List[T]]:
        """将数据列表分块"""
        chunks = []
        for i in range(0, len(data_list), self._chunk_size):
            chunk = data_list[i:i + self._chunk_size]
            chunks.append(chunk)
        return chunks

    async def async_map(self, 
                        async_func: Callable[[T], Any], 
                        data_list: List[T],
                        timeout: Optional[float] = None) -> List[Any]:
        """
        异步映射函数

        Args:
            async_func: 异步函数
            data_list: 数据列表
            timeout: 超时时间（秒）

        Returns:
            List[Any]: 结果列表
        """
        if not data_list:
            return []
        
        start_time = time.time()
        
        # 重置统计信息
        self._stats = ProcessingStats(total_tasks=len(data_list))
        
        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(self._max_workers)
        
        async def process_with_semaphore(item: T) -> Any:
            async with semaphore:
                return await async_func(item)
        
        # 并发执行所有任务
        tasks = [process_with_semaphore(item) for item in data_list]
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                self._stats.failed_tasks += 1
                processed_results.append(None)
            else:
                self._stats.completed_tasks += 1
                processed_results.append(result)
        
        # 更新统计信息
        self._stats.total_time = time.time() - start_time
        
        return processed_results

    def parallel_collision_detection(self, 
                                     elements: List[Any],
                                     detection_func: Callable[[Any, Any], bool]) -> List[Tuple[str, str]]:
        """
        并行碰撞检测

        Args:
            elements: 元素列表
            detection_func: 碰撞检测函数

        Returns:
            List[Tuple[str, str]]: 碰撞对列表
        """
        # 生成所有候选对
        candidates = []
        for i in range(len(elements)):
            for j in range(i + 1, len(elements)):
                candidates.append((elements[i], elements[j]))
        
        # 使用模块级别的函数
        def check_collision(pair: Tuple[Any, Any]) -> Optional[Tuple[str, str]]:
            elem_a, elem_b = pair
            if detection_func(elem_a, elem_b):
                return (elem_a.element_id, elem_b.element_id)
            return None
        
        # 并行检测
        results = self.parallel_map(check_collision, candidates)
        
        # 过滤有效结果
        return [result for result in results if result is not None]

    def parallel_rule_check(self,
                           elements: List[Any],
                           rule_func: Callable[[Any], List[Any]]) -> List[Any]:
        """
        并行规则检查

        Args:
            elements: 元素列表
            rule_func: 规则检查函数

        Returns:
            List[Any]: 检查结果列表
        """
        return self.parallel_map(rule_func, elements)

    def get_stats(self) -> ProcessingStats:
        """获取统计信息"""
        return self._stats

    def get_optimal_workers(self, task_type: str = "cpu") -> int:
        """
        获取最优工作进程/线程数

        Args:
            task_type: 任务类型（"cpu" 或 "io"）

        Returns:
            int: 最优工作进程/线程数
        """
        cpu_count = os.cpu_count() or 4
        
        if task_type == "cpu":
            # CPU密集型任务：使用CPU核心数
            return cpu_count
        elif task_type == "io":
            # IO密集型任务：使用更多线程
            return cpu_count * 2
        else:
            return cpu_count


class AsyncParallelProcessor:
    """
    异步并行处理器

    专门用于异步IO密集型任务

    使用方式：
        processor = AsyncParallelProcessor()
        results = await processor.process(async_function, data_list)
    """

    def __init__(self, max_concurrent: int = 100):
        """
        初始化异步并行处理器

        Args:
            max_concurrent: 最大并发数
        """
        self._max_concurrent = max_concurrent
        self._stats = ProcessingStats()

    async def process(self, 
                      async_func: Callable[[T], Any], 
                      data_list: List[T],
                      timeout: Optional[float] = None) -> List[Any]:
        """
        异步处理任务

        Args:
            async_func: 异步函数
            data_list: 数据列表
            timeout: 超时时间（秒）

        Returns:
            List[Any]: 结果列表
        """
        if not data_list:
            return []
        
        start_time = time.time()
        
        # 重置统计信息
        self._stats = ProcessingStats(total_tasks=len(data_list))
        
        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(self._max_concurrent)
        
        async def process_with_semaphore(item: T) -> Any:
            async with semaphore:
                return await async_func(item)
        
        # 并发执行所有任务
        tasks = [process_with_semaphore(item) for item in data_list]
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                self._stats.failed_tasks += 1
                processed_results.append(None)
            else:
                self._stats.completed_tasks += 1
                processed_results.append(result)
        
        # 更新统计信息
        self._stats.total_time = time.time() - start_time
        
        return processed_results

    def get_stats(self) -> ProcessingStats:
        """获取统计信息"""
        return self._stats


if __name__ == "__main__":
    # 测试代码
    import random
    
    def cpu_intensive_task(x: int) -> int:
        """CPU密集型任务"""
        total = 0
        for i in range(10000):
            total += x * i
        return total
    
    async def io_intensive_task(x: int) -> int:
        """IO密集型任务"""
        await asyncio.sleep(0.01)  # 模拟IO操作
        return x * 2
    
    async def test_async_processor():
        """测试异步处理器"""
        processor = AsyncParallelProcessor(max_concurrent=10)
        
        data = list(range(100))
        
        start_time = time.time()
        results = await processor.process(io_intensive_task, data)
        end_time = time.time()
        
        print(f"异步处理 {len(data)} 个任务")
        print(f"耗时: {end_time - start_time:.3f} 秒")
        print(f"统计: {processor.get_stats()}")
        
        # 验证结果
        assert len(results) == len(data), "结果数量不匹配"
        assert all(result == x * 2 for result, x in zip(results, data)), "结果不正确"
    
    print("测试并行处理器...")
    
    # 测试多进程处理器
    processor = ParallelProcessor(max_workers=4, use_processes=True)
    
    data = list(range(100))
    
    start_time = time.time()
    results = processor.parallel_map(cpu_intensive_task, data)
    end_time = time.time()
    
    print(f"多进程处理 {len(data)} 个任务")
    print(f"耗时: {end_time - start_time:.3f} 秒")
    print(f"统计: {processor.get_stats()}")
    
    # 验证结果
    assert len(results) == len(data), "结果数量不匹配"
    
    # 测试异步处理器
    asyncio.run(test_async_processor())
    
    print("✓ 所有测试通过！")