# ============================================================================
# K8s AIOps Copilot - Dockerfile
# ============================================================================
# 构建: docker build -t k8s-aiops-copilot:latest .
# ============================================================================

FROM python:3.12-slim

# 构建参数
ARG VERSION=1.0.0
ARG COMMIT_HASH=unknown
ARG BUILD_TIME=unknown
ARG KUBECTL_VERSION=v1.29.0

# 设置工作目录
WORKDIR /app

# 安装系统依赖和诊断工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    curl \
    ca-certificates \
    # 网络诊断工具
    net-tools \
    iproute2 \
    dnsutils \
    iputils-ping \
    netcat-openbsd \
    # 系统诊断工具
    procps \
    lsof \
    # 文本处理工具
    jq \
    && rm -rf /var/lib/apt/lists/*

# 安装 kubectl
RUN curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    && kubectl version --client


# 安装 Helm 并预配置常用仓库
RUN curl -fsSL https://get.helm.sh/helm-v3.14.0-linux-amd64.tar.gz | tar -xzf - \
    && mv linux-amd64/helm /usr/local/bin/helm \
    && rm -rf linux-amd64 \
    && helm version --short \
    && helm repo add bitnami https://charts.bitnami.com/bitnami \
    && helm repo add stable https://charts.helm.sh/stable \
    && helm repo update
    
# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY config/ ./config/
COPY knowledge_base/ ./knowledge_base/
COPY tools/ ./tools/
COPY mcp_bridges/ ./mcp_bridges/
COPY run.py .
COPY VERSION .

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    APP_VERSION=${VERSION} \
    APP_COMMIT=${COMMIT_HASH} \
    APP_BUILD_TIME=${BUILD_TIME}

# 版本标签
LABEL version="${VERSION}" \
      commit="${COMMIT_HASH}" \
      build_time="${BUILD_TIME}" \
      maintainer="HuHu" \
      description="K8s AIOps Copilot - 智能运维助手"

# 启动命令
CMD ["python", "run.py"]
