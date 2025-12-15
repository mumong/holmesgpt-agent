# CrashLoopBackOff 故障手册

## 故障特征
**状态关键词**: `CrashLoopBackOff`、`Error`、`Restart Count > 0`

**典型表现**:
- Pod 状态反复在 Running 和 CrashLoopBackOff 之间切换
- Restart Count 持续增加
- 服务无法正常提供

## 问题原理
Kubernetes 检测到容器退出后会尝试重启，但如果容器持续退出，
kubelet 会逐渐增加重启间隔（指数退避），最终进入 CrashLoopBackOff 状态。

**退避时间**: 10s → 20s → 40s → 80s → ... → 最大 5 分钟

## Exit Code 知识库

| Exit Code | 信号 | 含义 | 典型场景 |
|-----------|------|------|---------|
| 0 | - | 正常退出 | 一次性任务完成、启动命令错误 |
| 1 | - | 应用错误 | 配置错误、依赖缺失、代码异常 |
| 126 | - | 无执行权限 | 脚本没有执行权限 |
| 127 | - | 命令不存在 | command 配置错误、镜像缺少依赖 |
| 137 | SIGKILL(9) | OOMKilled | 内存超限被系统杀死 |
| 139 | SIGSEGV(11) | 段错误 | 应用访问非法内存 |
| 143 | SIGTERM(15) | 优雅终止 | 被 K8s 主动终止、健康检查失败 |

## 常见场景与根因

### 场景 1: OOMKilled（Exit Code 137）
**特征**: Last State Reason 为 `OOMKilled`
**根因**: 
- memory limit 设置过低
- 应用内存泄漏
- JVM/Node.js 堆内存配置不当
**修复**: 增加 memory limit，或优化应用内存使用

### 场景 2: 应用配置错误（Exit Code 1）
**特征**: 日志中有明确的配置相关错误
**根因**:
- 环境变量缺失或错误
- ConfigMap/Secret 配置错误
- 数据库连接串错误
**修复**: 修正配置后重启 Pod

### 场景 3: 依赖服务不可用（Exit Code 1）
**特征**: 日志中有 `connection refused`、`timeout` 等
**根因**: 
- 依赖的数据库、缓存、API 不可用
- DNS 解析失败
- 网络策略阻止访问
**修复**: 确保依赖服务可用，检查网络策略

### 场景 4: 启动命令错误（Exit Code 0/127）
**特征**: Pod 启动后立即退出，几乎没有日志
**根因**:
- command/args 配置错误
- 入口点脚本有问题
**修复**: 检查并修正 command 配置

### 场景 5: 健康检查过严（Exit Code 143）
**特征**: 应用日志正常，但被频繁重启
**根因**:
- livenessProbe 超时时间太短
- 健康检查端点响应慢
- initialDelaySeconds 不足
**修复**: 放宽健康检查配置

## 诊断方法论

### 通用诊断流程
1. `kubectl describe pod` 获取 Exit Code 和 Reason
2. `kubectl logs --previous` 获取崩溃前日志
3. 根据 Exit Code 和日志匹配上述场景
4. 针对性修复

### 关键诊断命令
```bash
# 获取 Pod 状态和 Exit Code
kubectl describe pod <name> -n <ns>

# 获取上一次崩溃的日志
kubectl logs <name> -n <ns> --previous
```

## 🔧 修复命令（直接执行）

### 通用修复：删除 Pod 让其重建
```bash
kubectl delete pod <pod-name> -n <namespace>
```

### OOMKilled (Exit Code 137) 修复
```bash
kubectl patch deployment <deployment-name> -n <namespace> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","resources":{"limits":{"memory":"1Gi"}}}]}}}}'
```

### 启动命令错误 (Exit Code 1/127) 修复
```bash
kubectl patch deployment <deployment-name> -n <namespace> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","command":["/bin/sh","-c","sleep infinity"]}]}}}}'
```

### 配置错误修复
```bash
kubectl rollout restart deployment <deployment-name> -n <namespace>
```

### 健康检查过严修复
```bash
kubectl patch deployment <deployment-name> -n <namespace> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","livenessProbe":{"initialDelaySeconds":60,"timeoutSeconds":10,"failureThreshold":5}}]}}}}'
```

### 删除有问题的 Deployment（最后手段）
```bash
kubectl delete deployment <deployment-name> -n <namespace>
```

## 🔍 修复后验证
```bash
kubectl get pod -n <namespace> | grep <pod-name>
```

## 预防措施
- 设置合理的资源 requests/limits（limits 为实际使用的 1.5-2 倍）
- 使用 startupProbe 处理启动慢的应用
- 配置 Pod 重启告警
- 应用实现优雅关闭
