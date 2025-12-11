# Runbook 知识库集成指南

## 📋 目录

1. [概述](#概述)
2. [工作原理](#工作原理)
3. [添加 Runbook](#添加-runbook)
4. [Runbook 格式](#runbook-格式)
5. [动态更新](#动态更新)
6. [最佳实践](#最佳实践)

---

## 概述

Runbook 是结构化的排查手册，帮助 AI 按照标准流程诊断和解决问题。

### 核心概念

- **Runbook**: Markdown 格式的排查手册
- **Catalog**: 包含所有 runbook 的索引文件
- **自动匹配**: AI 根据用户问题自动选择相关 runbook
- **动态加载**: 无需重启服务，添加后自动生效

---

## 工作原理

### 工作流程

```
1. 用户提问
   ↓
2. AI 分析问题，匹配相关 runbook（基于 catalog 描述）
   ↓
3. 如果匹配，调用 fetch_runbook 工具获取完整内容
   ↓
4. AI 按照 runbook 的步骤执行工具调用
   ↓
5. 综合结果，生成最终答案
```

### 关键点

1. **Catalog 只包含描述**
   - AI 看到的是 runbook 的描述，不是完整内容
   - 只有当 AI 认为相关时，才会获取完整内容

2. **动态获取**
   - Runbook 内容在需要时才加载
   - 支持大量 runbook 而不影响性能

3. **自动执行**
   - AI 会按照 runbook 的步骤自动执行工具调用
   - 无需人工干预

---

## 添加 Runbook

### 步骤 1: 创建 Runbook 文件

在 `knowledge_base/runbooks/` 目录下创建 Markdown 文件：

```bash
vim knowledge_base/runbooks/pod-restart-troubleshooting.md
```

### 步骤 2: 更新 Catalog

编辑 `knowledge_base/runbooks/catalog.json`：

```json
{
  "catalog": [
    {
      "link": "pod-restart-troubleshooting.md",
      "title": "Pod 重启问题排查",
      "description": "当 Pod 持续重启或处于 CrashLoopBackOff 状态时的标准排查流程",
      "tags": ["pod", "restart", "crashloop", "troubleshooting"]
    }
  ]
}
```

**Catalog 字段说明：**

| 字段 | 说明 | 示例 |
|------|------|------|
| `link` | 文件名（相对路径） | `"pod-restart-troubleshooting.md"` |
| `title` | Runbook 标题 | `"Pod 重启问题排查"` |
| `description` | 描述（AI 匹配的关键） | `"当 Pod 持续重启时的排查流程"` |
| `tags` | 标签（可选） | `["pod", "restart"]` |

### 步骤 3: 验证

```bash
# 验证 catalog 格式
python3 scripts/validate_runbooks.py
```

**完成！下次查询自动生效，无需重启。**

---

## Runbook 格式

### 标准格式

```markdown
# [问题类型] 排查指南

## Goal
明确说明这个 runbook 要解决的问题。

## Workflow for [问题类型] Diagnosis

1. **步骤 1**: [具体操作]
   - 使用 `kubectl_describe` 工具检查 Pod 状态
   - 查看 Pod 的 Events 信息

2. **步骤 2**: [具体操作]
   - 使用 `kubectl_logs` 工具查看容器日志
   - 查找错误信息

3. **步骤 3**: [具体操作]
   - 使用 `execute_prometheus_range_query` 查询资源使用情况
   - 检查是否达到资源限制

## Expected Findings

- 如果发现 X，说明是 Y 问题
- 如果发现 Z，说明是 W 问题

## Resolution Steps

1. **立即执行**: [止血措施]
2. **短期排查**: [定位问题]
3. **长期优化**: [根治方案]
```

### 关键字段

- **Goal**: 明确问题类型，帮助 AI 匹配
- **Workflow**: 详细的排查步骤，AI 会按照执行
- **Expected Findings**: 帮助 AI 理解可能的结果
- **Resolution Steps**: 提供解决方案

---

## 完整示例

### Runbook 文件

`knowledge_base/runbooks/pod-restart-troubleshooting.md`:

```markdown
# Pod 重启问题排查指南

## Goal
当 Pod 持续重启或处于 CrashLoopBackOff 状态时，使用此 runbook 进行系统化排查。

## Workflow for Pod Restart Diagnosis

1. **检查 Pod 状态**
   - 使用 `kubectl_describe` 工具查看 Pod 详细信息
   - 重点关注 Events 中的错误信息
   - 检查 Pod 的重启次数和状态

2. **查看容器日志**
   - 使用 `kubectl_logs` 工具获取容器日志
   - 查找错误、异常、panic 等关键词
   - 分析日志中的堆栈信息

3. **检查资源使用**
   - 使用 `execute_prometheus_range_query` 查询内存使用情况
   - 检查是否达到资源限制（OOMKilled）
   - 查看 CPU 使用情况

4. **检查依赖服务**
   - 使用 `kubectl_get_by_kind_in_namespace` 检查相关 Service
   - 验证网络连通性
   - 检查配置和密钥

## Expected Findings

- **OOMKilled**: 内存不足，需要增加资源限制
- **健康检查失败**: 检查 liveness/readiness probe 配置
- **依赖服务不可用**: 检查相关 Service 和 Pod 状态
- **配置错误**: 检查环境变量、ConfigMap、Secret

## Resolution Steps

1. **立即执行 (止血)**
   - 如果内存不足，临时增加资源限制
   - 如果健康检查失败，临时禁用 probe

2. **短期排查 (定位)**
   - 分析日志找出根本原因
   - 检查配置是否正确

3. **长期优化 (根治)**
   - 优化应用代码
   - 调整资源配置
   - 优化健康检查策略
```

### Catalog 配置

`knowledge_base/runbooks/catalog.json`:

```json
{
  "catalog": [
    {
      "link": "pod-restart-troubleshooting.md",
      "title": "Pod 重启问题排查",
      "description": "当 Pod 持续重启或处于 CrashLoopBackOff 状态时的标准排查流程。包括检查 Pod 状态、查看日志、分析资源使用、检查依赖服务等步骤。",
      "tags": ["pod", "restart", "crashloop", "troubleshooting", "kubernetes"]
    }
  ]
}
```

---

## 动态更新

### 无需重启

Runbook 支持动态更新：

1. **添加新 Runbook**
   ```bash
   # 1. 创建文件
   vim knowledge_base/runbooks/new-runbook.md
   
   # 2. 更新 catalog.json
   vim knowledge_base/runbooks/catalog.json
   
   # 3. 下次查询自动生效
   ```

2. **更新现有 Runbook**
   ```bash
   # 直接修改文件
   vim knowledge_base/runbooks/pod-restart-troubleshooting.md
   
   # 下次查询自动使用新内容
   ```

3. **删除 Runbook**
   ```bash
   # 1. 删除文件
   rm knowledge_base/runbooks/old-runbook.md
   
   # 2. 从 catalog.json 中移除条目
   vim knowledge_base/runbooks/catalog.json
   ```

### 验证更新

```bash
# 验证 catalog 格式
python3 scripts/validate_runbooks.py

# 测试 runbook 是否生效
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "我的 Pod 一直在重启"}'
```

---

## 最佳实践

### 1. 描述要准确

Catalog 中的 `description` 是 AI 匹配的关键，要：
- 准确描述问题类型
- 包含关键词（如 "pod restart", "crashloop"）
- 说明适用场景

### 2. 步骤要具体

Workflow 中的步骤要：
- 明确指出使用的工具（如 `kubectl_describe`）
- 说明检查的内容
- 提供判断标准

### 3. 结构要清晰

- 使用标准的 Markdown 格式
- 步骤编号清晰
- 包含预期结果和解决方案

### 4. 标签要合理

Tags 帮助 AI 更好地匹配：
- 使用常见的关键词
- 包含问题类型、资源类型等
- 避免过于宽泛的标签

---

## 常见问题

### Q: AI 没有使用我的 runbook？

A: 检查：
1. Catalog 中的 `description` 是否准确描述了问题
2. 用户问题是否与 runbook 相关
3. Runbook 文件是否存在且格式正确

### Q: 如何让 AI 优先使用某个 runbook？

A: 在 `description` 中使用更具体的关键词，或者调整 System Prompt 中的 runbook 使用说明。

### Q: 可以添加多少个 runbook？

A: 理论上没有限制，但建议：
- 每个 runbook 专注于一个具体问题
- 避免重复和冲突
- 保持 catalog 描述清晰

### Q: Runbook 必须使用英文吗？

A: 可以使用中文，但建议：
- 工具名称使用英文（如 `kubectl_describe`）
- 描述和步骤可以使用中文
- 保持格式一致

---

## 下一步

- [使用指南](./USAGE_GUIDE.md) - 如何使用 HolmesGPT
- [MCP 工具集成指南](./MCP_INTEGRATION_GUIDE.md) - 集成工具

