# -*- coding: utf-8 -*-
from .base_agent import BaseAgent, AgentConfig, AgentReport
from .discipline_agents import (
    BuildingAgent, StructureAgent, HvacAgent, PlumbingAgent,
    ElectricalAgent, FireAgent, FreeReviewAgent,
    CurtainWallAgent, DecorationAgent, LandscapeAgent, FoundationPitAgent,
)
from .chief_agent import ChiefAgent, ChiefReport, DedupResult

# 统一Agent注册中心 —— 所有消费方（master_v7/orchestrator/migrate）共用此字典
# 新增Agent只需在此处加一行即可
AGENT_REGISTRY = {
    "building": BuildingAgent,
    "structure": StructureAgent,
    "hvac": HvacAgent,
    "plumbing": PlumbingAgent,
    "electrical": ElectricalAgent,
    "fire": FireAgent,
    "free_review": FreeReviewAgent,
    "curtain_wall": CurtainWallAgent,
    "decoration": DecorationAgent,
    "landscape": LandscapeAgent,
    "foundation_pit": FoundationPitAgent,
}
