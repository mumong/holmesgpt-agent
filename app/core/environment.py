#!/usr/bin/env python3
"""
环境检测模块
自动检测运行环境（Kubernetes 集群内/外）并选择对应的配置
"""

import os
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def is_running_in_kubernetes() -> bool:
    """
    检测是否在 Kubernetes 集群内运行
    
    检测方法：
    1. 检查 ServiceAccount token 文件是否存在
    2. 检查 KUBERNETES_SERVICE_HOST 环境变量
    
    Returns:
        True 如果在 Kubernetes 集群内运行
    """
    # 方法 1: 检查 ServiceAccount token
    sa_token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    if sa_token_path.exists():
        return True
    
    # 方法 2: 检查 KUBERNETES_SERVICE_HOST 环境变量
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return True
    
    return False


def get_environment() -> str:
    """
    获取当前运行环境名称
    
    Returns:
        "kubernetes" 或 "local"
    """
    if is_running_in_kubernetes():
        return "kubernetes"
    return "local"


def get_config_file_path(project_root: Path) -> Tuple[Path, str]:
    """
    根据环境自动选择配置文件
    
    优先级：
    1. 环境变量 CONFIG_FILE 指定的路径
    2. Kubernetes 环境: config/config.k8s.yaml
    3. 本地环境: config/config.yaml
    
    Args:
        project_root: 项目根目录
    
    Returns:
        (配置文件路径, 环境名称) 元组
    """
    config_dir = project_root / "config"
    
    # 1. 检查环境变量
    env_config = os.getenv("CONFIG_FILE")
    if env_config:
        config_path = Path(env_config)
        if config_path.is_absolute():
            if config_path.exists():
                logger.info(f"📄 使用环境变量指定的配置: {config_path}")
                return config_path, "custom"
        else:
            # 相对路径，相对于项目根目录
            config_path = project_root / env_config
            if config_path.exists():
                logger.info(f"📄 使用环境变量指定的配置: {config_path}")
                return config_path, "custom"
        logger.warning(f"环境变量 CONFIG_FILE 指定的文件不存在: {env_config}")
    
    # 2. 检测运行环境
    environment = get_environment()
    
    if environment == "kubernetes":
        # Kubernetes 环境优先使用 k8s 配置
        k8s_config = config_dir / "config.k8s.yaml"
        if k8s_config.exists():
            logger.info(f"🐳 检测到 Kubernetes 环境，使用集群内配置: {k8s_config}")
            return k8s_config, "kubernetes"
        else:
            logger.warning(f"Kubernetes 环境但 config.k8s.yaml 不存在，使用默认配置")
    
    # 3. 默认使用本地配置
    local_config = config_dir / "config.yaml"
    logger.info(f"💻 使用本地配置: {local_config}")
    return local_config, "local"


def log_environment_info():
    """输出环境信息日志"""
    env = get_environment()
    
    logger.info("=" * 50)
    logger.info("📍 运行环境信息")
    logger.info("=" * 50)
    
    if env == "kubernetes":
        logger.info(f"   环境: Kubernetes 集群内")
        logger.info(f"   K8s Host: {os.getenv('KUBERNETES_SERVICE_HOST', 'N/A')}")
        logger.info(f"   K8s Port: {os.getenv('KUBERNETES_SERVICE_PORT', 'N/A')}")
        
        # 尝试获取 Pod 信息
        pod_name = os.getenv("POD_NAME", os.getenv("HOSTNAME", "N/A"))
        pod_namespace = os.getenv("POD_NAMESPACE", "N/A")
        logger.info(f"   Pod: {pod_name}")
        logger.info(f"   Namespace: {pod_namespace}")
    else:
        logger.info(f"   环境: 本地开发/集群外部")
        logger.info(f"   主机: {os.getenv('HOSTNAME', 'localhost')}")
    
    logger.info("=" * 50)

