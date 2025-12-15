#!/usr/bin/env python3
"""
DSPy Prompt Enhancer
轻量级集成：只用 DSPy 增强 prompt，保留现有 HolmesGPT + MCP 架构

使用方式：
    from app.core.dspy_enhancer import enhance_prompt, preprocess_query
    
    # 在调用 HolmesGPT 之前，增强 prompt
    enhanced_prompt = enhance_prompt(user_question, SYSTEM_PROMPT)
"""

import os
import logging
import dspy
from typing import Optional, Dict, Tuple
from functools import lru_cache

from app.core.prompts import (
    SYSTEM_PROMPT, 
    FOCUSED_PROMPTS, 
    PROBLEM_TYPE_LABELS,
    get_focused_prompt,
    get_problem_label
)

logger = logging.getLogger(__name__)


# ============================================================================
# 1. 语言模型配置（与 HolmesGPT 统一）
# ============================================================================
# 环境变量:
#   - DEEPSEEK_API_KEY: API Key（必填）
#   - DEEPSEEK_API_BASE: API 地址（可选，默认 https://api.deepseek.com）
#   - DEEPSEEK_MODEL: 模型名称（可选，默认 deepseek-chat）
#
# 部署时通过 Secret 注入环境变量，与 HolmesGPT 共用同一份配置
# ============================================================================

_lm_configured = False


def _ensure_lm_configured():
    """
    确保 LM 已配置（只配置一次）
    
    使用与 HolmesGPT 相同的环境变量配置，部署时只需配置一次
    """
    global _lm_configured
    if _lm_configured:
        return
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("未找到 LLM 配置，请设置环境变量 DEEPSEEK_API_KEY")
    
    api_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    lm = dspy.LM(
        f"openai/{model}",
        api_key=api_key,
        api_base=api_base
    )
    
    dspy.configure(lm=lm)
    _lm_configured = True
    logger.info(f"🤖 DSPy 使用 DeepSeek: {model}")


# ============================================================================
# 2. DSPy Signatures - 轻量级任务定义
# ============================================================================

class QueryClassification(dspy.Signature):
    """
    问题分类：识别用户问题的类型和关键信息
    
    核心 3 Case:
    - disk_full: 磁盘空间耗尽 (No space left on device)
    - pod_crash: 容器崩溃循环 (CrashLoopBackOff)
    - port_conflict: 端口被占用 (Address already in use)
    """
    user_query: str = dspy.InputField(desc="用户的问题或告警信息")
    
    problem_type: str = dspy.OutputField(
        desc="问题类型: disk_full(磁盘满) | pod_crash(容器崩溃/CrashLoopBackOff) | port_conflict(端口占用) | oom_killed(内存溢出) | pending(调度问题) | network(网络问题) | image(镜像问题) | unknown"
    )
    key_resources: str = dspy.OutputField(
        desc="关键资源: 提取的 hostname、namespace、pod、service、port、path 等信息"
    )
    urgency: str = dspy.OutputField(
        desc="紧急程度: critical | high | medium | low"
    )
    suggested_focus: str = dspy.OutputField(
        desc="建议关注点: 应该首先检查什么（一句话）"
    )


class PromptOptimization(dspy.Signature):
    """
    Prompt 优化：根据问题类型生成针对性的诊断指引
    
    不替换 SYSTEM_PROMPT，而是生成额外的 focus hint 添加到用户问题前
    """
    problem_type: str = dspy.InputField(desc="问题类型")
    key_resources: str = dspy.InputField(desc="关键资源")
    suggested_focus: str = dspy.InputField(desc="建议关注点")
    
    diagnostic_hints: str = dspy.OutputField(
        desc="诊断提示: 针对这类问题的具体诊断建议（2-3条）"
    )


# ============================================================================
# 3. 核心功能函数
# ============================================================================

# 问题分类器（缓存模块实例）
_classifier: Optional[dspy.Module] = None

def _get_classifier() -> dspy.Module:
    """获取问题分类器（懒加载）"""
    global _classifier
    if _classifier is None:
        _ensure_lm_configured()
        _classifier = dspy.Predict(QueryClassification)
    return _classifier


def preprocess_query(user_query: str) -> Dict[str, str]:
    """
    预处理用户问题
    
    在调用 HolmesGPT 之前，先理解问题类型和关键信息
    
    Args:
        user_query: 用户的问题
    
    Returns:
        {
            "problem_type": "pod_crash",
            "key_resources": "nginx-pod in namespace production",
            "urgency": "high",
            "suggested_focus": "检查 Pod 日志和事件"
        }
    
    Example:
        >>> info = preprocess_query("我的 Pod nginx-xxx 一直在重启")
        >>> print(info["problem_type"])  # "pod_crash"
    """
    try:
        classifier = _get_classifier()
        result = classifier(user_query=user_query)
        
        return {
            "problem_type": result.problem_type,
            "key_resources": result.key_resources,
            "urgency": result.urgency,
            "suggested_focus": result.suggested_focus
        }
    except Exception as e:
        # 如果 DSPy 调用失败，返回默认值，不影响主流程
        return {
            "problem_type": "unknown",
            "key_resources": "",
            "urgency": "medium",
            "suggested_focus": "使用 kubectl 检查资源状态",
            "error": str(e)
        }


