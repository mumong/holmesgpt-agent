#!/usr/bin/env python3
"""
HolmesGPT API Server
FastAPI 应用入口，只负责应用配置和启动
"""
import os
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import register_routes

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger(__name__)

# 确保相关模块的日志也能输出
logging.getLogger('app.core.service').setLevel(logging.INFO)
logging.getLogger('app.core.mcp_manager').setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    from app.core import get_service
    from app.core.mcp_manager import auto_start_mcp_servers, shutdown_mcp_servers, get_mcp_manager
    
    logger.info("=" * 60)
    logger.info("🚀 K8s AIOps Copilot 启动中...")
    logger.info("=" * 60)
    
    # ==================== 1. 启动 MCP 服务器 ====================
    logger.info("")
    logger.info("📡 [步骤 1/2] 启动 MCP 服务器...")
    logger.info("-" * 40)
    
    try:
        mcp_results = await auto_start_mcp_servers()
        
        if mcp_results:
            success_count = sum(1 for v in mcp_results.values() if v)
            total_count = len(mcp_results)
            
            for name, success in mcp_results.items():
                status_icon = "✅" if success else "❌"
                logger.info(f"   {status_icon} {name}: {'启动成功' if success else '启动失败'}")
            
            logger.info(f"   📊 MCP 服务器: {success_count}/{total_count} 个启动成功")
        else:
            logger.info("   📭 没有配置需要自动启动的 MCP 服务器")
        
        # 等待 MCP 服务器完全启动
        if any(mcp_results.values()):
            logger.info("   ⏳ 等待 MCP 服务器就绪...")
            await asyncio.sleep(2)
            
    except Exception as e:
        logger.error(f"   ❌ MCP 服务器启动失败: {e}", exc_info=True)
    
    # ==================== 2. 初始化 HolmesGPT ====================
    logger.info("")
    logger.info("🤖 [步骤 2/2] 初始化 HolmesGPT...")
    logger.info("-" * 40)
    
    try:
        service = get_service()
        service.initialize()
    except Exception as e:
        logger.error(f"   ❌ HolmesGPT 初始化失败: {e}", exc_info=True)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ 服务启动完成!")
    logger.info("=" * 60)
    
    yield
    
    # ==================== 清理资源 ====================
    logger.info("")
    logger.info("🛑 正在关闭服务...")
    
    try:
        await shutdown_mcp_servers()
        logger.info("✅ MCP 服务器已关闭")
    except Exception as e:
        logger.error(f"关闭 MCP 服务器时出错: {e}")
    
    logger.info("👋 服务已停止")


# 创建 FastAPI 应用
app = FastAPI(
    title="HolmesGPT API Server",
    description="智能运维 Copilot API 服务",
    version="1.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
register_routes(app)


# 添加 MCP 状态查询端点
@app.get("/api/v1/mcp/status")
async def get_mcp_status():
    """获取 MCP 服务器状态"""
    from app.core.mcp_manager import get_mcp_manager
    manager = get_mcp_manager()
    return {
        "success": True,
        "servers": manager.get_status()
    }


def create_app() -> FastAPI:
    """创建并返回 FastAPI 应用实例"""
    return app


def main():
    """启动 API 服务器"""
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"🚀 启动 HolmesGPT API 服务器")
    logger.info(f"   地址: http://{host}:{port}")
    logger.info(f"   API 文档: http://{host}:{port}/docs")
    logger.info(f"   健康检查: http://{host}:{port}/health")
    logger.info(f"   MCP 状态: http://{host}:{port}/api/v1/mcp/status")
    
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "access": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access"],
                "level": "INFO",
                "propagate": False,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["default"],
        },
    }
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        log_config=log_config,
        use_colors=True
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
