# 🤖 K8s AIOps Copilot

基于 [HolmesGPT](https://github.com/robusta-dev/holmesgpt) 的智能运维 Copilot，专注于 Kubernetes 集群故障诊断。

---

## 🚀 快速开始

### 本地运行

```bash
# 1. 安装依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置 API Key
export DEEPSEEK_API_KEY="your-api-key"

# 3. 启动
python run.py
```

### 镜像构建与部署

```bash
# 修改版本号
echo "1.2.0" > VERSION

# 构建、推送、部署一条龙
make build push deploy
```

---

## 📁 核心目录

```
├── app/core/service.py      # 核心逻辑（⭐重点）
├── config/config.yaml       # 本地配置（含工具集/MCP）
├── knowledge_base/runbooks/ # Runbook 知识库
├── deploy/                  # K8s 部署文件
│   ├── k8s-simple.yaml      # 主部署文件
│   ├── configmap/           # 配置注入
│   │   ├── config.yaml      # 应用配置
│   │   └── runbooks.yaml    # Runbook（catalog + md）
│   └── secrets/             # 敏感信息
└── mcp_standard/            # 第三方 MCP 集成示例
```

---

## 📡 API 使用

```bash
# 流式查询（推荐）
curl -N -X POST "http://localhost:8000/api/v1/query/stream" \
  -H "Content-Type: application/json" \
  -d '{"question": "我的 Pod 一直在重启，帮我分析一下原因"}'

# K8s 部署后（NodePort 30800）
curl -N -X POST "http://<NODE_IP>:30800/api/v1/query/stream" \
  -H "Content-Type: application/json" \
  -d '{"question": "检查集群状态"}'
```

---

## ☸️ K8s 部署

### 部署流程

```bash
# 1. 配置 Secret（必须）
vim deploy/secrets/core.yaml          # 填入 DEEPSEEK_API_KEY

# 2. 配置 ConfigMap（可选）
vim deploy/configmap/config.yaml      # 工具集配置
vim deploy/configmap/runbooks.yaml    # Runbook 知识库

# 3. 部署
make deploy

# 4. 更新 Runbook 后重启
kubectl delete pod -n aiops -l app=aiops-copilot
```

### 动态更新 Runbook

```bash
# 在线编辑
kubectl edit configmap aiops-runbooks -n aiops

# 重启生效
kubectl delete pod -n aiops -l app=aiops-copilot
```

---

## 🔌 MCP 扩展（mcp_standard）

`mcp_standard/` 目录提供第三方 MCP 集成示例（如 Elasticsearch）。

### 启动第三方 MCP

```bash
cd mcp_standard

# 配置环境变量
export ES_URL="https://your-es:9200"
export ES_USERNAME="elastic"
export ES_PASSWORD="your-password"

# 启动（使用 Supergateway 转换 stdio → SSE）
python start_mcp.py
```

### 在 config.yaml 中配置

```yaml
mcp_servers:
  elasticsearch:
    config:
      url: "http://localhost:8082/sse"
      mode: "sse"
    enabled: true
```

---

## 🔐 敏感信息位置

### ⚠️ 需要处理的文件

| 文件 | 敏感信息 | 说明 |
|------|---------|------|
| `config/config.yaml` | Grafana API Key | 第 7 行 `api_key:` |
| `config/config.yaml` | ES Basic Auth | 第 27 行（已注释） |
| `deploy/secrets/core.yaml` | DeepSeek API Key | 第 21 行 |
| `deploy/secrets/observability.yaml` | Grafana/ES 凭证 | 可观测性服务凭证 |

### 🛡️ 建议

1. **不要提交真实密钥到 Git**
2. 使用 `.gitignore` 忽略 `deploy/secrets/*.yaml`
3. 或使用占位符，部署时替换

---

## 📊 Makefile 命令

| 命令 | 说明 |
|------|------|
| `make build` | 构建 Docker 镜像 |
| `make push` | 推送到仓库 |
| `make deploy` | 部署到 K8s（自动更新镜像版本）|
| `make delete` | 删除部署（保留 namespace）|
| `make sync-version` | 同步 VERSION 到 yaml 文件 |

---

## 🤝 致谢

- [HolmesGPT](https://github.com/robusta-dev/holmesgpt) - AI 故障诊断引擎
- [Supergateway](https://github.com/supercorp-ai/supergateway) - MCP stdio → SSE 转换
