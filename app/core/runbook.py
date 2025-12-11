#!/usr/bin/env python3
"""
Runbook Manager
负责加载、合并和管理 Runbooks
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional

from holmes.plugins.runbooks import RunbookCatalog

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """获取项目根目录"""
    # app/core/runbook.py -> 项目根目录
    return Path(__file__).parent.parent.parent


class RunbookManager:
    """Runbook 管理器"""
    
    def __init__(self, runbook_dir: Optional[Path] = None):
        """
        初始化 Runbook 管理器
        
        Args:
            runbook_dir: 自定义 runbook 目录路径，如果为 None 则使用默认路径
        """
        if runbook_dir is None:
            # 默认路径：项目根目录下的 knowledge_base/runbooks
            # K8s 部署时会被 ConfigMap 覆盖
            project_root = get_project_root()
            self.runbook_dir = project_root / "knowledge_base" / "runbooks"
        else:
            self.runbook_dir = Path(runbook_dir)
        
        # 额外的 runbook 目录（用于扩展）
        self.additional_dirs: list[Path] = []
    
    def load_custom_catalog(self) -> Optional[RunbookCatalog]:
        """
        加载自定义 runbook catalog
        
        Returns:
            RunbookCatalog 对象或 None
        """
        catalog_file = self.runbook_dir / "catalog.json"
        
        if not catalog_file.exists():
            logger.debug(f"自定义 runbook catalog 不存在: {catalog_file}")
            return None
        
        try:
            with open(catalog_file, 'r', encoding='utf-8') as f:
                catalog_dict = json.load(f)
            
            # 验证 runbook 文件是否存在
            validated_entries = []
            for entry in catalog_dict.get("catalog", []):
                if "link" in entry:
                    # 检查文件是否存在（支持相对路径和绝对路径）
                    found = False
                    if os.path.isabs(entry["link"]):
                        runbook_path = Path(entry["link"])
                        found = runbook_path.exists()
                    else:
                        # 在主目录和所有额外目录中查找
                        for search_dir in [self.runbook_dir] + self.additional_dirs:
                            runbook_path = search_dir / entry["link"]
                            if runbook_path.exists():
                                found = True
                                break
                    
                    if not found:
                        logger.warning(f"Runbook 文件不存在，跳过: {entry['link']}")
                        continue
                
                validated_entries.append(entry)
            
            if not validated_entries:
                logger.warning(f"没有有效的 runbook 条目在 {catalog_file}")
                return None
            
            # 创建 catalog（只包含有效的条目）
            catalog_dict["catalog"] = validated_entries
            catalog = RunbookCatalog(**catalog_dict)
            logger.info(f"✅ 加载自定义 runbook catalog: {len(catalog.catalog)} 个 runbooks")
            return catalog
        except Exception as e:
            logger.error(f"加载自定义 runbook catalog 失败: {e}", exc_info=True)
            return None
    
    def merge_catalogs(
        self,
        base_catalog: Optional[RunbookCatalog],
        custom_catalog: Optional[RunbookCatalog]
    ) -> Optional[RunbookCatalog]:
        """
        合并内置和自定义 runbook catalogs
        
        Args:
            base_catalog: 内置 runbook catalog
            custom_catalog: 自定义 runbook catalog
        
        Returns:
            合并后的 RunbookCatalog
        """
        if not custom_catalog:
            return base_catalog
        if not base_catalog:
            return custom_catalog
        
        # 合并两个 catalog
        merged_catalog = RunbookCatalog(
            catalog=base_catalog.catalog + custom_catalog.catalog
        )
        logger.info(
            f"合并 runbook catalogs: 内置 {len(base_catalog.catalog)} + "
            f"自定义 {len(custom_catalog.catalog)} = 总计 {len(merged_catalog.catalog)}"
        )
        return merged_catalog
    
    def configure_search_path(self, ai, custom_path: Optional[str] = None):
        """
        配置自定义 runbook 搜索路径（包括主目录和 PVC 目录）
        
        Args:
            ai: AI 实例
            custom_path: 自定义 runbook 路径，如果为 None 则使用 self.runbook_dir
        """
        # 收集所有需要添加的路径
        paths_to_add = []
        
        if custom_path is None:
            paths_to_add.append(str(self.runbook_dir))
        else:
            paths_to_add.append(custom_path)
        
        # 添加 PVC 挂载目录
        for additional_dir in self.additional_dirs:
            paths_to_add.append(str(additional_dir))
        
        try:
            # 查找 runbook toolset
            for toolset in ai.tool_executor.toolsets:
                if toolset.name == "runbook":
                    # 获取 runbook toolset 的配置
                    if not hasattr(toolset, 'config') or toolset.config is None:
                        toolset.config = {}
                    
                    # 配置 additional_search_paths
                    if "additional_search_paths" not in toolset.config:
                        toolset.config["additional_search_paths"] = []
                    
                    for path in paths_to_add:
                        if not Path(path).exists():
                            logger.debug(f"Runbook 目录不存在，跳过: {path}")
                            continue
                        
                        if path not in toolset.config["additional_search_paths"]:
                            toolset.config["additional_search_paths"].append(path)
                        
                        # 更新 RunbookFetcher 的搜索路径
                        for tool in toolset.tools:
                            if hasattr(tool, 'additional_search_paths'):
                                # 初始化 additional_search_paths 如果为 None
                                if tool.additional_search_paths is None:
                                    tool.additional_search_paths = []
                                
                                if path not in tool.additional_search_paths:
                                    tool.additional_search_paths.append(path)
                                
                                # 更新可用 runbooks 列表（扫描目录中的 .md 文件）
                                if hasattr(tool, 'available_runbooks'):
                                    runbook_dir = Path(path)
                                    if runbook_dir.exists():
                                        for file in runbook_dir.glob("*.md"):
                                            file_name = file.name
                                            if file_name not in tool.available_runbooks:
                                                tool.available_runbooks.append(file_name)
                                                logger.debug(f"添加 runbook 到可用列表: {file_name}")
                        
                        logger.info(f"✅ 已配置 runbook 搜索路径: {path}")
                    
                    return
            
            logger.warning("未找到 runbook toolset，无法配置自定义路径")
        except Exception as e:
            logger.error(f"配置自定义 runbook 路径失败: {e}", exc_info=True)

