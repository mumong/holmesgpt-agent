#!/usr/bin/env python3
"""
API Routes
定义所有 API 端点和路由处理逻辑
"""
import logging
from datetime import datetime
from typing import Generator

from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.core.service import get_service
from app.api.models import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)


def register_routes(app):
    """
    注册所有 API 路由到 FastAPI 应用
    
    Args:
        app: FastAPI 应用实例
    """
    
    @app.get("/")
    async def root():
        """根端点，返回 API 信息"""
        return {
            "service": "HolmesGPT API Server",
            "version": "1.0.0",
            "status": "running",
            "endpoints": {
                "query": "/api/v1/query",
                "query_stream": "/api/v1/query/stream",
                "health": "/health",
                "tools": "/api/v1/tools"
            }
        }
    
    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        service = get_service()
        return service.health_check()
    
    @app.get("/api/v1/tools")
    async def list_tools():
        """列出所有可用的工具"""
        try:
            service = get_service()
            return service.get_tools_info()
        except Exception as e:
            logger.error(f"获取工具列表失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/v1/query", response_model=QueryResponse)
    async def query(request: QueryRequest):
        """
        执行查询的主要端点
        
        接收用户问题，执行 HolmesGPT 分析，返回结果
        """
        logger.info(f"收到查询请求: {request.question[:100]}...")
        
        try:
            service = get_service()
            result = service.execute_query(
                question=request.question,
                system_prompt=request.system_prompt,
                api_key=request.api_key,
                model=request.model,
                max_steps=request.max_steps
            )
            
            # 转换为 QueryResponse 模型
            response = QueryResponse(**result)
            
            if not response.success:
                raise HTTPException(status_code=500, detail=response.error)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"处理查询请求时出错: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/v1/query/stream")
    async def query_stream(request: QueryRequest):
        """
        流式执行查询的端点
        
        接收用户问题，执行 HolmesGPT 分析，以流式方式返回结果。
        
        输出格式（通过 output_format 参数控制）：
        - "text" (默认): 易读的纯文本格式，适合 curl 直接查看
        - "sse": JSON 格式的 SSE 事件，适合程序解析
        
        使用示例（推荐，易读输出）:
        curl -N -X POST "http://localhost:8000/api/v1/query/stream" \\
          -H "Content-Type: application/json" \\
          -d '{"question": "我的 Pod 一直在重启"}'
        
        使用示例（SSE 格式，程序解析）:
        curl -N -X POST "http://localhost:8000/api/v1/query/stream" \\
          -H "Content-Type: application/json" \\
          -d '{"question": "我的 Pod 一直在重启", "output_format": "sse"}'
        """
        output_format = request.output_format or "text"
        logger.info(f"收到流式查询请求 [格式: {output_format}]: {request.question[:100]}...")
        
        def generate_stream() -> Generator[str, None, None]:
            """生成流式输出"""
            try:
                service = get_service()
                yield from service.execute_query_stream(
                    question=request.question,
                    system_prompt=request.system_prompt,
                    api_key=request.api_key,
                    model=request.model,
                    max_steps=request.max_steps,
                    output_format=output_format
                )
            except Exception as e:
                logger.error(f"流式查询出错: {e}", exc_info=True)
                if output_format == "sse":
                    import json
                    yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                else:
                    yield f"\n❌ 错误: {str(e)}\n"
        
        # 根据输出格式设置不同的 Content-Type
        if output_format == "sse":
            media_type = "text/event-stream"
        else:
            media_type = "text/plain; charset=utf-8"
        
        return StreamingResponse(
            generate_stream(),
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    @app.post("/api/v1/query/async")
    async def query_async(request: QueryRequest, background_tasks: BackgroundTasks):
        """
        异步执行查询（立即返回，后台执行）
        
        注意：这是一个简化版本，实际生产环境应该使用任务队列（如 Celery）
        """
        # 生成任务 ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        logger.info(f"收到异步查询请求 [Task ID: {task_id}]: {request.question[:100]}...")
        
        try:
            service = get_service()
            result = service.execute_query(
                question=request.question,
                system_prompt=request.system_prompt,
                api_key=request.api_key,
                model=request.model,
                max_steps=request.max_steps
            )
            
            return {
                "task_id": task_id,
                "status": "completed" if result.get("success") else "failed",
                "result": result
            }
        except Exception as e:
            logger.error(f"处理异步查询请求时出错: {e}", exc_info=True)
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e)
            }

