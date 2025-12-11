#!/usr/bin/env python3
"""
MCP Server Manager
负责根据配置文件自动启动和管理 MCP 服务器
"""
import os
import sys
import time
import signal
import asyncio
import atexit
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from urllib.parse import urlparse

import yaml
import httpx

logger = logging.getLogger(__name__)

# 用于跟踪所有启动的进程（即使管理器被销毁也能清理）
_all_started_processes: List[subprocess.Popen] = []
_cleanup_registered = False


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


@dataclass
class MCPServerInfo:
    """MCP 服务器信息"""
    name: str
    description: str
    url: str
    port: int
    host: str
    enabled: bool
    script_path: Optional[Path] = None
    config: Dict[str, Any] = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    status: str = "stopped"  # stopped, starting, running, failed
    error: Optional[str] = None


class MCPServerManager:
    """MCP 服务器管理器"""
    
    # 服务器名称到脚本路径的映射
    SERVER_SCRIPTS = {
        "test_tool_server": "tools/test_mcp_server_simple.py",
        "elasticsearch": "mcp_bridges/elasticsearch/bridge_server.py",
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化 MCP 服务器管理器
        
        Args:
            config_path: 配置文件路径，如果为 None 则使用默认路径
        """
        self.project_root = get_project_root()
        
        if config_path is None:
            config_path = self.project_root / "config" / "config.yaml"
        
        self.config_path = config_path
        self.servers: Dict[str, MCPServerInfo] = {}
        self._shutdown_event = asyncio.Event()
        self._health_check_task: Optional[asyncio.Task] = None
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not self.config_path.exists():
            logger.warning(f"配置文件不存在: {self.config_path}")
            return {}
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def parse_mcp_servers(self) -> Dict[str, MCPServerInfo]:
        """解析 MCP 服务器配置"""
        config = self.load_config()
        mcp_servers = config.get("mcp_servers", {})
        
        servers = {}
        for name, server_config in mcp_servers.items():
            if not isinstance(server_config, dict):
                continue
            
            enabled = server_config.get("enabled", False)
            description = server_config.get("description", "")
            inner_config = server_config.get("config", {})
            url = inner_config.get("url", "")
            
            # 解析 URL 获取 host 和 port
            if url:
                parsed = urlparse(url)
                host = parsed.hostname or "localhost"
                port = parsed.port or 8080
            else:
                host = "localhost"
                port = 8080
            
            # 获取脚本路径
            script_path = None
            if name in self.SERVER_SCRIPTS:
                script_path = self.project_root / self.SERVER_SCRIPTS[name]
                if not script_path.exists():
                    logger.warning(f"MCP 服务器脚本不存在: {script_path}")
                    script_path = None
            
            servers[name] = MCPServerInfo(
                name=name,
                description=description,
                url=url,
                port=port,
                host=host,
                enabled=enabled,
                script_path=script_path,
                config=inner_config
            )
        
        return servers
    
    def _build_env(self, server: MCPServerInfo) -> Dict[str, str]:
        """构建服务器进程的环境变量"""
        env = os.environ.copy()
        
        # 添加 Python 路径
        env["PYTHONPATH"] = str(self.project_root)
        
        # 根据服务器类型设置特定的环境变量
        if server.name == "elasticsearch":
            config = server.config
            if config.get("es_url"):
                env["ES_URL"] = config["es_url"]
            if config.get("username"):
                env["ES_USERNAME"] = config["username"]
            if config.get("password"):
                env["ES_PASSWORD"] = config["password"]
            if config.get("api_key"):
                env["ES_API_KEY"] = config["api_key"]
            # 禁用 TLS 验证（用于自签名证书）
            env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
            env["BRIDGE_PORT"] = str(server.port)
            env["BRIDGE_HOST"] = server.host
        
        return env
    
    async def start_server(self, name: str) -> bool:
        """
        启动指定的 MCP 服务器
        
        Args:
            name: 服务器名称
        
        Returns:
            是否启动成功
        """
        if name not in self.servers:
            logger.error(f"未知的 MCP 服务器: {name}")
            return False
        
        server = self.servers[name]
        
        if not server.enabled:
            logger.debug(f"MCP 服务器 {name} 未启用，跳过")
            return False
        
        if not server.script_path or not server.script_path.exists():
            logger.error(f"MCP 服务器 {name} 的脚本不存在: {server.script_path}")
            server.status = "failed"
            server.error = "脚本文件不存在"
            return False
        
        # 检查是否已经在运行
        if server.process and server.process.poll() is None:
            logger.info(f"MCP 服务器 {name} 已在运行")
            return True
        
        # 检查端口是否已被占用（可能是之前启动的进程）
        if await self._check_health(server):
            logger.info(f"MCP 服务器 {name} 已在端口 {server.port} 上运行")
            server.status = "running"
            return True
        
        logger.info(f"🚀 启动 MCP 服务器: {name} (端口: {server.port})")
        server.status = "starting"
        
        try:
            # 构建环境变量
            env = self._build_env(server)
            
            # 获取 Python 解释器路径
            python_path = sys.executable
            
            # 启动子进程
            server.process = subprocess.Popen(
                [python_path, str(server.script_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.project_root),
                # 创建新的进程组，方便后续终止
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            # 添加到全局进程列表，确保清理
            _all_started_processes.append(server.process)
            
            # 等待服务器启动
            max_wait = 10  # 最大等待 10 秒
            for i in range(max_wait * 2):
                await asyncio.sleep(0.5)
                
                # 检查进程是否还在运行
                if server.process.poll() is not None:
                    # 进程已退出，读取错误输出
                    stdout, _ = server.process.communicate()
                    error_msg = stdout.decode('utf-8', errors='ignore')[-500:] if stdout else "未知错误"
                    logger.error(f"MCP 服务器 {name} 启动失败: {error_msg}")
                    server.status = "failed"
                    server.error = error_msg
                    return False
                
                # 检查健康状态
                if await self._check_health(server):
                    logger.info(f"✅ MCP 服务器 {name} 启动成功 (端口: {server.port})")
                    server.status = "running"
                    server.error = None
                    return True
            
            # 超时
            logger.warning(f"⚠️ MCP 服务器 {name} 启动超时，但进程仍在运行")
            server.status = "running"  # 假设正在运行
            return True
            
        except Exception as e:
            logger.error(f"启动 MCP 服务器 {name} 失败: {e}", exc_info=True)
            server.status = "failed"
            server.error = str(e)
            return False
    
    async def stop_server(self, name: str) -> bool:
        """
        停止指定的 MCP 服务器
        
        Args:
            name: 服务器名称
        
        Returns:
            是否停止成功
        """
        if name not in self.servers:
            return False
        
        server = self.servers[name]
        
        if not server.process:
            server.status = "stopped"
            return True
        
        logger.info(f"🛑 停止 MCP 服务器: {name}")
        
        try:
            if os.name != 'nt':
                # Unix: 发送 SIGTERM 到进程组
                os.killpg(os.getpgid(server.process.pid), signal.SIGTERM)
            else:
                # Windows
                server.process.terminate()
            
            # 等待进程结束
            try:
                server.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 强制终止
                if os.name != 'nt':
                    os.killpg(os.getpgid(server.process.pid), signal.SIGKILL)
                else:
                    server.process.kill()
            
            server.process = None
            server.status = "stopped"
            logger.info(f"✅ MCP 服务器 {name} 已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止 MCP 服务器 {name} 失败: {e}")
            return False
    
    async def _check_health(self, server: MCPServerInfo) -> bool:
        """检查服务器健康状态"""
        try:
            # 尝试连接 SSE 端点
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"http://{server.host}:{server.port}/sse")
                # SSE 端点返回流，所以我们只检查连接是否成功
                return response.status_code in [200, 500]  # 500 可能是因为没有正确的 MCP 握手
        except Exception:
            return False
    
    async def start_all_enabled(self) -> Dict[str, bool]:
        """
        启动所有已启用的 MCP 服务器
        
        Returns:
            服务器名称到启动结果的映射
        """
        # 重新加载配置
        self.servers = self.parse_mcp_servers()
        
        results = {}
        enabled_servers = [s for s in self.servers.values() if s.enabled]
        
        if not enabled_servers:
            logger.info("📭 没有启用的 MCP 服务器")
            return results
        
        logger.info(f"🔄 准备启动 {len(enabled_servers)} 个 MCP 服务器...")
        
        # 按顺序启动（避免端口冲突等问题）
        for server in enabled_servers:
            if server.script_path:
                results[server.name] = await self.start_server(server.name)
            else:
                logger.warning(f"⚠️ MCP 服务器 {server.name} 没有配置脚本路径，无法自动启动")
                results[server.name] = False
        
        return results
    
    async def stop_all(self):
        """停止所有 MCP 服务器"""
        self._shutdown_event.set()
        
        # 停止健康检查任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        for name in list(self.servers.keys()):
            await self.stop_server(name)
    
    async def _health_check_loop(self, interval: int = 30):
        """
        定期健康检查循环
        
        Args:
            interval: 检查间隔（秒）
        """
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(interval)
                
                for name, server in self.servers.items():
                    if not server.enabled or server.status == "stopped":
                        continue
                    
                    is_healthy = await self._check_health(server)
                    
                    if is_healthy:
                        if server.status != "running":
                            server.status = "running"
                            logger.info(f"✅ MCP 服务器 {name} 恢复正常")
                    else:
                        if server.status == "running":
                            logger.warning(f"⚠️ MCP 服务器 {name} 健康检查失败，尝试重启...")
                            server.status = "failed"
                            # 尝试重启
                            await self.start_server(name)
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查出错: {e}")
    
    def start_health_check(self, interval: int = 30):
        """启动健康检查任务"""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(
                self._health_check_loop(interval)
            )
    
    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器的状态"""
        return {
            name: {
                "enabled": server.enabled,
                "status": server.status,
                "port": server.port,
                "url": server.url,
                "error": server.error,
                "has_script": server.script_path is not None
            }
            for name, server in self.servers.items()
        }


# 全局管理器实例
_global_manager: Optional[MCPServerManager] = None


def _cleanup_all_processes():
    """
    同步清理所有启动的进程
    这是最后的清理手段，确保即使异步清理失败也能清理进程
    """
    global _all_started_processes
    
    if not _all_started_processes:
        return
    
    logger.info("🧹 清理 MCP 服务器进程...")
    
    for process in list(_all_started_processes):
        try:
            if process.poll() is None:  # 进程仍在运行
                pid = process.pid
                logger.info(f"   终止进程 PID: {pid}")
                
                if os.name != 'nt':
                    # Unix: 首先尝试 SIGTERM
                    try:
                        pgid = os.getpgid(pid)
                        os.killpg(pgid, signal.SIGTERM)
                        time.sleep(0.5)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
                    
                    # 检查是否还在运行
                    if process.poll() is None:
                        try:
                            process.terminate()
                            time.sleep(0.5)
                        except:
                            pass
                    
                    # 如果还在运行，强制终止
                    if process.poll() is None:
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError, OSError):
                            pass
                        try:
                            process.kill()
                        except:
                            pass
                else:
                    # Windows
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                
                # 最后确认
                try:
                    process.wait(timeout=1)
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"清理进程时出错: {e}")
    
    _all_started_processes.clear()
    logger.info("✅ MCP 服务器进程已清理")


