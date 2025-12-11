#!/usr/bin/env python3
"""
配置加载器 - 从 .holmes/config.yaml 读取 Elasticsearch MCP 配置
"""

import yaml
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def load_elasticsearch_config(config_file: Optional[Path] = None) -> Dict[str, Any]:
    """
    从 config.yaml 加载 Elasticsearch 配置
    
    Args:
        config_file: 配置文件路径，如果为 None 则使用默认路径
        
    Returns:
        包含配置的字典，包含: es_url, es_api_key, bridge_port, bridge_host
    """
    # 确定配置文件路径
    if config_file is None:
        # 默认路径：项目根目录下的 .holmes/config.yaml
        current_dir = Path(__file__).parent.parent.parent
        config_file = current_dir / ".holmes" / "config.yaml"
    
    if not config_file.exists():
        logger.warning(f"配置文件不存在: {config_file}")
        return {}
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        
        # 提取 elasticsearch MCP 服务器配置
        mcp_servers = config_dict.get("mcp_servers", {})
        elasticsearch_config = mcp_servers.get("elasticsearch", {})
        
        if not elasticsearch_config:
            logger.warning("未找到 elasticsearch 配置")
            return {}
        
        # 提取配置
        config_section = elasticsearch_config.get("config", {})
        
        # 提取 Elasticsearch 连接信息
        es_url = config_section.get("es_url") or config_section.get("url")
        username = config_section.get("username")
        password = config_section.get("password")
        es_api_key = config_section.get("es_api_key")
        es_ca_cert = config_section.get("es_ca_cert")
        
        # 提取桥接服务器配置
        bridge_port = config_section.get("bridge_port", 8082)
        bridge_host = config_section.get("bridge_host", "0.0.0.0")
        
        result = {
            "es_url": es_url,
            "es_username": username,
            "es_password": password,
            "es_api_key": es_api_key,
            "es_ca_cert": es_ca_cert,
            "bridge_port": bridge_port,
            "bridge_host": bridge_host,
            "enabled": elasticsearch_config.get("enabled", False)
        }
        
        # 过滤掉 None 值
        result = {k: v for k, v in result.items() if v is not None}
        
        return result
        
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}", exc_info=True)
        return {}


if __name__ == "__main__":
    # 测试配置加载
    logging.basicConfig(level=logging.INFO)
    config = load_elasticsearch_config()
    print("配置:", config)

