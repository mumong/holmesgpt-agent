# Pod 重启问题排查指南

## Goal
诊断和解决 Kubernetes Pod 频繁重启的问题。本指南涵盖 CrashLoopBackOff、OOMKilled、健康检查失败等常见原因的诊断步骤和解决方案。AI 必须按照本指南的步骤顺序执行诊断，确保全面、系统地排查问题。

## Workflow for Pod Restart Diagnosis

1. **检查 Pod 当前状态**:
   - 使用 `kubectl_describe` 工具查看 Pod 的详细状态
   - 重点关注以下字段：
     * `Last State`: 上次容器的状态和退出原因
     * `Reason`: 容器退出的原因（如 OOMKilled、Error、Completed）
     * `Restart Count`: 重启次数，确认重启频率
     * `State`: 当前状态（CrashLoopBackOff、Running、Pending 等）
     * `Conditions`: Pod 的条件状态，查看是否有异常

2. **查看容器日志**:
   - 使用 `kubectl_logs` 工具获取容器日志
   - 如果 Pod 有多个容器，使用 `kubectl_logs_all_containers` 获取所有容器日志
   - 查找以下关键信息：
     * 错误消息和异常堆栈（如 `OutOfMemoryError`、`ConnectionRefused`）
     * 启动失败的具体原因
     * 应用程序特定的错误代码
     * 时间戳，确认重启的时间模式

3. **检查资源使用情况**:
   - 使用 `kubectl_get_yaml` 查看 Pod 的资源限制配置
   - 检查 `spec.containers[].resources.limits` 和 `spec.containers[].resources.requests`
   - 如果 `Last State.Reason` 是 `OOMKilled`，重点关注内存限制
   - 对比实际资源使用量和限制值（如果 Metrics Server 可用）

4. **检查依赖服务**:
   - 使用 `kubectl_get_yaml` 查看 Pod 的环境变量（`env` 和 `envFrom`）
   - 检查 ConfigMap 和 Secret 的配置是否正确
   - 验证依赖的服务（如数据库、API 服务）是否正常运行
   - 使用网络工具测试服务连通性

5. **检查健康检查配置**:
   - 使用 `kubectl_get_yaml` 查看 `livenessProbe` 和 `readinessProbe` 配置
   - 验证健康检查的路径、端口和超时设置是否正确
   - 检查健康检查是否过于严格导致 Pod 被频繁重启
   - 如果可能，测试健康检查端点是否正常响应

6. **检查事件信息**:
   - 使用 `kubectl_events` 工具查看 Pod 相关的事件
   - 查找警告和错误事件
   - 关注调度失败、镜像拉取失败、资源不足等事件

## Synthesize Findings

根据以上步骤的发现，综合判断根本原因：

- **OOMKilled**: 如果 `Last State.Reason` 是 `OOMKilled`，且内存使用接近 `resources.limits.memory`，则是内存不足导致。日志中可能包含 `OutOfMemoryError` 相关信息。

- **健康检查失败**: 如果日志显示应用正常运行，但 Pod 频繁重启，且 `livenessProbe` 配置存在，很可能是健康检查失败导致。检查健康检查端点的响应。

- **依赖服务问题**: 如果日志显示连接失败（如 `ConnectionRefused`、`ConnectionTimeout`、`Name resolution failed`），检查依赖服务状态和网络配置。

- **配置错误**: 如果日志显示配置相关的错误（如环境变量缺失、配置文件格式错误、密钥不存在），检查 ConfigMap 和 Secret 的配置。

- **应用 Bug**: 如果日志显示应用程序异常（如未捕获的异常、空指针、启动脚本错误），需要修复应用代码。

- **镜像问题**: 如果事件显示镜像拉取失败或镜像不存在，检查镜像仓库和镜像标签。

## Recommended Remediation Steps

### 立即执行（止血）

1. **如果是 OOMKilled**:
   - 临时增加 `resources.limits.memory`
   - 命令示例：`kubectl patch pod <pod-name> -n <namespace> -p '{"spec":{"containers":[{"name":"<container-name>","resources":{"limits":{"memory":"2Gi"}}}]}}'`
   - 或者编辑 Deployment/StatefulSet 的资源配置

2. **如果是依赖服务问题**:
   - 检查并修复依赖服务（数据库、API 服务等）
   - 验证网络策略是否允许访问
   - 检查 Service 和 Endpoints 是否正常

3. **如果是健康检查失败**:
   - 临时禁用或放宽 `livenessProbe`（增加 `failureThreshold` 或 `timeoutSeconds`）
   - 检查健康检查端点是否正常响应
   - 修复应用程序的健康检查实现

4. **如果是配置错误**:
   - 修复 ConfigMap 或 Secret 中的配置
   - 验证环境变量是否正确设置
   - 重新创建 Pod 以应用新配置

### 短期排查（定位）

1. **优化应用**:
   - 修复应用中的内存泄漏
   - 优化资源使用（减少内存占用、优化启动时间）
   - 添加更详细的日志记录

2. **调整配置**:
   - 根据实际使用情况调整资源限制（requests 和 limits）
   - 优化健康检查配置（调整间隔、超时、阈值）
   - 配置适当的启动探针（startupProbe）

### 长期优化（根治）

1. **建立监控**:
   - 配置 Pod 重启告警（使用 Prometheus 和 Alertmanager）
   - 监控资源使用趋势
   - 设置依赖服务健康检查

2. **优化架构**:
   - 实现优雅关闭（graceful shutdown）
   - 添加重试机制和断路器
   - 优化启动时间
   - 实现健康检查的最佳实践

3. **文档和培训**:
   - 记录常见问题和解决方案
   - 建立标准化的排查流程
   - 培训团队使用本 runbook

## 注意事项

- 在执行任何修复操作前，确保理解操作的影响
- 对于生产环境，建议先在测试环境验证
- 保留操作记录，便于后续分析和改进
- 如果问题持续存在，考虑升级应用版本或 Kubernetes 版本

