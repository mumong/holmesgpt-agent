#!/usr/bin/env python3
"""
API Models - 简化的数据模型

新 API 设计不再需要复杂的请求模型，
这里只保留响应模型供内部使用。
"""
from typing import Optional, List
from pydantic import BaseModel


class ToolCallInfo(BaseModel):
    """工具调用信息"""
    tool_name: str
    result: Optional[str] = None
    error: Optional[str] = None


class QueryResult(BaseModel):
    """查询结果（内部使用）"""
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[ToolCallInfo] = []
