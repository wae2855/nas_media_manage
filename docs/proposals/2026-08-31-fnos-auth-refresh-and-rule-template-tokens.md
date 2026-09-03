---
title: "fnOS 授权即时刷新与规则模板变量助手"
type: proposal
date: 2026-08-31
status: approved
confidence: high
requirement: REQ-20260831-224737
---

# fnOS 授权即时刷新与规则模板变量助手

- **Requirement**: [REQ-20260831-224737](../tracking/requirements-board.md)
- **Plan**: [实施记录](../_archive/2026-08-31-fnos-auth-refresh-and-rule-template-tokens/2026-08-31-fix-fnos-auth-refresh-and-rule-template-tokens-plan.md)

## 用户问题

已有片库在 fnOS 重新授权后，页面没有自动刷新存储结论，用户只能点击“重新检查”；规则路径变量只能靠记忆手写，容易输错。

## 决策

1. 授权回调后立即显示持久同步状态，有限重试 fnOS 授权能力，成功后统一调用配置/readiness 加载入口。
2. 已存在的片库路径只刷新权限，不改动片库配置；新路径才进入片库命名和保存。
3. 规则弹窗提供可点击的核心变量及已启用维度变量，插入当前光标或替换选区。
4. 只展示后端已验证支持的变量，不扩展模板语法。

## 用户结果

授权动作有明确进度和结果，不再需要猜测或手工刷新；规则路径可以通过点击组合，不需要记忆占位符。
