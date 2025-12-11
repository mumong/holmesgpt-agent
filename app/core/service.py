#!/usr/bin/env python3
"""
HolmesGPT Service
负责 HolmesGPT 的初始化、配置和查询执行
"""
import os
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, Any, Generator, Dict
from datetime import datetime

from rich.console import Console

from holmes.config import Config
from holmes.core.prompt import build_initial_ask_messages
from holmes.plugins.runbooks import RunbookCatalog
from holmes.utils.stream import StreamEvents, StreamMessage

from app.core.runbook import RunbookManager, get_project_root
from app.core.prompts import SYSTEM_PROMPT
from app.core.environment import get_config_file_path, log_environment_info, get_environment

logger = logging.getLogger(__name__)


def create_sse_message_cn(event_type: str, data: Optional[Dict] = None) -> str:
    """
    创建 SSE 消息，支持中文输出（不转义为 Unicode）
    
    Args:
        event_type: 事件类型
        data: 事件数据
    
    Returns:
        SSE 格式的消息字符串
    """
    if data is None:
        data = {}
    # ensure_ascii=False 确保中文不被转义
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_duration(seconds: float) -> str:
    """格式化持续时间为人类可读格式"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


class HolmesService:
    """HolmesGPT 服务类"""
    
    def __init__(self):
        """初始化服务"""
        self.config: Optional[Config] = None
        self.ai: Any = None
        self.console = Console()
        self.runbook_manager = RunbookManager()
        self.merged_catalog: Optional[RunbookCatalog] = None
        self.stream_output: bool = False  # 流式输出配置
    
    def initialize(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_steps: int = 50,
        config_file: Optional[Path] = None
    ) -> Tuple[Config, Any]:
        """
        初始化 HolmesGPT 配置和 AI 实例
        
        Args:
            api_key: LLM API Key
            model: 使用的模型
            max_steps: 最大执行步数
            config_file: 配置文件路径，如果为 None 则使用默认路径
        
        Returns:
            (config, ai_instance) 元组
        """
        # 如果已经初始化，直接返回
        if self.config is not None and self.ai is not None:
            return self.config, self.ai
        
        logger.info("初始化 HolmesGPT 配置...")
        
        # 获取项目根目录
        project_root = get_project_root()
        
        # 获取配置文件路径（自动检测环境）
        if config_file is None:
            config_file, env_name = get_config_file_path(project_root)
            logger.info(f"🔧 运行环境: {env_name}")
        
        # 先读取流式输出配置（在 Config.load_from_file 之前，避免验证错误）
        if config_file.exists():
            self._load_stream_config(config_file)
        else:
            self.stream_output = False
        
        # 确定使用的 API Key
        final_api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not final_api_key:
            raise ValueError(
                "未提供 API Key，请通过参数或环境变量 DEEPSEEK_API_KEY/OPENAI_API_KEY 设置"
            )
        
        # 确定使用的模型
        final_model = model or "deepseek/deepseek-chat"
        
        # 加载配置（需要先创建一个临时配置文件，移除 stream_output 字段）
        if config_file.exists():
            logger.info(f"从配置文件加载: {config_file}")
            # 创建临时配置文件（移除 stream_output 字段）
            import yaml
            import tempfile
            with open(config_file, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)
            
            # 环境变量替换：支持 ${VAR} 和 ${VAR:-default} 语法
            config_dict = self._substitute_env_vars(config_dict)
            logger.info("✅ 环境变量替换完成")
            
            # 移除 stream_output 字段（如果存在）
            temp_config_dict = {k: v for k, v in config_dict.items() if k != "stream_output"}
            
            # 创建临时配置文件（确保使用正确的 YAML 格式）
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as temp_file:
                yaml.dump(temp_config_dict, temp_file, allow_unicode=True, default_flow_style=False, sort_keys=False)
                temp_config_path = Path(temp_file.name)
            
            try:
                self.config = Config.load_from_file(
                    config_file=temp_config_path,
                    api_key=final_api_key,
                    model=final_model,
                    max_steps=max_steps
                )
            finally:
                # 删除临时文件
                temp_config_path.unlink()
        else:
            logger.warning(f"配置文件不存在: {config_file}，使用默认配置")
            self.config = Config(
                api_key=final_api_key,
                model=final_model,
                max_steps=max_steps
            )
        
        # 加载和合并 runbook catalogs
        self._load_runbooks()
        
        # 创建 AI 实例
        logger.info("创建 AI 实例...")
        self.ai = self.config.create_console_toolcalling_llm()
        
        # 配置自定义 runbook 搜索路径
        if self.runbook_manager.runbook_dir.exists():
            self.runbook_manager.configure_search_path(self.ai)
        
        logger.info(f"✅ HolmesGPT 初始化完成，模型: {self.config.model}")
        logger.info(f"📡 输出模式: {'流式输出 (stream)' if self.stream_output else '非流式输出 (invoke)'}")
        
        # 输出加载的资源信息
        self._log_loaded_resources()
        
        return self.config, self.ai
    
    def _load_stream_config(self, config_file: Path):
        """
        从配置文件加载流式输出配置
        
        Args:
            config_file: 配置文件路径
        """
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)
            
            # 读取 stream_output 配置（顶级字段）
            self.stream_output = config_dict.get("stream_output", False)
            
            output_mode = "流式输出 (stream)" if self.stream_output else "非流式输出 (invoke)"
            logger.info(f"📡 输出模式: {output_mode}")
        except Exception as e:
            logger.warning(f"读取流式输出配置失败，使用默认值（非流式）: {e}")
            self.stream_output = False
    
    def _substitute_env_vars(self, obj: Any, depth: int = 0) -> Any:
        """
        递归替换配置中的环境变量占位符
        
        支持语法:
            - ${VAR}         - 使用环境变量 VAR 的值，不存在则保留原字符串
            - ${VAR:-default} - 使用环境变量 VAR 的值，不存在则使用 default
        
        Args:
            obj: 要处理的对象（dict、list 或 str）
            depth: 递归深度（防止无限递归）
        
        Returns:
            替换后的对象
        """
        import re
        
        if depth > 50:  # 防止无限递归
            return obj
        
        if isinstance(obj, dict):
            return {k: self._substitute_env_vars(v, depth + 1) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item, depth + 1) for item in obj]
        elif isinstance(obj, str):
            # 匹配 ${VAR} 或 ${VAR:-default}
            pattern = r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}'
            
            def replace_match(match):
                var_name = match.group(1)
                default_value = match.group(2)  # 可能是 None
                
                env_value = os.environ.get(var_name)
                
                if env_value is not None:
                    logger.debug(f"🔄 环境变量替换: ${{{var_name}}} -> ***")
                    return env_value
                elif default_value is not None:
                    logger.debug(f"🔄 使用默认值: ${{{var_name}}} -> {default_value}")
                    return default_value
                else:
                    # 环境变量不存在且没有默认值，保留原字符串（但记录警告）
                    logger.warning(f"⚠️ 环境变量未设置: {var_name}")
                    return match.group(0)  # 保留原字符串
            
            return re.sub(pattern, replace_match, obj)
        else:
            return obj
    
    def _call_with_stream(self, messages: list) -> Any:
        """
        使用流式输出调用 AI，收集所有事件后返回最终响应
        
        Args:
            messages: 消息列表
        
        Returns:
            与 ai.call() 相同格式的响应对象
        """
        from holmes.utils.stream import StreamEvents
        
        # 从 messages 中提取 system_prompt 和 user_prompt
        system_prompt = ""
        user_prompt = None
        msgs = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
            elif msg.get("role") == "user":
                if user_prompt is None:
                    user_prompt = msg.get("content", "")
                else:
                    msgs.append(msg)
            else:
                msgs.append(msg)
        
        # 调用流式输出
        final_result = None
        final_tool_calls = []
        all_content = []
        
        try:
            for stream_event in self.ai.call_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                msgs=msgs if msgs else None
            ):
                # 收集 AI 消息内容
                if stream_event.event == StreamEvents.AI_MESSAGE:
                    content = stream_event.data.get("content", "")
                    if content:
                        all_content.append(content)
                
                # 收集工具调用结果
                elif stream_event.event == StreamEvents.TOOL_RESULT:
                    tool_data = stream_event.data
                    if tool_data:
                        tool_name = tool_data.get("name") or tool_data.get("tool_name") or "unknown"
                        result_dict = tool_data.get("result", {})
                        
                        if isinstance(result_dict, dict):
                            result_str = result_dict.get("data") or str(result_dict)
                            error_str = result_dict.get("error")
                        else:
                            result_str = str(result_dict)
                            error_str = None
                        
                        tool_info = {
                            "tool_name": tool_name,
                            "result": str(result_str) if result_str else None,
                            "error": str(error_str) if error_str else None
                        }
                        final_tool_calls.append(tool_info)
                
                # 检查是否结束
                elif stream_event.event == StreamEvents.ANSWER_END:
                    final_result = "".join(all_content)
                    break
            
            # 如果没有收到 ANSWER_END，使用收集到的内容
            if final_result is None:
                final_result = "".join(all_content)
            
            # 创建一个类似 response 的对象
            class StreamResponse:
                def __init__(self, result, tool_calls):
                    self.result = result
                    self.tool_calls = tool_calls
            
            return StreamResponse(final_result, final_tool_calls)
            
        except Exception as e:
            logger.error(f"流式输出处理失败: {e}", exc_info=True)
            logger.warning("回退到非流式输出")
            return self.ai.call(messages)
    
    def _load_runbooks(self):
        """加载和合并 runbook catalogs"""
        # 加载自定义 runbook catalog
        custom_catalog = self.runbook_manager.load_custom_catalog()
        
        # 获取内置 runbook catalog
        base_catalog = self.config.get_runbook_catalog()
        
        # 合并 catalogs
        self.merged_catalog = self.runbook_manager.merge_catalogs(
            base_catalog, custom_catalog
        )
    
    def _log_loaded_resources(self):
        """输出加载的资源信息（工具集、MCP 服务器、工具、Runbook）"""
        if not self.ai or not self.ai.tool_executor:
            return
        
        # 1. 输出工具集信息（按类型分类）
        toolsets = self.ai.tool_executor.toolsets
        builtin_toolsets = []
        mcp_servers = []
        
        for toolset in toolsets:
            toolset_class_name = toolset.__class__.__name__.lower()
            is_mcp = (
                'mcp' in toolset_class_name or
                (hasattr(toolset, 'type') and str(toolset.type).lower() == 'mcp') or
                (hasattr(toolset, '__module__') and 'mcp' in toolset.__module__.lower())
            )
            
            if is_mcp:
                mcp_servers.append(toolset)
            else:
                builtin_toolsets.append(toolset)
        
        # 输出内置工具集
        if builtin_toolsets:
            enabled_builtin = [ts for ts in builtin_toolsets if ts.enabled]
            if enabled_builtin:
                successful_toolsets = []
                failed_toolsets = []
                for toolset in enabled_builtin:
                    toolset_tools = []
                    if hasattr(toolset, 'tools') and toolset.tools:
                        toolset_tools = [t.name for t in toolset.tools if hasattr(t, 'name')]
                    registered_tools = [t for t in toolset_tools if t in self.ai.tool_executor.tools_by_name]
                    
                    status_str = str(toolset.status.value) if hasattr(toolset.status, 'value') else str(toolset.status)
                    if status_str == "enabled" and registered_tools:
                        successful_toolsets.append((toolset, len(registered_tools)))
                    else:
                        failed_toolsets.append((toolset, status_str, len(toolset_tools), len(registered_tools)))
                
                if successful_toolsets:
                    logger.info(f"📦 内置工具集 ({len(successful_toolsets)} 个已启用并可用):")
                    for toolset, tool_count in successful_toolsets:
                        logger.info(f"   ✅ {toolset.name} ({tool_count} 个工具)")
                
                if failed_toolsets:
                    logger.warning(f"⚠️  内置工具集 ({len(failed_toolsets)} 个配置但未成功加载):")
                    for toolset, status, total_tools, registered_tools in failed_toolsets:
                        error_msg = getattr(toolset, 'error', '未知错误')
                        logger.warning(f"   ❌ {toolset.name} (状态: {status}, 工具: {registered_tools}/{total_tools}, 错误: {error_msg[:100]})")
        
        # 输出 MCP 服务器
        if mcp_servers:
            enabled_mcp = [ts for ts in mcp_servers if ts.enabled]
            if enabled_mcp:
                logger.info(f"🌐 MCP 服务器 ({len(enabled_mcp)} 个已连接):")
                for toolset in enabled_mcp:
                    tool_count = len(toolset.tools) if hasattr(toolset, 'tools') else 0
                    status_icon = "✅" if toolset.status.value == "enabled" else "❌"
                    logger.info(f"   {status_icon} {toolset.name} ({tool_count} 个工具)")
            else:
                logger.info("🌐 MCP 服务器: 无已启用的服务器")
        else:
            logger.info("🌐 MCP 服务器: 未配置")
        
        # 2. 输出工具统计
        all_tools = list(self.ai.tool_executor.tools_by_name.keys())
        if all_tools:
            tool_counts = {}
            for toolset in toolsets:
                if toolset.enabled and hasattr(toolset, 'tools'):
                    toolset_tools = [t.name for t in toolset.tools if hasattr(t, 'name')]
                    registered_tools = [t for t in toolset_tools if t in self.ai.tool_executor.tools_by_name]
                    if registered_tools:
                        tool_counts[toolset.name] = len(registered_tools)
            
            logger.info(f"🔧 可用工具: 总计 {len(all_tools)} 个（已注册）")
            if tool_counts:
                sorted_counts = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                for toolset_name, count in sorted_counts:
                    logger.info(f"   • {toolset_name}: {count} 个工具")
                if len(tool_counts) > 10:
                    logger.info(f"   ... 还有 {len(tool_counts) - 10} 个工具集")
        
        # 3. 输出 Runbook 信息
        if self.merged_catalog and self.merged_catalog.catalog:
            logger.info(f"📚 Runbook 知识库: {len(self.merged_catalog.catalog)} 个")
            for entry in self.merged_catalog.catalog[:5]:
                if hasattr(entry, 'title'):
                    title = entry.title
                elif isinstance(entry, dict):
                    title = entry.get('title', 'Unknown')
                else:
                    title = str(entry)
                logger.info(f"   • {title}")
            if len(self.merged_catalog.catalog) > 5:
                logger.info(f"   ... 还有 {len(self.merged_catalog.catalog) - 5} 个 runbook")
        else:
            logger.info("📚 Runbook 知识库: 未配置")
    
    def execute_query(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_steps: int = 50
    ) -> dict:
        """
        执行查询并返回结果
        
        Args:
            question: 用户问题
            system_prompt: 自定义系统提示词
            api_key: LLM API Key
            model: 使用的模型
            max_steps: 最大执行步数
        
        Returns:
            包含查询结果的字典
        """
        start_time = datetime.now()
        
        try:
            # 如果参数变化，重新初始化
            if api_key or model or max_steps != 50:
                self.config = None
                self.ai = None
            
            # 初始化（如果还未初始化）
            self.initialize(api_key=api_key, model=model, max_steps=max_steps)
            
            # 确定使用的系统提示词
            final_system_prompt = system_prompt or SYSTEM_PROMPT
            logger.info(f"执行查询: {question[:100]}...")
            
            # 使用合并后的 runbook catalog
            runbook_catalog = (
                self.merged_catalog if self.merged_catalog 
                else self.config.get_runbook_catalog()
            )
            
            # 构建消息
            messages = build_initial_ask_messages(
                console=self.console,
                initial_user_prompt=question,
                file_paths=None,
                tool_executor=self.ai.tool_executor,
                runbooks=runbook_catalog,
                system_prompt_additions=final_system_prompt if final_system_prompt else None
            )
            
            # 根据配置选择调用方式
            if self.stream_output:
                response = self._call_with_stream(messages)
            else:
                response = self.ai.call(messages)
            
            # 提取工具调用信息
            tool_calls = []
            if response and hasattr(response, 'tool_calls') and response.tool_calls:
                if isinstance(response.tool_calls, list) and len(response.tool_calls) > 0:
                    if isinstance(response.tool_calls[0], dict):
                        tool_calls = response.tool_calls
                    else:
                        for tool in response.tool_calls:
                            tool_calls.append({
                                "tool_name": tool.tool_name,
                                "result": str(tool.result) if hasattr(tool, 'result') else None,
                                "error": str(tool.error) if hasattr(tool, 'error') and tool.error else None
                            })
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": True,
                "result": response.result if response else None,
            }
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"执行查询时出错: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
    
    def execute_query_stream(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_steps: int = 50,
        output_format: str = "text"
    ) -> Generator[str, None, None]:
        """
        执行查询并以流式方式返回结果（带耗时统计）
        
        Args:
            question: 用户问题
            system_prompt: 自定义系统提示词
            api_key: LLM API Key
            model: 使用的模型
            max_steps: 最大执行步数
            output_format: 输出格式 - "text"=易读纯文本, "sse"=JSON格式SSE事件
        
        Yields:
            根据 output_format 返回纯文本或 SSE 格式的事件字符串
        """
        # 根据输出格式选择输出函数
        if output_format == "text":
            yield from self._execute_query_stream_text(
                question, system_prompt, api_key, model, max_steps
            )
            return
        
        # ==================== SSE 格式输出 ====================
        total_start_time = time.time()
        tool_calls_collected = []
        timing_stats = {
            "initialization": 0,
            "message_building": 0,
            "llm_iterations": [],
            "tool_calls": [],
            "total": 0
        }
        iteration_count = 0
        current_tool_start_time = None
        current_tool_name = None
        llm_iteration_start_time = None
        
        try:
            # 初始化阶段
            init_start = time.time()
            
            if api_key or model or max_steps != 50:
                self.config = None
                self.ai = None
            
            self.initialize(api_key=api_key, model=model, max_steps=max_steps)
            timing_stats["initialization"] = time.time() - init_start
            
            final_system_prompt = system_prompt or SYSTEM_PROMPT
            
            logger.info("=" * 60)
            logger.info(f"📝 [流式查询] 问题: {question[:100]}...")
            logger.info(f"⏱️  初始化耗时: {format_duration(timing_stats['initialization'])}")
            
            yield create_sse_message_cn("stream_start", {
                "message": "🚀 开始处理查询...",
                "question": question[:100],
                "phase": "initialization",
                "init_time": format_duration(timing_stats["initialization"]),
                "timestamp": datetime.now().isoformat()
            })
            
            # 消息构建阶段
            msg_build_start = time.time()
            
            runbook_catalog = (
                self.merged_catalog if self.merged_catalog 
                else self.config.get_runbook_catalog()
            )
            
            messages = build_initial_ask_messages(
                console=self.console,
                initial_user_prompt=question,
                file_paths=None,
                tool_executor=self.ai.tool_executor,
                runbooks=runbook_catalog,
                system_prompt_additions=final_system_prompt if final_system_prompt else None
            )
            
            timing_stats["message_building"] = time.time() - msg_build_start
            logger.info(f"⏱️  消息构建耗时: {format_duration(timing_stats['message_building'])}")
            
            # 提取 prompts
            sys_prompt = ""
            user_prompt = None
            msgs = []
            
            for msg in messages:
                if msg.get("role") == "system":
                    sys_prompt = msg.get("content", "")
                elif msg.get("role") == "user":
                    if user_prompt is None:
                        user_prompt = msg.get("content", "")
                    else:
                        msgs.append(msg)
                else:
                    msgs.append(msg)
            
            # LLM 调用阶段
            final_content = None
            llm_iteration_start_time = time.time()
            
            logger.info("-" * 60)
            logger.info("🤖 开始 LLM 迭代...")
            
            for stream_event in self.ai.call_stream(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                msgs=msgs if msgs else None
            ):
                event_type = stream_event.event
                event_data = stream_event.data
                
                if event_type == StreamEvents.START_TOOL:
                    tool_name = event_data.get("tool_name", "unknown")
                    tool_id = event_data.get("id", "")
                    current_tool_start_time = time.time()
                    current_tool_name = tool_name
                    
                    logger.info(f"  🔧 [{iteration_count+1}] 开始调用工具: {tool_name}")
                    
                    yield create_sse_message_cn("tool_start", {
                        "tool_name": tool_name,
                        "tool_id": tool_id,
                        "iteration": iteration_count + 1,
                        "message": f"🔧 正在调用工具: {tool_name}",
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif event_type == StreamEvents.TOOL_RESULT:
                    tool_name = event_data.get("name") or event_data.get("tool_name") or current_tool_name or "unknown"
                    result_dict = event_data.get("result", {})
                    description = event_data.get("description", "")
                    
                    tool_duration = 0
                    if current_tool_start_time:
                        tool_duration = time.time() - current_tool_start_time
                        timing_stats["tool_calls"].append({
                            "name": tool_name,
                            "duration": tool_duration,
                            "iteration": iteration_count + 1
                        })
                    
                    if isinstance(result_dict, dict):
                        result_str = result_dict.get("data") or str(result_dict)
                        error_str = result_dict.get("error")
                        status = result_dict.get("status", "unknown")
                    else:
                        result_str = str(result_dict)
                        error_str = None
                        status = "success"
                    
                    tool_info = {
                        "tool_name": tool_name,
                        "result": str(result_str)[:500] if result_str else None,
                        "error": str(error_str) if error_str else None,
                        "status": status,
                        "duration": tool_duration
                    }
                    tool_calls_collected.append(tool_info)
                    
                    status_icon = "✅" if status == "success" else "❌"
                    logger.info(f"  {status_icon} [{iteration_count+1}] 工具完成: {tool_name} (耗时: {format_duration(tool_duration)})")
                    
                    yield create_sse_message_cn("tool_result", {
                        "tool_name": tool_name,
                        "description": description,
                        "status": status,
                        "result_preview": str(result_str)[:300] if result_str else None,
                        "error": str(error_str) if error_str else None,
                        "duration": format_duration(tool_duration),
                        "duration_seconds": round(tool_duration, 2),
                        "iteration": iteration_count + 1,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    current_tool_start_time = None
                    current_tool_name = None
                
                elif event_type == StreamEvents.AI_MESSAGE:
                    content = event_data.get("content", "")
                    reasoning = event_data.get("reasoning", "")
                    
                    if reasoning:
                        # 日志显示完整内容（换行符替换为空格便于阅读）
                        log_reasoning = reasoning.replace('\n', ' ')
                        logger.info(f"  💭 [{iteration_count+1}] AI 推理: {log_reasoning}")
                        yield create_sse_message_cn("ai_reasoning", {
                            "reasoning": reasoning,
                            "iteration": iteration_count + 1,
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    if content:
                        # 日志显示完整内容（换行符替换为空格便于阅读）
                        log_content = content.replace('\n', ' ')
                        logger.info(f"  💬 [{iteration_count+1}] AI 消息: {log_content}")
                        yield create_sse_message_cn("ai_message", {
                            "content": content,
                            "iteration": iteration_count + 1,
                            "timestamp": datetime.now().isoformat()
                        })
                
                elif event_type == StreamEvents.TOKEN_COUNT:
                    if llm_iteration_start_time:
                        iteration_duration = time.time() - llm_iteration_start_time
                        timing_stats["llm_iterations"].append({
                            "iteration": iteration_count + 1,
                            "duration": iteration_duration
                        })
                        logger.info(f"  ⏱️  [{iteration_count+1}] 迭代完成，耗时: {format_duration(iteration_duration)}")
                    
                    iteration_count += 1
                    llm_iteration_start_time = time.time()
                    
                    metadata = event_data.get("metadata", {})
                    usage = metadata.get("usage", {})
                    if usage:
                        yield create_sse_message_cn("token_count", {
                            "usage": usage,
                            "iteration": iteration_count,
                            "elapsed_time": format_duration(time.time() - total_start_time),
                            "timestamp": datetime.now().isoformat()
                        })
                
                elif event_type == StreamEvents.CONVERSATION_HISTORY_COMPACTED:
                    logger.info(f"  📦 [{iteration_count+1}] 对话历史已压缩")
                    yield create_sse_message_cn("history_compacted", {
                        "message": "📦 对话历史已压缩以适应上下文窗口",
                        "iteration": iteration_count + 1,
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif event_type == StreamEvents.ANSWER_END:
                    final_content = event_data.get("content", "")
                    
                    if llm_iteration_start_time:
                        iteration_duration = time.time() - llm_iteration_start_time
                        timing_stats["llm_iterations"].append({
                            "iteration": iteration_count + 1,
                            "duration": iteration_duration
                        })
                    
                    logger.info(f"  🎯 [{iteration_count+1}] 收到最终答案")
                    break
                
                elif event_type == StreamEvents.ERROR:
                    error_msg = event_data.get("msg", "未知错误")
                    logger.error(f"  ❌ [{iteration_count+1}] 错误: {error_msg}")
                    yield create_sse_message_cn("error", {
                        "error": error_msg,
                        "iteration": iteration_count + 1,
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif event_type == StreamEvents.APPROVAL_REQUIRED:
                    pending = event_data.get("pending_approvals", [])
                    yield create_sse_message_cn("approval_required", {
                        "pending_approvals": pending,
                        "message": "⚠️ 需要用户批准以下操作",
                        "iteration": iteration_count + 1,
                        "timestamp": datetime.now().isoformat()
                    })
            
            # 统计汇总
            timing_stats["total"] = time.time() - total_start_time
            total_llm_time = sum(it["duration"] for it in timing_stats["llm_iterations"])
            total_tool_time = sum(tc["duration"] for tc in timing_stats["tool_calls"])
            slowest_tools = sorted(timing_stats["tool_calls"], key=lambda x: x["duration"], reverse=True)[:5]
            
            logger.info("-" * 60)
            logger.info("📊 性能统计:")
            logger.info(f"  ├─ 总耗时: {format_duration(timing_stats['total'])}")
            logger.info(f"  ├─ 初始化: {format_duration(timing_stats['initialization'])} ({timing_stats['initialization']/timing_stats['total']*100:.1f}%)")
            logger.info(f"  ├─ 消息构建: {format_duration(timing_stats['message_building'])} ({timing_stats['message_building']/timing_stats['total']*100:.1f}%)")
            logger.info(f"  ├─ LLM 迭代: {format_duration(total_llm_time)} ({total_llm_time/timing_stats['total']*100:.1f}%) - {len(timing_stats['llm_iterations'])} 次")
            logger.info(f"  └─ 工具调用: {format_duration(total_tool_time)} ({total_tool_time/timing_stats['total']*100:.1f}%) - {len(timing_stats['tool_calls'])} 次")
            
            if slowest_tools:
                logger.info("  🐢 最慢的工具调用:")
                for i, tool in enumerate(slowest_tools, 1):
                    logger.info(f"     {i}. {tool['name']}: {format_duration(tool['duration'])}")
            
            logger.info("=" * 60)
            
            yield create_sse_message_cn("stream_end", {
                "success": True,
                "result": final_content
            })
            
            logger.info(f"✅ 查询完成，总耗时: {format_duration(timing_stats['total'])}")
            
        except Exception as e:
            total_time = time.time() - total_start_time
            logger.error(f"❌ 执行查询时出错 (耗时 {format_duration(total_time)}): {e}", exc_info=True)
            yield create_sse_message_cn("error", {
                "success": False,
                "error": str(e)
            })
    
    def _execute_query_stream_text(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_steps: int = 50
    ) -> Generator[str, None, None]:
        """
        执行查询并以易读的纯文本格式流式返回结果
        专为 curl 等命令行工具优化
        """
        total_start_time = time.time()
        tool_calls_collected = []
        timing_stats = {
            "initialization": 0,
            "message_building": 0,
            "llm_iterations": [],
            "tool_calls": [],
            "total": 0
        }
        iteration_count = 0
        current_tool_start_time = None
        current_tool_name = None
        llm_iteration_start_time = None
        
        def emit(text: str) -> str:
            return f"{text}\n"
        
        try:
            init_start = time.time()
            
            if api_key or model or max_steps != 50:
                self.config = None
                self.ai = None
            
            self.initialize(api_key=api_key, model=model, max_steps=max_steps)
            timing_stats["initialization"] = time.time() - init_start
            
            final_system_prompt = system_prompt or SYSTEM_PROMPT
            
            yield emit("=" * 70)
            yield emit(f"🔍 HolmesGPT 流式查询")
            yield emit("=" * 70)
            yield emit(f"📝 问题: {question[:100]}")
            yield emit(f"⏱️  初始化: {format_duration(timing_stats['initialization'])}")
            yield emit("-" * 70)
            yield emit("")
            
            msg_build_start = time.time()
            
            runbook_catalog = (
                self.merged_catalog if self.merged_catalog 
                else self.config.get_runbook_catalog()
            )
            
            messages = build_initial_ask_messages(
                console=self.console,
                initial_user_prompt=question,
                file_paths=None,
                tool_executor=self.ai.tool_executor,
                runbooks=runbook_catalog,
                system_prompt_additions=final_system_prompt if final_system_prompt else None
            )
            
            timing_stats["message_building"] = time.time() - msg_build_start
            
            sys_prompt = ""
            user_prompt = None
            msgs = []
            
            for msg in messages:
                if msg.get("role") == "system":
                    sys_prompt = msg.get("content", "")
                elif msg.get("role") == "user":
                    if user_prompt is None:
                        user_prompt = msg.get("content", "")
                    else:
                        msgs.append(msg)
                else:
                    msgs.append(msg)
            
            final_content = None
            llm_iteration_start_time = time.time()
            
            yield emit("🤖 开始 LLM 迭代...")
            yield emit("")
            
            for stream_event in self.ai.call_stream(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                msgs=msgs if msgs else None
            ):
                event_type = stream_event.event
                event_data = stream_event.data
                
                if event_type == StreamEvents.START_TOOL:
                    tool_name = event_data.get("tool_name", "unknown")
                    current_tool_start_time = time.time()
                    current_tool_name = tool_name
                    yield emit(f"  🔧 [{iteration_count+1}] 调用工具: {tool_name}")
                
                elif event_type == StreamEvents.TOOL_RESULT:
                    tool_name = event_data.get("name") or event_data.get("tool_name") or current_tool_name or "unknown"
                    result_dict = event_data.get("result", {})
                    description = event_data.get("description", "")
                    
                    tool_duration = 0
                    if current_tool_start_time:
                        tool_duration = time.time() - current_tool_start_time
                        timing_stats["tool_calls"].append({
                            "name": tool_name,
                            "duration": tool_duration,
                            "iteration": iteration_count + 1
                        })
                    
                    if isinstance(result_dict, dict):
                        status = result_dict.get("status", "unknown")
                        error_str = result_dict.get("error")
                    else:
                        status = "success"
                        error_str = None
                    
                    tool_info = {
                        "tool_name": tool_name,
                        "status": status,
                        "duration": tool_duration
                    }
                    tool_calls_collected.append(tool_info)
                    
                    status_icon = "✅" if status == "success" else "❌"
                    yield emit(f"  {status_icon} [{iteration_count+1}] 完成: {tool_name} ({format_duration(tool_duration)})")
                    
                    if description:
                        yield emit(f"       📋 {description[:60]}")
                    
                    if error_str:
                        yield emit(f"       ⚠️ 错误: {error_str[:60]}")
                    
                    current_tool_start_time = None
                    current_tool_name = None
                
                elif event_type == StreamEvents.AI_MESSAGE:
                    content = event_data.get("content", "")
                    reasoning = event_data.get("reasoning", "")
                    
                    if reasoning:
                        yield emit(f"  💭 [{iteration_count+1}] 推理:")
                        # 完整输出推理内容
                        for line in reasoning.split('\n'):
                            yield emit(f"     {line}")
                    
                    if content:
                        yield emit(f"  💬 [{iteration_count+1}] AI:")
                        # 完整输出 AI 消息内容
                        for line in content.split('\n'):
                            yield emit(f"     {line}")
                
                elif event_type == StreamEvents.TOKEN_COUNT:
                    if llm_iteration_start_time:
                        iteration_duration = time.time() - llm_iteration_start_time
                        timing_stats["llm_iterations"].append({
                            "iteration": iteration_count + 1,
                            "duration": iteration_duration
                        })
                    
                    iteration_count += 1
                    llm_iteration_start_time = time.time()
                    
                    metadata = event_data.get("metadata", {})
                    usage = metadata.get("usage", {})
                    elapsed = format_duration(time.time() - total_start_time)
                    
                    if usage:
                        tokens = usage.get("total_tokens", 0)
                        yield emit(f"  📊 [{iteration_count}] 迭代完成 | Token: {tokens} | 已用时: {elapsed}")
                    yield emit("")
                
                elif event_type == StreamEvents.CONVERSATION_HISTORY_COMPACTED:
                    yield emit(f"  📦 [{iteration_count+1}] 对话历史已压缩")
                
                elif event_type == StreamEvents.ANSWER_END:
                    final_content = event_data.get("content", "")
                    
                    if llm_iteration_start_time:
                        iteration_duration = time.time() - llm_iteration_start_time
                        timing_stats["llm_iterations"].append({
                            "iteration": iteration_count + 1,
                            "duration": iteration_duration
                        })
                    break
                
                elif event_type == StreamEvents.ERROR:
                    error_msg = event_data.get("msg", "未知错误")
                    yield emit(f"  ❌ 错误: {error_msg}")
            
            timing_stats["total"] = time.time() - total_start_time
            total_llm_time = sum(it["duration"] for it in timing_stats["llm_iterations"])
            total_tool_time = sum(tc["duration"] for tc in timing_stats["tool_calls"])
            slowest_tools = sorted(timing_stats["tool_calls"], key=lambda x: x["duration"], reverse=True)[:5]
            
            yield emit("-" * 70)
            yield emit("")
            yield emit("🎯 最终答案:")
            yield emit("-" * 50)
            
            if final_content:
                for line in final_content.split('\n'):
                    yield emit(f"  {line}")
            
            yield emit("-" * 50)
            yield emit("")
            yield emit("📊 性能统计:")
            yield emit(f"  ├─ 总耗时: {format_duration(timing_stats['total'])}")
            yield emit(f"  ├─ 初始化: {format_duration(timing_stats['initialization'])}")
            yield emit(f"  ├─ 消息构建: {format_duration(timing_stats['message_building'])}")
            
            if timing_stats['total'] > 0:
                llm_pct = total_llm_time / timing_stats['total'] * 100
                tool_pct = total_tool_time / timing_stats['total'] * 100
            else:
                llm_pct = tool_pct = 0
            
            yield emit(f"  ├─ LLM 迭代: {format_duration(total_llm_time)} ({llm_pct:.1f}%) - {len(timing_stats['llm_iterations'])} 次")
            yield emit(f"  └─ 工具调用: {format_duration(total_tool_time)} ({tool_pct:.1f}%) - {len(timing_stats['tool_calls'])} 次")
            
            if slowest_tools:
                yield emit("")
                yield emit("  🐢 最慢的工具:")
                for i, tool in enumerate(slowest_tools, 1):
                    yield emit(f"     {i}. {tool['name']}: {format_duration(tool['duration'])}")
            
            yield emit("")
            yield emit("=" * 70)
            yield emit(f"✅ 完成! 总耗时: {format_duration(timing_stats['total'])}")
            yield emit("=" * 70)
            
        except Exception as e:
            total_time = time.time() - total_start_time
            logger.error(f"❌ 执行查询时出错: {e}", exc_info=True)
            yield emit("")
            yield emit(f"❌ 错误: {str(e)}")
            yield emit(f"⏱️  耗时: {format_duration(total_time)}")
    
    def get_tools_info(self) -> dict:
        """获取可用工具信息"""
        self.initialize()
        
        tools = list(self.ai.tool_executor.tools_by_name.keys())
        toolsets = [{
            "name": toolset.name,
            "enabled": toolset.enabled,
            "status": toolset.status.value if hasattr(toolset.status, 'value') else str(toolset.status)
        } for toolset in self.ai.tool_executor.toolsets]
        
        return {
            "success": True,
            "total_tools": len(tools),
            "tools": sorted(tools),
            "toolsets": toolsets
        }
    
    def health_check(self) -> dict:
        """健康检查"""
        try:
            self.initialize()
            return {
                "status": "healthy",
                "config_loaded": self.config is not None,
                "ai_initialized": self.ai is not None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 全局服务实例（单例模式）
_global_service: Optional[HolmesService] = None


def get_service() -> HolmesService:
    """获取全局服务实例"""
    global _global_service
    if _global_service is None:
        _global_service = HolmesService()
    return _global_service

