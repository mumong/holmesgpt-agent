"""
Core 模块
核心业务逻辑，包括 HolmesGPT 服务、Runbook 管理、提示词配置和 MCP 服务器管理
"""

from .service import HolmesService, get_service
from .runbook import RunbookManager
from .prompts import SYSTEM_PROMPT
from .mcp_manager import (
    MCPServerManager,
    get_mcp_manager,
    auto_start_mcp_servers,
    shutdown_mcp_servers,
    shutdown_mcp_servers_sync,
)
from .environment import (
    is_running_in_kubernetes,
    get_environment,
    get_config_file_path,
    log_environment_info,
)

__all__ = [
    "HolmesService",
    "get_service",
    "RunbookManager",
    "SYSTEM_PROMPT",
    "MCPServerManager",
    "get_mcp_manager",
    "auto_start_mcp_servers",
    "shutdown_mcp_servers",
    "shutdown_mcp_servers_sync",
]

