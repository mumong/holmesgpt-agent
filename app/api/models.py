#!/usr/bin/env python3
"""
API Models
定义所有 API 请求和响应的数据模型
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """查询请求模型"""
    question: str = Field(..., description="用户的问题或查询内容")
    system_prompt: Optional[str] = Field(None, description="自定义系统提示词，如果不提供则使用默认的")
    max_steps: Optional[int] = Field(20, description="最大执行步数", ge=1, le=100)
    model: Optional[str] = Field(None, description="使用的 LLM 模型，如果不提供则使用配置中的默认模型")
    api_key: Optional[str] = Field(None, description="LLM API Key，如果不提供则使用环境变量中的")
    output_format: Optional[Literal["text", "sse"]] = Field(
        "text", 
        description="流式输出格式: 'text'=易读纯文本(默认,推荐curl使用), 'sse'=JSON格式SSE事件"
    )


class ToolCallInfo(BaseModel):
    """工具调用信息"""
    tool_name: str
    result: Optional[str] = None
    error: Optional[str] = None


class QueryResponse(BaseModel):
    """查询响应模型"""
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[ToolCallInfo] = []
    execution_time: float
    timestamp: str

