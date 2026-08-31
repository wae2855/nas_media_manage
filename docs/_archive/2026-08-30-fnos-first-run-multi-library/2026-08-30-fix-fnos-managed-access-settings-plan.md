---
title: "fix: fnOS 托管服务认证与端口"
type: plan
date: 2026-08-30
status: implemented
confidence: high
requirement: REQ-20260830-180954
---

# fnOS 托管服务认证与端口

将 Web 服务 API Key 和监听端口从 fnOS 安装向导及普通配置界面移除，降低首次安装和日常配置成本。

## 已实施边界

- fnOS 安装向导不再要求填写初始化 API Key 或端口。
- 新安装默认 `server.api_key` 为空、端口固定为 `14591`。
- 配置界面不再展示“安全配置”入口、服务 API Key 或端口字段。
- 后端认证、CLI/YAML 端口覆盖能力继续保留，旧配置与升级配置不被覆盖。
- TMDB、LLM 等业务凭据配置不受影响。
- manifest、CGI 回退、配置模板与 CLI 缺省值统一使用 `14591`；本地开发仍可显式使用 `9855`。

## 完成任务

- [x] 调整 fnOS 初始化为固定端口、空认证，删除向导字段和配置回调端口更新。
- [x] 删除普通配置界面的安全入口、页面、加载与保存逻辑。
- [x] 更新文案、测试与打包校验，确认业务 API Key 页面仍存在。
- [x] 运行定向测试、非 UI 回归、前端语法、文档检查并重新构建 FPK。
- [x] 自评审并归档计划，需求回到待实机验收。

## 验收证据

- 定向回归：38 passed；最终端口一致性回归：19 passed。
- 完整非 UI 回归：744 passed。
- Ruff、compileall、JavaScript/Shell 语法、文档和 diff 检查通过。
- 桌面 1440px 与手机 390px：服务 Key/端口字段均不存在，LLM Key 保留，无横向溢出和控制台错误。
- FPK `0.3.3`：manifest `service_port=14591`；安装/配置向导无托管字段；结构与 SHA256 校验通过。
- 待验收：fnOS 实机全新安装、升级保留旧配置、桌面/移动端应用入口。