def enhance_query(user_query: str, add_hints: bool = True) -> str:
    """
    增强用户问题
    
    在用户问题前添加诊断提示，帮助 HolmesGPT 更精准地诊断
    
    Args:
        user_query: 原始用户问题
        add_hints: 是否添加诊断提示
    
    Returns:
        增强后的用户问题
    
    Example:
        >>> enhanced = enhance_query("Pod 一直 Pending")
        >>> # 返回: "[调度问题] 建议先检查节点资源和 Pod Events\n\n用户问题：Pod 一直 Pending"
    """
    if not add_hints:
        return user_query
    
    try:
        info = preprocess_query(user_query)
        
        # 如果分类失败，直接返回原问题
        if info.get("error") or info["problem_type"] == "unknown":
            return user_query
        
        # 获取问题类型标签（从 prompts.py 导入）
        type_label = get_problem_label(info["problem_type"])
        
        # 构建增强后的问题
        enhanced = f"""[{type_label}] {info["suggested_focus"]}
关键资源: {info["key_resources"]}

用户问题：{user_query}"""
        
        return enhanced
        
    except Exception:
        # 任何错误都不影响主流程
        return user_query


# get_focused_prompt 已移动到 prompts.py 统一管理


def enhance_system_prompt(user_query: str, base_prompt: str = SYSTEM_PROMPT) -> str:
    """
    增强 System Prompt
    
    根据用户问题类型，在 base_prompt 后添加针对性的诊断指引
    
    Args:
        user_query: 用户问题
        base_prompt: 基础 System Prompt
    
    Returns:
        增强后的 System Prompt
    
    Example:
        >>> enhanced = enhance_system_prompt("Pod OOMKilled", SYSTEM_PROMPT)
        >>> # 返回 SYSTEM_PROMPT + 针对 OOM 的诊断指引
    """
    try:
        info = preprocess_query(user_query)
        focused = get_focused_prompt(info["problem_type"])
        
        if focused:
            return f"{base_prompt}\n{focused}"
        return base_prompt
        
    except Exception:
        return base_prompt


# ============================================================================
# 4. 便捷集成函数
# ============================================================================

def prepare_for_holmes(
    user_query: str,
    system_prompt: str = SYSTEM_PROMPT,
    enhance_mode: str = "both"
) -> Tuple[str, str]:
    """
    为 HolmesGPT 准备增强后的输入
    
    这是最简单的集成方式，只需要在调用 HolmesGPT 之前调用这个函数
    
    Args:
        user_query: 用户问题
        system_prompt: 基础 System Prompt
        enhance_mode: 增强模式
            - "query": 只增强用户问题
            - "prompt": 只增强 System Prompt
            - "both": 两者都增强
            - "none": 不增强（直接返回原值）
    
    Returns:
        (enhanced_query, enhanced_prompt) 元组
    
    Example:
        >>> from app.core.dspy_enhancer import prepare_for_holmes
        >>> query, prompt = prepare_for_holmes("Pod 一直重启", SYSTEM_PROMPT)
        >>> # 然后传给 HolmesGPT
    """
    if enhance_mode == "none":
        return user_query, system_prompt
    
    enhanced_query = user_query
    enhanced_prompt = system_prompt
    
    if enhance_mode in ("query", "both"):
        enhanced_query = enhance_query(user_query)
    
    if enhance_mode in ("prompt", "both"):
        enhanced_prompt = enhance_system_prompt(user_query, system_prompt)
    
    return enhanced_query, enhanced_prompt


# ============================================================================
# 5. 测试
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 测试 DSPy Prompt Enhancer")
    print("=" * 60)
    
    test_queries = [
        "我的 Pod nginx-xxx 一直在 CrashLoopBackOff",
        "服务响应很慢，P99 延迟达到 5 秒",
        "新部署的 Pod 一直 Pending",
        "Pod 被 OOMKilled 了",
    ]
    
    for query in test_queries:
        print(f"\n📝 原始问题: {query}")
        print("-" * 40)
        
        # 预处理
        info = preprocess_query(query)
        print(f"   问题类型: {info['problem_type']}")
        print(f"   紧急程度: {info['urgency']}")
        print(f"   关键资源: {info['key_resources']}")
        print(f"   建议关注: {info['suggested_focus']}")
        
        # 增强问题
        enhanced = enhance_query(query)
        print(f"\n   增强后问题:")
        for line in enhanced.split('\n'):
            print(f"   {line}")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成!")

