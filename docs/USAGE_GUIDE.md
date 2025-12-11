# HolmesGPT 使用指南

## 📋 目录

1. [快速开始](#快速开始)
2. [运行方式](#运行方式)
3. [发送请求](#发送请求)
4. [常见请求示例](#常见请求示例)
5. [配置说明](#配置说明)

---

## 快速开始

### 前置要求

1. **Python 环境**: Python 3.12+
2. **API Key**: DeepSeek 或 OpenAI API Key
3. **配置文件**: `.holmes/config.yaml`

### 环境变量设置

```bash
export DEEPSEEK_API_KEY=your-api-key-here
# 或
export OPENAI_API_KEY=your-api-key-here
```

---

## 运行方式

### 方式 1: API 服务器模式（推荐）

**启动服务器：**

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动 API 服务器
python api_server.py

# 或后台运行
nohup python api_server.py > /tmp/api_server.log 2>&1 &
```

**服务器信息：**
- 默认地址: `http://0.0.0.0:8000`
- API 文档: `http://localhost:8000/docs`
- 健康检查: `http://localhost:8000/health`

### 方式 2: 命令行模式

**直接运行：**

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行主程序
python roubusta.py
```

**说明：**
- 问题在 `prompt.py` 的 `question_ask` 中定义
- 结果直接输出到终端

---

## 发送请求

### API 端点

**主要端点：** `POST /api/v1/query`

### 请求格式

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "你的问题",
    "max_steps": 50
  }'
```

### 请求参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 用户的问题或查询内容 |
| `system_prompt` | string | ❌ | 自定义系统提示词（可选） |
| `max_steps` | integer | ❌ | 最大执行步数（默认: 50） |
| `model` | string | ❌ | LLM 模型（默认: deepseek/deepseek-chat） |
| `api_key` | string | ❌ | LLM API Key（默认: 使用环境变量） |

### 响应格式

```json
{
  "success": true,
  "result": "AI 的分析结果...",
  "tool_calls": [
    {
      "tool_name": "execute_prometheus_range_query",
      "result": "...",
      "error": null
    }
  ],
  "execution_time": 12.34,
  "timestamp": "2025-12-05T10:30:00.123456"
}
```

---

## 常见请求示例

### 示例 1: 查询集群内存使用率

**问题：** 过去1小时的集群内存使用率是多少？直接使用prometheus的工具进行计算

**请求：**

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "过去1小时的集群内存使用率是多少？直接使用prometheus的工具进行计算"
  }' | jq .
```

**说明：**
- AI 会调用 Prometheus 工具查询内存使用率
- 返回详细的分析报告和图表数据

**预期输出：**
- 集群平均内存使用率
- 各节点内存使用详情
- 内存使用趋势分析
- 建议和优化方案

---

### 示例 2: 测试工具调用

**问题：** 运行测试工具临时输出，我需要进行测试临时输出，运行测试工具

**请求：**

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "运行测试工具临时输出，我需要进行测试临时输出，运行测试工具"
  }' | jq .
```

**说明：**
- AI 会识别并调用测试工具（test_tool）
- 测试工具返回：`"这是测试huhu-xnet"`

**前提条件：**
- 测试 MCP 服务器需要运行在 `http://localhost:8081`
- 在 `.holmes/config.yaml` 中已配置 `test_tool_server`

---

### 示例 3: Pod 重启问题排查

**问题：** 我的 Pod 一直在重启

**请求：**

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "我的 Pod 一直在重启"
  }' | jq .
```

**说明：**
- AI 会按照 System Prompt 的三阶段工作流程进行分析
- 如果存在相关 runbook，AI 会调用 `fetch_runbook` 获取排查步骤
- 按照 runbook 的指导逐步排查问题

**预期输出：**
- 问题摘要
- 根本原因分析 (RCA)
- 证据链（指标、日志、追踪）
- 建议行动方案（立即执行、短期排查、长期优化）

---

## 配置说明

### 配置文件位置

`.holmes/config.yaml`

### 主要配置项

```yaml
# 输出模式配置
stream_output: false  # true: 流式输出, false: 非流式输出

# 内置工具集配置
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://localhost:9090"

# 第三方 MCP 服务器配置
mcp_servers:
  test_tool_server:
    description: "测试工具集"
    config:
      url: "http://localhost:8081/sse"
      mode: "sse"
    enabled: true
```

### 环境变量

```bash
# API 服务器配置
export API_PORT=8000          # API 服务端口
export API_HOST=0.0.0.0       # API 服务地址

# LLM 配置
export DEEPSEEK_API_KEY=your-api-key
```

---

## 其他常用端点

### 健康检查

```bash
curl http://localhost:8000/health
```

### 列出可用工具

```bash
curl http://localhost:8000/api/v1/tools | jq .
```

### API 文档

访问 `http://localhost:8000/docs` 查看完整的 API 文档（Swagger UI）

---

## 常见问题

### Q: 如何查看工具调用详情？

A: 响应中的 `tool_calls` 字段包含所有工具调用的详细信息，包括工具名称、结果和错误信息。

### Q: 如何自定义系统提示词？

A: 在请求中传入 `system_prompt` 参数，或修改 `prompt.py` 中的 `SYSTEM_PROMPT`。

### Q: 如何增加工具调用次数？

A: 在请求中设置 `max_steps` 参数（默认 50，最大 100）。

### Q: 如何查看执行日志？

A: API 服务器日志输出到终端，后台运行时查看 `/tmp/api_server.log`。

---

## 下一步

- [MCP 工具集成指南](./MCP_INTEGRATION_GUIDE.md) - 集成内置和第三方 MCP 工具
- [Runbook 集成指南](./RUNBOOK_INTEGRATION_GUIDE.md) - 集成知识库和排查手册

