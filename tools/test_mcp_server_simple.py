#!/usr/bin/env python3
"""
简化的测试 MCP 服务器 - 只输出"这是测试"
支持优雅退出
"""

import asyncio
import signal
import sys
import logging
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server.sse import SseServerTransport
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

# 创建 MCP 服务器实例
app = Server("test_tool_server")

# 全局服务器引用，用于优雅关闭
_server: uvicorn.Server = None


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """返回可用工具列表"""
    return [
        types.Tool(
            name="test_tool",
            description="只有当用户需要测试的时候才运行。这是一个简单的测试工具，用于验证 MCP 集成是否正常工作。",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理工具调用"""
    try:
        if name == "test_tool":
            logger.info("测试工具被调用")
            return [types.TextContent(
                type="text",
                text="这是测试huhu-xnet"
            )]
        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ 测试工具执行失败: {str(e)}"
        )]


async def main():
    """主函数 - SSE 传输方式"""
    global _server
    
    transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            from mcp.types import ToolsCapability, ServerCapabilities
            from mcp.server import NotificationOptions

            capabilities = ServerCapabilities(
                tools=ToolsCapability(listChanged=False),
                logging=None,
                experimental=None
            )

            await app.run(
                streams[0], streams[1], InitializationOptions(
                    server_name="test_tool_server",
                    server_version="1.0.0",
                    capabilities=capabilities,
                    notification_options=NotificationOptions(
                        tools_changed=False
                    )
                )
            )
        from starlette.responses import Response
        return Response()

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
        host="0.0.0.0", 
        port=8081, 
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

    logger.info("🚀 测试 MCP 服务器启动在 http://0.0.0.0:8081")
    logger.info("📋 可用工具: test_tool")
    
    try:
        await _server.serve()
    finally:
        logger.info("✅ 测试 MCP 服务器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 收到键盘中断，退出")
        sys.exit(0)
