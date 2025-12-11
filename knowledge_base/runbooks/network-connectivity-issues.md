# Kubernetes 网络连通性问题排查指南

## Goal
诊断和解决 Kubernetes 集群中的网络连通性问题。包括 Service 无法访问、DNS 解析失败、NetworkPolicy 配置错误、Pod 间通信问题等网络相关故障的诊断步骤和解决方案。

## Workflow for Network Connectivity Diagnosis

1. **检查 Service 配置**:
   - 使用 `kubectl_describe` 查看 Service 的详细配置
   - 检查 `Selector` 是否匹配到 Pod
   - 验证 `Port` 配置是否正确
   - 使用 `kubectl_get_by_name` 查看 Service 的 Endpoints

2. **检查 Pod 网络配置**:
   - 使用 `kubectl_describe` 查看 Pod 的网络配置
   - 检查 Pod IP 是否正常分配
   - 验证 Pod 是否在正确的节点上运行

3. **测试 DNS 解析**:
   - 在 Pod 内测试 DNS 解析（需要 exec 到 Pod）
   - 检查 `/etc/resolv.conf` 配置
   - 测试内部服务名解析（如 `service-name.namespace.svc.cluster.local`）
   - 测试外部域名解析

4. **检查 NetworkPolicy**:
   - 使用 `kubectl_get_by_kind_in_namespace` 查看 NetworkPolicy
   - 验证 NetworkPolicy 规则是否允许必要的流量
   - 检查 ingress 和 egress 规则

5. **检查节点网络**:
   - 检查节点之间的网络连通性
   - 验证 CNI 插件是否正常运行
   - 检查网络插件相关的 Pod 状态

## Synthesize Findings

综合判断网络问题的根本原因：
- Service 无 Endpoints: Service 的 Selector 不匹配任何 Pod
- DNS 解析失败: CoreDNS 配置问题或网络策略阻止
- NetworkPolicy 阻止: 策略规则过于严格
- CNI 问题: 网络插件故障

## Recommended Remediation Steps

### 立即执行
1. 修复 Service Selector 匹配问题
2. 调整 NetworkPolicy 规则
3. 重启 CoreDNS Pod

### 短期排查
1. 检查 CNI 插件配置
2. 验证网络插件日志

### 长期优化
1. 建立网络监控
2. 优化 NetworkPolicy 策略

