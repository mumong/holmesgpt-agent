#!/usr/bin/env python3
"""
Elasticsearch MCP 桥接服务器 (使用 langchain_mcp_adapters)
将 npm 包的 stdio MCP 服务器转换为 HTTP/SSE 服务器，供 HolmesGPT 使用

这个版本使用 langchain_mcp_adapters 来处理 MCP 协议，更可靠
支持优雅退出
"""

import asyncio
import logging
import os
import sys
import signal
from pathlib import Path
from typing import Optional

# 全局服务器引用，用于优雅关闭
_server: "uvicorn.Server" = None

from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.server.sse import SseServerTransport
from mcp.types import ToolsCapability, ServerCapabilities, Tool
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ElasticsearchMCPBridge:
    """Elasticsearch MCP 桥接类，使用 langchain_mcp_adapters"""
    
    def __init__(
        self,
        es_url: str,
        es_api_key: Optional[str] = None,
        es_username: Optional[str] = None,
        es_password: Optional[str] = None,
        es_ca_cert: Optional[str] = None,
        node_tls_reject_unauthorized: Optional[bool] = None,
        port: int = 8082,
        host: str = "0.0.0.0"
    ):
        """
        初始化桥接服务器
        
        Args:
            es_url: Elasticsearch URL
            es_api_key: Elasticsearch API Key（可选，与 username/password 二选一）
            es_username: Elasticsearch 用户名（可选，与 api_key 二选一）
            es_password: Elasticsearch 密码（可选，与 api_key 二选一）
            es_ca_cert: Elasticsearch CA 证书路径（可选）
            node_tls_reject_unauthorized: 是否禁用 Node.js TLS 证书验证（可选，用于自签名证书）
            port: HTTP 服务器端口
            host: HTTP 服务器主机
        """
        self.es_url = es_url
        self.es_api_key = es_api_key
        self.es_username = es_username
        self.es_password = es_password
        self.es_ca_cert = es_ca_cert
        self.node_tls_reject_unauthorized = node_tls_reject_unauthorized
        self.port = port
        self.host = host
        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.tools_cache: Optional[list] = None
        self.tool_metadata_cache: Optional[list] = None  # 缓存工具元数据（名称、描述、schema）
        
    async def create_mcp_client(self):
        """创建 MCP 客户端"""
        env = {
            "ES_URL": self.es_url
        }
        
        # 优先使用用户名和密码，如果没有则使用 API Key
        if self.es_username and self.es_password:
            env["ES_USERNAME"] = self.es_username
            env["ES_PASSWORD"] = self.es_password
            logger.info(f"🚀 创建 Elasticsearch MCP 客户端（使用用户名密码认证）...")
            logger.info(f"   ES_URL: {self.es_url}")
            logger.info(f"   ES_USERNAME: {self.es_username}")
        elif self.es_api_key:
            env["ES_API_KEY"] = self.es_api_key
            logger.info(f"🚀 创建 Elasticsearch MCP 客户端（使用 API Key 认证）...")
            logger.info(f"   ES_URL: {self.es_url}")
        else:
            logger.warning("⚠️  未设置认证信息（ES_USERNAME/ES_PASSWORD 或 ES_API_KEY）")
        
        # 如果提供了 CA 证书路径
        if self.es_ca_cert:
            env["ES_CA_CERT"] = self.es_ca_cert
        
        # 如果设置了禁用 TLS 证书验证（从环境变量读取）
        if self.node_tls_reject_unauthorized is False:
            env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        
        self.mcp_client = MultiServerMCPClient(
            {
                "elasticsearch": {
                    "command": "npx",
                    "args": [
                        "-y",
                        "@elastic/mcp-server-elasticsearch"
                    ],
                    "env": env,
                    "transport": "stdio"
                }
            }
        )
        
        logger.info("✅ MCP 客户端创建成功")
        
    async def get_tools(self) -> list[Tool]:
        """获取工具列表"""
        if self.tools_cache is None:
            if self.mcp_client is None:
                await self.create_mcp_client()
            
            try:
                # 获取 LangChain 工具（每次调用 get_tools 都会创建新会话，但工具元数据可以缓存）
                langchain_tools = await self.mcp_client.get_tools()
                logger.info(f"✅ 从 MCP 客户端获取到 {len(langchain_tools)} 个 LangChain 工具")
                
                # 将 LangChain 工具转换为 MCP Tool 格式（只缓存元数据，不缓存工具对象）
                mcp_tools = []
                tool_metadata = []  # 缓存工具元数据（名称、描述、schema）
                
                for tool in langchain_tools:
                    try:
                        # 提取工具信息
                        tool_name = tool.name
                        tool_description = tool.description or ""
                        
                        # 获取输入 schema
                        input_schema = {"type": "object", "properties": {}, "required": []}
                        if hasattr(tool, 'args_schema') and tool.args_schema:
                            # 将 Pydantic 模型转换为 JSON Schema
                            try:
                                if hasattr(tool.args_schema, 'model_json_schema'):
                                    schema_dict = tool.args_schema.model_json_schema()
                                    input_schema = schema_dict
                                elif hasattr(tool.args_schema, 'schema'):
                                    input_schema = tool.args_schema.schema()
                            except Exception as e:
                                logger.warning(f"转换工具 {tool_name} 的 schema 失败: {e}")
                        elif hasattr(tool, 'schema') and tool.schema:
                            input_schema = tool.schema
                        
                        # 增强工具描述：添加必需参数说明
                        enhanced_description = tool_description
                        if input_schema.get("required"):
                            required_params = input_schema.get("required", [])
                            properties = input_schema.get("properties", {})
                            
                            # 构建参数说明
                            param_descriptions = []
                            for param in required_params:
                                param_info = properties.get(param, {})
                                param_type = param_info.get("type", "string")
                                param_desc = param_info.get("description", "")
                                param_example = param_info.get("example", "")
                                
                                param_str = f"- `{param}` ({param_type})"
                                if param_desc:
                                    param_str += f": {param_desc}"
                                if param_example:
                                    param_str += f" (示例: {param_example})"
                                param_descriptions.append(param_str)
                            
                            if param_descriptions:
                                enhanced_description += f"\n\n**必需参数：**\n" + "\n".join(param_descriptions)
                        
                        mcp_tool = Tool(
                            name=tool_name,
                            description=enhanced_description,
                            inputSchema=input_schema
                        )
                        mcp_tools.append(mcp_tool)
                        
                        # 保存工具元数据（用于后续查找）
                        tool_metadata.append({
                            "name": tool_name,
                            "description": tool_description,
                            "schema": input_schema
                        })
                    except Exception as e:
                        logger.warning(f"转换工具失败: {e}, 工具: {tool}")
                        continue
                
                self.tools_cache = mcp_tools
                self.tool_metadata_cache = tool_metadata  # 缓存元数据
                tool_names = [t.name for t in mcp_tools[:10]]
                logger.info(f"✅ 转换后得到 {len(mcp_tools)} 个 MCP 工具: {tool_names}...")
                
            except Exception as e:
                logger.error(f"获取工具列表失败: {e}", exc_info=True)
                import traceback
                logger.error(traceback.format_exc())
                self.tools_cache = []
                self.tool_metadata_cache = []
        
        return self.tools_cache
    
    async def call_tool(self, name: str, arguments: dict):
        """调用工具"""
        if self.mcp_client is None:
            await self.create_mcp_client()
        
        # 确保工具列表已加载（获取元数据）
        if self.tools_cache is None:
            await self.get_tools()
        
        try:
            # 验证工具是否存在
            tool_exists = any(t.name == name for t in self.tools_cache) if self.tools_cache else False
            if not tool_exists:
                raise ValueError(f"工具 {name} 未找到")
            
            # 每次调用工具时，重新获取工具对象（创建新会话）
            # 这样可以确保会话正确管理
            logger.debug(f"重新获取工具对象以调用: {name}")
            langchain_tools = await self.mcp_client.get_tools()
            
            # 查找对应的工具
            tool = None
            for t in langchain_tools:
                if t.name == name:
                    tool = t
                    break
            
            if not tool:
                raise ValueError(f"工具 {name} 未找到")
            
            # 调用工具（支持同步和异步）
            logger.debug(f"调用工具: {name}, 参数: {arguments}")
            if hasattr(tool, 'ainvoke'):
                result = await tool.ainvoke(arguments)
            elif hasattr(tool, 'invoke'):
                result = tool.invoke(arguments)
            else:
                # 尝试直接调用
                result = await tool(**arguments)
            
            # 转换为 MCP TextContent 格式
            from mcp.types import TextContent
            if isinstance(result, str):
                text = result
            elif isinstance(result, dict):
                import json
                text = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                text = str(result)
            
            return [TextContent(
                type="text",
                text=text
            )]
        except Exception as e:
            logger.error(f"调用工具失败: {e}", exc_info=True)
            import traceback
            logger.error(traceback.format_exc())
            from mcp.types import TextContent
            return [TextContent(
                type="text",
                text=f"工具调用失败: {str(e)}"
            )]
    
    async def run_bridge(self, read_stream, write_stream):
        """
        运行桥接逻辑
        
        Args:
            read_stream: SSE 客户端的读取流
            write_stream: SSE 客户端的写入流
        """
        try:
            # 创建代理 MCP 服务器
            bridge_server = Server("elasticsearch-mcp-bridge")
            
            # 转发工具列表请求
            @bridge_server.list_tools()
            async def handle_list_tools():
                """返回工具列表"""
                try:
                    tools = await self.get_tools()
                    logger.info(f"📋 返回 {len(tools)} 个工具")
                    return tools
                except Exception as e:
                    logger.error(f"获取工具列表失败: {e}", exc_info=True)
                    return []
            
            # 转发工具调用请求
            @bridge_server.call_tool()
            async def handle_call_tool(name: str, arguments: dict):
                """调用工具"""
                try:
                    logger.info(f"🔧 调用工具: {name}")
                    result = await self.call_tool(name, arguments)
                    logger.info(f"✅ 工具调用成功: {name}")
                    return result
                except Exception as e:
                    logger.error(f"工具调用失败: {e}", exc_info=True)
                    from mcp.types import TextContent
                    return [TextContent(
                        type="text",
                        text=f"工具调用异常: {str(e)}"
                    )]
            
            # 运行桥接服务器
            capabilities = ServerCapabilities(
                tools=ToolsCapability(listChanged=False),
                logging=None,
                experimental=None
            )
            
            await bridge_server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="elasticsearch-mcp-bridge",
                    server_version="2.0.0",
                    capabilities=capabilities,
                    notification_options=NotificationOptions(
                        tools_changed=False
                    )
                )
            )
        except Exception as e:
            logger.error(f"桥接运行错误: {e}", exc_info=True)
            raise


