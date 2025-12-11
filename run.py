#!/usr/bin/env python3
"""
K8s AIOps Copilot 启动入口
简化的启动脚本，用于启动 API 服务
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.main import main

if __name__ == "__main__":
    main()

