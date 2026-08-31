---
title: "fix: fnOS 桌面入口与旧配置迁移"
type: plan
date: 2026-08-30
status: implemented
confidence: high
requirement: REQ-20260830-180954
---

# fnOS 桌面入口与旧配置迁移

- **Requirement**: [REQ-20260830-180954](../tracking/requirements-board.md)
- **ADR**: [0011](../decisions/0011-fnos-install-runtime-config-ownership.md)、[0017](../decisions/0017-fnos-first-run-directory-authorization.md)
- **Status**: implemented

修复 0.3.3 真机升级后服务仍监听旧端口、fnOS 桌面 CGI 返回 502，以及未完成目录配置时缺少明确首次引导的问题。

## Problem Statement

新包声明端口 `14591`，但升级回调只更新离线依赖，不迁移旧 `config.yaml`。真机保留的旧配置仍监听 `9855` 且保留服务 API Key；fnOS 执行 CGI 时又不保证注入 `TRIM_PKGVAR`，入口因此按默认 `14591` 访问无监听服务并返回 502。安装向导已把目录选择移到首次 Web 启动，桌面入口失败后用户无法完成该流程。

## Target End State

- 全新安装和旧版升级都由 fnOS 桌面图标正常打开应用。
- 升级只迁移托管字段 `server.port=14591`、`server.api_key=""`，用户目录和业务配置保持不变。
- CGI 不依赖 fnOS 未承诺注入的包数据目录变量，稳定代理固定托管端口。
- 来源、片库或回收目录缺失时，首次进入应用明确落到配置流程；文件自动处理继续受 readiness 门禁阻塞。

## Scope and Non-Goals

- 修改 fnOS 配置迁移工具、升级回调、CGI、首次 Web 引导、打包测试和部署文档。
- 不覆盖来源目录、多个片库根、回收目录、TMDB/LLM 凭据或业务开关。
- 不改变本地开发显式使用 `9855` 的方式，不直接修改 fnOS 用户媒体文件。

## Decision Rationale

`14591` 和空服务认证已经成为 fnOS 托管运行契约，因此升级时应做一次幂等迁移；继续兼容任意旧端口会让 manifest、桌面入口和实际进程长期双源。固定 CGI 上游端口比猜测包变量路径更可靠。目录仍由首次 Web 授权选择，符合 fnOS 共享目录权限模型。

## Assumptions

| Assumption | Status | Evidence |
|---|---|---|
| fnOS CGI 环境不保证提供 `TRIM_PKGVAR` | Verified | 2026-08-30 真机桌面请求返回 502，直接带入该变量执行 CGI 可访问旧服务 |
| 旧配置中的目录和业务项必须保留 | Verified | ADR-0011 与用户已确认的升级边界 |
| 未完成目录配置时服务可以只提供配置页 | Verified | ADR-0017，自动任务已有 storage readiness 门禁 |

## Risks

- 清空旧服务 API Key 会改变直接调用旧 API 的行为；该字段已从 fnOS 普通配置移除，并由用户确认改为 fnOS 托管无服务 Key。
- 升级迁移失败若仍启动，会再次形成端口错配；升级回调必须失败可见并中止。
- 首次引导不得覆盖已有完整配置；只在 readiness 显示必需目录缺失时跳转。

## Implementation Tasks

- [x] 为 `fnos_config.py` 增加幂等托管配置迁移，只改服务端口和服务 API Key，并验证其他 YAML 内容不变。
- [x] 在安装与升级回调调用迁移；让 CGI 固定代理 `127.0.0.1:14591`，错误信息不暴露内部路径或密钥。
- [x] 补齐首次目录未就绪时的前端进入配置行为和可理解提示，完整配置保持现状。
- [x] 更新打包回归、ADR/部署文档与 FPK 校验，执行定向测试、非 UI 回归、真机安装包验证。
- [x] 自评审后将需求转回 `pending_acceptance` 并归档本计划。

## Acceptance Criteria

- 旧配置迁移后 `server.port=14591`、`server.api_key=""`，来源、片库、回收和业务配置逐项不变；重复迁移无副作用。
- 打包后的 `cmd/upgrade_callback` 明确执行迁移，失败返回非零；`ui/index.cgi` 不读取 `TRIM_PKGVAR`。
- 未配置必需目录时首次打开进入配置页，已配置用户仍进入常规首页。
- 本地打包与校验通过；fnOS 真机升级后只监听 `14591`，桌面 iframe 返回 200 且配置 API 不再 401。

## Verification Evidence

- 定向回归：49 passed；非 UI 全量回归：746 passed；架构护栏：18 passed。
- Ruff、JavaScript 语法、Shell 语法、文档检查全部通过。
- 生成 0.3.4 FPK，SHA-256：`e679d28a01983090209d46dd63e8260d6517966679c98f821b13d85399df5895`；包结构校验通过。
- fnOS 真机从旧版升级至 0.3.4 后仅监听 `0.0.0.0:14591`，健康检查 200，旧端口 `9855` 无监听。
- fnOS 桌面图标可打开原生应用窗口；首次进入自动落到“存储检查”，未配置回收目录与无写权限片库均被明确阻塞，后台扫描保持停用。
