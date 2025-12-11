# MCP 桥接服务

将第三方 MCP 服务器（npm 包）桥接到 HTTP/SSE 协议，供 HolmesGPT 使用。

## 快速开始

### Elasticsearch MCP

```bash
# 安装依赖
cd mcp_bridges/elasticsearch
pip install -r requirements.txt

# 直接运行（从 config.yaml 读取配置）
python3 bridge_server.py

# 或使用环境变量
export ES_URL="http://your-elasticsearch:9200"
export ES_USERNAME="elastic"
export ES_PASSWORD="password"
python3 bridge_server.py
```

### 配置

在 `.holmes/config.yaml` 中配置：

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
      bridge_port: 8082
    llm_instructions: "当用户需要搜索日志、查询 Elasticsearch 数据时使用此工具集"
    enabled: true
```

## 添加新的 MCP 服务

1. 在 `mcp_bridges/` 下创建新目录
2. 创建 `bridge_server.py`（参考 `elasticsearch/bridge_server.py`）
3. 创建 `config_loader.py`（参考 `elasticsearch/config_loader.py`）
4. 在 `config.yaml` 中添加配置

核心逻辑：
- `create_mcp_client()`: 启动 npm 进程
- `get_tools()`: 获取工具列表
- `call_tool()`: 调用工具
- `main()`: 启动 HTTP/SSE 服务器
