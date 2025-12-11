# MCP 工具集成指南

## 📋 目录

1. [概述](#概述)
2. [内置工具集集成](#内置工具集集成)
3. [第三方 MCP 工具集成](#第三方-mcp-工具集成)
4. [标准集成流程](#标准集成流程)
5. [常见问题](#常见问题)

---

## 概述

HolmesGPT 支持两种类型的工具集成：

1. **内置工具集**（Built-in Toolsets）
   - Prometheus、Kubernetes、Docker 等
   - 通过配置文件启用和配置

2. **第三方 MCP 工具**（Remote MCP Servers）
   - 自定义开发的 MCP 服务器
   - 通过 HTTP/SSE 协议连接

---

## 内置工具集集成

### 配置位置

`.holmes/config.yaml`

### 配置格式

```yaml
# 内置工具集配置
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://localhost:9090"
  
  kubernetes/core:
    enabled: true
    config:
      kubeconfig_path: "~/.kube/config"
```

### 常用内置工具集

| 工具集 | 配置键 | 说明 |
|--------|--------|------|
| Prometheus | `prometheus/metrics` | 指标查询和监控 |
| Kubernetes | `kubernetes/core` | K8s 资源管理 |
| Docker | `docker/core` | 容器管理 |
| Runbook | `runbook` | 知识库和排查手册 |

### 完整配置示例

```yaml
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://localhost:9090"
  
  kubernetes/core:
    enabled: true
  
  kubernetes/logs:
    enabled: true
```

---

## 第三方 MCP 工具集成

### 标准集成流程

#### 步骤 1: 开发 MCP 服务器

创建 MCP 服务器文件（如 `my_mcp_server.py`）：

```python
#!/usr/bin/env python3
from mcp.server import Server
import mcp.types as types

app = Server("my_tool_server")

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="my_tool",
            description="工具描述",
            inputSchema={"type": "object", "properties": {}}
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "my_tool":
        return [types.TextContent(type="text", text="工具执行结果")]
```

#### 步骤 2: 启动 MCP 服务器

```bash
# 启动服务器（监听 8081 端口）
python my_mcp_server.py
```

**要求：**
- 必须支持 SSE（Server-Sent Events）传输模式
- 提供两个端点：
  - `GET /sse` - SSE 流连接
  - `POST /messages/` - 消息接收

#### 步骤 3: 配置 config.yaml

在 `.holmes/config.yaml` 中添加配置：

```yaml
# 第三方 MCP 服务器配置
mcp_servers:
  my_tool_server:
    description: "我的工具集描述"
    config:
      url: "http://localhost:8081/sse"
      mode: "sse"
    llm_instructions: "什么时候使用这个工具的说明"
    enabled: true
```

**配置说明：**

| 字段 | 说明 | 示例 |
|------|------|------|
| `description` | 工具集描述 | "我的工具集描述" |
| `config.url` | MCP 服务器 SSE 端点 | `"http://localhost:8081/sse"` |
| `config.mode` | 传输模式 | `"sse"` |
| `llm_instructions` | AI 使用说明 | "只有当用户需要...时才使用" |
| `enabled` | 是否启用 | `true` |

#### 步骤 4: 重启 HolmesGPT

```bash
# 如果使用 API 服务器模式
# 重启 API 服务器
pkill -f api_server.py
python api_server.py

# 如果使用命令行模式
# 直接运行即可
python roubusta.py
```

#### 步骤 5: 验证集成

```bash
# 检查工具是否加载
curl http://localhost:8000/api/v1/tools | jq '.tools[] | select(. | contains("my_tool"))'
```

---

## 标准集成流程

### 流程图

```
1. 开发 MCP 服务器
   ↓
2. 启动 MCP 服务器（独立进程）
   ↓
3. 在 config.yaml 中配置
   ↓
4. 重启 HolmesGPT
   ↓
5. 验证工具加载
   ↓
6. 使用工具
```

### 关键要点

1. **MCP 服务器独立运行**
   - MCP 服务器是独立的进程
   - 通过 HTTP/SSE 与 HolmesGPT 通信
   - 可以部署在不同的机器上

2. **配置文件格式**
   - 使用 `mcp_servers` 键
   - 每个服务器需要唯一的名称
   - `enabled: true` 才会加载

3. **工具命名规范**
   - 工具名称必须符合 `^[a-zA-Z0-9_-]+$` 正则表达式
   - 不能包含中文字符或特殊符号

4. **传输模式**
   - 当前支持 `sse`（Server-Sent Events）模式
   - 需要提供 `GET /sse` 和 `POST /messages/` 端点

---

## 完整示例：测试工具

### 1. MCP 服务器代码

文件：`test_mcp_server_simple.py`

```python
#!/usr/bin/env python3
from mcp.server import Server
import mcp.types as types
from mcp.server.sse import SseServerTransport
# ... (完整代码见文件)

app = Server("test_tool_server")

@app.list_tools()
async def handle_list_tools():
    return [types.Tool(
        name="test_tool",
        description="测试工具",
        inputSchema={"type": "object", "properties": {}}
    )]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "test_tool":
        return [types.TextContent(type="text", text="这是测试")]
```

### 2. 启动服务器

```bash
python test_mcp_server_simple.py
# 服务器运行在 http://localhost:8081
```

### 3. 配置文件

`.holmes/config.yaml`:

```yaml
mcp_servers:
  test_tool_server:
    description: "测试工具集"
    config:
      url: "http://localhost:8081/sse"
      mode: "sse"
    llm_instructions: "只有当用户需要测试的时候才运行"
    enabled: true
```

### 4. 使用

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "运行测试工具"}'
```

---

## 常见问题

### Q: MCP 服务器无法连接？

A: 检查：
1. MCP 服务器是否正在运行
2. URL 和端口是否正确
3. 防火墙是否允许连接
4. SSE 端点是否可访问：`curl -I http://localhost:8081/sse`

### Q: 工具名称不符合规范？

A: 工具名称必须符合 `^[a-zA-Z0-9_-]+$`，不能包含：
- 中文字符
- 特殊符号（除了 `_` 和 `-`）
- 空格

### Q: 如何查看工具是否加载成功？

A: 使用 `/api/v1/tools` 端点查看所有可用工具。

### Q: 可以集成多个 MCP 服务器吗？

A: 可以，在 `config.yaml` 中配置多个 `mcp_servers` 条目即可。

### Q: MCP 服务器需要和 HolmesGPT 在同一台机器吗？

A: 不需要，只要网络可达即可。URL 可以是：
- `http://localhost:8081/sse`（本地）
- `http://192.168.1.100:8081/sse`（内网）
- `https://mcp.example.com/sse`（公网）

---

## 下一步

- [使用指南](./USAGE_GUIDE.md) - 如何使用 HolmesGPT
- [Runbook 集成指南](./RUNBOOK_INTEGRATION_GUIDE.md) - 集成知识库

