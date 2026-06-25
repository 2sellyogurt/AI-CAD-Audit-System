# -*- coding: utf-8 -*-
"""
AI智能审图系统 v7.0 — 混合架构多角色Agent集群版

架构:
  preprocessor/  图纸预处理（标准化校验+ezdxf提取+CAD打印+分类）
  checkpoints/   参数化检查点引擎（YAML驱动+15种检查类型）
  agents/        6专业Agent+自由审查Agent+总工Agent
  scheduler/     Agent集群调度器（并行+异常恢复+限流）
  problem_pool/  统一问题池（完整溯源链+双路径标记+CAD定位）
  review_ui/     人工复核Web界面（Flask/FastAPI）
  report_v7/     报告生成（4角色Word/PDF）
  audit/         假阴性审计+操作审计日志
  llm/           LLM适配器（文本+多模态+故障转移+并发控制）
"""

__version__ = "7.0.0"
__project_id__ = "PROJ-20260529-001"