def _register_cleanup():
    """注册清理函数"""
    global _cleanup_registered
    
    if _cleanup_registered:
        return
    
    # 注册 atexit 处理器
    atexit.register(_cleanup_all_processes)
    
    # 注册信号处理器
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在清理...")
        _cleanup_all_processes()
        sys.exit(0)
    
    # 只在主线程中注册信号处理器
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except ValueError:
        # 如果不在主线程中，信号处理器注册会失败，这是正常的
        pass
    
    _cleanup_registered = True
    logger.debug("已注册进程清理处理器")


def get_mcp_manager() -> MCPServerManager:
    """获取全局 MCP 管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = MCPServerManager()
        # 注册清理函数
        _register_cleanup()
    return _global_manager


async def auto_start_mcp_servers() -> Dict[str, bool]:
    """
    自动启动所有已启用的 MCP 服务器
    在应用启动时调用
    
    Returns:
        服务器名称到启动结果的映射
    """
    manager = get_mcp_manager()
    results = await manager.start_all_enabled()
    
    # 启动健康检查
    manager.start_health_check()
    
    return results


async def shutdown_mcp_servers():
    """
    关闭所有 MCP 服务器
    在应用关闭时调用
    """
    global _global_manager
    if _global_manager:
        await _global_manager.stop_all()
        _global_manager = None
    
    # 确保清理所有进程
    _cleanup_all_processes()


def shutdown_mcp_servers_sync():
    """
    同步关闭所有 MCP 服务器
    用于信号处理器等无法使用异步的场景
    """
    global _global_manager
    
    if _global_manager:
        # 同步停止所有服务器
        for name, server in _global_manager.servers.items():
            if server.process and server.process.poll() is None:
                try:
                    logger.info(f"🛑 停止 MCP 服务器: {name}")
                    if os.name != 'nt':
                        os.killpg(os.getpgid(server.process.pid), signal.SIGTERM)
                    else:
                        server.process.terminate()
                    server.process.wait(timeout=3)
                except Exception as e:
                    logger.debug(f"停止 {name} 时出错: {e}")
                    try:
                        server.process.kill()
                    except:
                        pass
        _global_manager = None
    
    # 清理所有进程
    _cleanup_all_processes()

