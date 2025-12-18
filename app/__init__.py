"""
K8s AIOps Copilot 应用模块
基于 HolmesGPT 的智能运维 Copilot API 服务
"""

__version__ = "2.0.0"
__author__ = "HuHu"

from app.core import HolmesService, get_service, SYSTEM_PROMPT
from app.api import register_routes

__all__ = [
    "HolmesService",
    "get_service",
    "SYSTEM_PROMPT",
    "register_routes",
]
