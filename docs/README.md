# HolmesGPT 智能运维 Copilot

> 基于 HolmesGPT 框架的 Kubernetes 智能运维助手，通过 AI 驱动的多数据源联动分析，快速诊断和解决集群问题。

## 🌟 核心特点

### 1. **智能多数据源联动分析**
- **Prometheus**: 指标数据查询（CPU、内存、网络等）
- **Grafana**: 仪表盘管理和可视化数据查询
- **Elasticsearch**: 日志搜索和分析
- **Deepflow**: 分布式追踪和性能分析
- **Kubernetes**: 集群资源管理和操作

### 2. **可扩展的 MCP 工具集成**
- **内置工具集**: Prometheus、Kubernetes、Docker、Helm 等开箱即用
- **第三方 MCP 桥接**: 轻松集成 npm 包形式的 MCP 服务器（如 Elasticsearch）
- **自定义工具**: 支持开发自定义 MCP 服务器

### 3. **Runbook 知识库集成**
- 基于 RAG 的运维知识库检索
- 标准化的排查手册和最佳实践
- 自动关联知识库内容与实时数据

### 4. **结构化诊断输出**
- **问题摘要**: 清晰描述当前问题
- **根本原因分析 (RCA)**: 基于多数据源的深度分析
- **证据链**: 提供指标、日志、追踪等完整证据
- **行动方案**: 分步骤的可执行建议

## 🚀 快速开始

### 前置要求

- Python 3.12+
- DeepSeek 或 OpenAI API Key
- Kubernetes 集群访问权限（可选）

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd robusta

# 安装依赖
pip install -r requirements_api.txt

# 设置 API Key
export DEEPSEEK_API_KEY=your-api-key-here
# 或
export OPENAI_API_KEY=your-api-key-here
```

### 启动服务

```bash
# API 服务器模式（推荐）
python api_server.py

# 服务器信息
# - 默认地址: http://0.0.0.0:8000
# - API 文档: http://localhost:8000/docs
# - 健康检查: http://localhost:8000/health
```

### 发送请求

```bash

curl -N -X POST "http://localhost:8000/api/v1/query/stream" \
  -H "Content-Type: application/json" \
  -d '{"question": "运行测试工具"}'


curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "我的 Pod 一直在重启，帮我分析一下原因",
    "max_steps": 50
  }' | jq .

curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "运行测试工具。",
    "max_steps": 50
  }'| jq .

curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "计算过去1小时集群的内存使用率",
    "max_steps": 50
  }'| jq .
```

## 📋 核心功能

### 1. 智能问题诊断

**示例问题**:
- "我的 Pod 一直在重启"
- "为什么 api-server 这个服务最近响应很慢？"
- "帮我查一下 observability-mysql 的 CPU 和内存使用情况"
- "集群有什么问题？"

**工作流程**:
1. **异常发现**: 从用户问题或 Alertmanager 告警中提取关键信息
2. **智能分析**: 联动 Prometheus、Elasticsearch、Deepflow 等多数据源
3. **知识库检索**: 结合 Runbook 知识库进行推理
4. **结构化输出**: 提供问题摘要、RCA、证据链和行动方案

### 2. MCP 工具集成

#### 内置工具集

在 `.holmes/config.yaml` 中配置：

```yaml
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://localhost:9090"
  
  kubernetes/core:
    enabled: true
  
  grafana/core:
    enabled: true
    config:
      grafana_url: "http://localhost:3000"
```

#### 第三方 MCP 工具

支持通过 HTTP/SSE 协议集成第三方 MCP 服务器：

```yaml
mcp_servers:
  elasticsearch:
    description: "Elasticsearch 搜索和分析工具集"
    config:
      url: "http://localhost:8082/sse"
      mode: "sse"
      es_url: "http://your-elasticsearch:9200"
      username: "elastic"
      password: "password"
    enabled: true
```

**快速集成新工具**:
```bash
# 参考 mcp_bridges/elasticsearch 示例
cd mcp_bridges
mkdir my_tool
# 创建 bridge_server.py 和 config_loader.py
```

### 3. Runbook 知识库

**添加 Runbook**:
```bash
# 1. 创建文件
vim knowledge_base/runbooks/my-runbook.md

# 2. 更新目录
vim knowledge_base/runbooks/catalog.json