async def main():
    """主函数 - 启动 HTTP/SSE 桥接服务器"""
    global _server
    
    # 优先从配置文件读取，如果不存在则从环境变量读取
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from config_loader import load_elasticsearch_config
    
    file_config = load_elasticsearch_config()
    
    # 从配置文件或环境变量读取配置（配置文件优先级更高）
    es_url = file_config.get("es_url") or os.getenv("ES_URL", "http://localhost:9200")
    es_api_key = file_config.get("es_api_key") or os.getenv("ES_API_KEY")
    es_username = file_config.get("es_username") or os.getenv("ES_USERNAME")
    es_password = file_config.get("es_password") or os.getenv("ES_PASSWORD")
    es_ca_cert = file_config.get("es_ca_cert") or os.getenv("ES_CA_CERT")
    
    # 处理 NODE_TLS_REJECT_UNAUTHORIZED（仅从环境变量读取）
    node_tls_reject_unauthorized = None
    env_value = os.getenv("NODE_TLS_REJECT_UNAUTHORIZED")
    if env_value is not None:
        node_tls_reject_unauthorized = env_value.lower() in ("0", "false", "no")
    else:
        node_tls_reject_unauthorized = None
    
    port = int(file_config.get("bridge_port") or os.getenv("BRIDGE_PORT", "8082"))
    host = file_config.get("bridge_host") or os.getenv("BRIDGE_HOST", "0.0.0.0")
    
    # 检查认证信息
    if not es_username and not es_api_key:
        logger.warning("⚠️  未设置认证信息（ES_USERNAME/ES_PASSWORD 或 ES_API_KEY），某些功能可能无法使用")
    
    # 创建桥接实例
    bridge = ElasticsearchMCPBridge(
        es_url=es_url,
        es_api_key=es_api_key,
        es_username=es_username,
        es_password=es_password,
        es_ca_cert=es_ca_cert,
        node_tls_reject_unauthorized=node_tls_reject_unauthorized,
        port=port,
        host=host
    )
    
    # 创建 SSE 传输
    transport = SseServerTransport("/messages/")
    
    async def handle_sse(request: Request):
        """处理 SSE 连接"""
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await bridge.run_bridge(streams[0], streams[1])
        from starlette.responses import Response
        return Response()
    
    # 创建 ASGI 应用包装器用于 POST 消息处理
    async def post_message_app(scope, receive, send):
        """ASGI 应用包装器，用于处理 POST 消息"""
        await transport.handle_post_message(scope, receive, send)
    
    app_server = Starlette(
        debug=False,
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=post_message_app)
        ]
    )
    
    # 创建服务器配置，设置优雅关闭
    config = uvicorn.Config(
        app_server,
        host=host,
        port=port,
        log_level="warning",  # 减少日志输出
        timeout_graceful_shutdown=5  # 5秒优雅关闭超时
    )
    _server = uvicorn.Server(config)
    
    # 设置信号处理，让 uvicorn 能够优雅退出
    _server.install_signal_handlers = lambda: None  # 禁用默认信号处理
    
    # 自定义信号处理
    def handle_exit(signum, frame):
        logger.info(f"🛑 收到退出信号 {signum}，正在关闭...")
        if _server:
            _server.should_exit = True
    
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    logger.info(f"🌉 Elasticsearch MCP 桥接服务器启动: http://{host}:{port}")
    logger.info(f"   Elasticsearch URL: {es_url}")
    
    try:
        await _server.serve()
    finally:
        # 清理资源
        logger.info("✅ Elasticsearch MCP 桥接服务器已关闭")
        if bridge.mcp_client:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 收到键盘中断，退出")
        sys.exit(0)