# 3. 验证
python3 scripts/validate_runbooks.py
```

**知识库特点**:
- 自动检索相关排查手册
- 结合实时数据提供建议
- 优先使用知识库中的操作步骤

## 📁 项目结构

```
robusta/
├── api_server.py              # FastAPI 应用入口
├── api_routes.py              # API 路由定义
├── api_models.py              # API 数据模型
├── holmes_service.py          # HolmesGPT 服务层
├── runbook_manager.py         # Runbook 管理器
├── prompt.py                  # 系统提示词（AIOps Agent 定义）
├── roubusta.py                # 命令行模式入口
├── test_mcp_server_simple.py  # 测试 MCP 服务器示例
│
├── .holmes/
│   └── config.yaml            # HolmesGPT 配置文件
│
├── knowledge_base/
│   └── runbooks/              # Runbook 知识库
│       ├── catalog.json       # 知识库目录
│       └── *.md               # 排查手册文件
│
├── mcp_bridges/               # 第三方 MCP 桥接服务
│   ├── README.md              # 桥接服务说明
│   └── elasticsearch/         # Elasticsearch MCP 桥接示例
│       ├── bridge_server.py   # 桥接服务器（可直接运行）
│       ├── config_loader.py   # 配置加载器
│       └── requirements.txt   # Python 依赖
│
└── docs/                      # 文档目录
    ├── README.md              # 本文件
    ├── USAGE_GUIDE.md         # 使用指南
    ├── MCP_INTEGRATION_GUIDE.md    # MCP 工具集成指南
    └── RUNBOOK_INTEGRATION_GUIDE.md # Runbook 集成指南
```

## 🔧 配置说明

### 核心配置文件

`.holmes/config.yaml` - HolmesGPT 主配置文件

```yaml
# 工具集配置
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://localhost:9090"

# MCP 服务器配置
mcp_servers:
  elasticsearch:
    description: "Elasticsearch 搜索和分析工具集"
    config:
      url: "http://localhost:8082/sse"
      mode: "sse"
      es_url: "http://your-elasticsearch:9200"
    enabled: true

# Runbook 知识库配置
runbooks:
  enabled: true
  catalog_path: "knowledge_base/runbooks/catalog.json"
```

### 环境变量

```bash
# LLM API Key
export DEEPSEEK_API_KEY=your-api-key
# 或
export OPENAI_API_KEY=your-api-key

# 可选：自定义模型
export HOLMES_MODEL=deepseek/deepseek-chat
```

## 📚 文档导航

### 使用指南
- **[使用指南](./USAGE_GUIDE.md)** - 快速开始、运行方式、API 使用、常见示例

### 集成指南
- **[MCP 工具集成指南](./MCP_INTEGRATION_GUIDE.md)** - 集成内置和第三方 MCP 工具的标准流程
- **[Runbook 知识库集成指南](./RUNBOOK_INTEGRATION_GUIDE.md)** - 集成知识库和排查手册

### 开发指南
- **[MCP 桥接服务](../mcp_bridges/README.md)** - 如何集成第三方 MCP 工具（npm 包）

## 🎯 典型使用场景

### 1. Pod 重启问题诊断

**问题**: "我的 Pod 一直在重启"

**系统行为**:
1. 查询 Prometheus 获取重启次数和资源使用情况
2. 查询 Elasticsearch 获取错误日志
3. 查询 Kubernetes 获取 Pod 状态和事件
4. 检索 Runbook 知识库获取相关排查手册
5. 综合分析，提供根本原因和解决方案

### 2. 服务性能问题分析

**问题**: "为什么 api-server 这个服务最近响应很慢？"

**系统行为**:
1. 查询 Prometheus 获取延迟指标（P99/P95）
2. 查询 Deepflow 获取分布式追踪数据
3. 查询 Grafana 获取相关仪表盘
4. 分析服务调用链，定位性能瓶颈

### 3. 集群健康检查

**问题**: "集群有什么问题？"

**系统行为**:
1. 扫描 Kubernetes 资源状态
2. 检查 Prometheus 告警
3. 分析关键指标趋势
4. 提供集群健康报告

## 🔑 核心优势

1. **多数据源联动**: 自动关联指标、日志、追踪等多维度数据
2. **智能推理**: 基于 AI 的根因分析和问题定位
3. **知识库驱动**: 结合运维最佳实践和排查手册
4. **可扩展架构**: 轻松集成新的数据源和工具
5. **结构化输出**: 清晰的问题摘要、证据链和行动方案

## 🛠️ 技术栈

- **框架**: HolmesGPT (基于 LangGraph)
- **API 服务**: FastAPI + Uvicorn
- **LLM**: DeepSeek / OpenAI
- **数据源**: Prometheus, Grafana, Elasticsearch, Deepflow, Kubernetes
- **协议**: MCP (Model Context Protocol)

## 📖 相关链接

- [HolmesGPT 官方文档](https://holmesgpt.dev/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [内置工具集列表](https://holmesgpt.dev/data-sources/builtin-toolsets/)

## 💡 最佳实践

1. **配置优化**: 根据实际环境配置工具集和数据源
2. **知识库维护**: 定期更新 Runbook 知识库，添加新的排查手册
3. **工具扩展**: 使用 MCP 桥接服务集成更多第三方工具
4. **监控集成**: 配置 Alertmanager 告警转发，实现自动化诊断

---

**开始使用**: 查看 [使用指南](./USAGE_GUIDE.md) 快速上手
