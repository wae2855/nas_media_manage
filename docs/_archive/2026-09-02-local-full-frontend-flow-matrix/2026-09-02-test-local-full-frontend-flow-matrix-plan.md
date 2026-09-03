---
title: "test: 本地真实前端文件全流程矩阵验收"
type: plan
date: 2026-09-02
status: completed
confidence: high
requirement: REQ-20260902-180900
---

# 本地真实前端文件全流程矩阵验收计划

一句话总结：用隔离的真实文件、真实 HTTP 服务和 Chromium，从用户点击扫描开始跑通取消中心中转后的关键文件流，并把每个结果固化为可复核证据。

## Problem Statement

现有自动化分别证明了后端文件流和前端状态展示，但没有一套强制从前端业务入口开始、同时核对文件系统与任务事实的端到端矩阵。若继续把这两类测试合并描述为“全流程前台验收”，会掩盖扫描、异步刷新、确认请求与真实文件提交之间的接缝风险。

## Target End State

- 一条命令可在本地自启动服务并完成全矩阵，无需现有 9855 服务、真实账号或手工准备数据。
- 场景必须通过 Chromium 点击产品前端推进；初始化配置和外部 Provider fixture 可以在服务启动前注入。
- 每个场景独立保存文件树、SHA-256、任务状态、截图和浏览器错误，失败时仍保留现场。
- 结果明确区分本地确定性 E2E、真实 TMDB 外部烟测和 fnOS 真机验收。

## Scope

- 电影、电视剧、字幕、兜底、重复决策、来源三种处置和四类中断恢复。
- 桌面主流程，关键详情页追加 390px 无横向溢出检查。
- 文件树与任务状态的机器可读和人可读证据。

## Non-Goals

- 不使用或保存真实 TMDB API Key。
- 不宣称模拟进程异常等于 fnOS 断电、断网和多 GB 真实磁盘验收。
- 不扫描用户当前开发目录、现有片库或 192.168.1.50。
- 不以直接修改任务数据库代替正常扫描、确认和来源处置；只有中断恢复故障注入允许在已真实执行到指定边界后模拟崩溃状态。

## Proposed Solution

1. 新建自启动服务的 Playwright 矩阵，配置、数据库和全部文件均位于测试专属临时根。
2. 在 Provider 工厂边界注入固定候选；其余扫描、分类、冲突、复制、回收和来源处理走真实业务实现。
3. 浏览器执行“立即扫描/任务详情/确认入库/冲突选择/刷新”等真实操作，并等待后端稳定终态。
4. 每个场景写入 `output/full-frontend-flow-matrix/<run-id>/<scenario>/`，包含 `before.json`、`after.json`、`task.json`、`browser.json` 和截图。
5. 证据清单记录每个文件的相对路径、类型、大小和 SHA-256；目录只记录路径，不伪造哈希。

## Scenario Matrix

| ID | 用户路径 | 核心断言 |
|---|---|---|
| F01 | 电影扫描→规则入库→保留来源 | 确认前目标零写入；成功后来源和目标哈希一致 |
| F02 | 电视剧+多字幕→规则入库 | 视频与字幕整包进入季目录，视频最后发布 |
| F03 | 无规则→明确接受兜底 | 未确认前不复制；确认后标记已完成待整理 |
| F04 | 重复→保留片库现有 | 片库与来源均不变，任务明确结束 |
| F05 | 重复→另存一份 | 原片不变，新文件 no-replace 入库 |
| F06 | 单视频重复→确认替换 | 旧片进入本地回收，新片发布，双方哈希可追溯 |
| F07 | 成功后整组来源→本地回收 | 片库成功后来源单元进入回收区 |
| F08 | 成功后整组来源→永久删除 | 只有显式高风险配置才删除，片库保持 |
| F09 | 目标复制提交前中断→重试 | 临时成员清理，来源不变，重试从识别开始 |
| F10 | 完整提交后状态落库前中断 | 重启复核后成功，不重复复制，来源保留 |
| F11 | 部分提交/目标指纹异常 | 文件全部保留，任务提示人工检查 |
| F12 | 浏览器启动复制→父进程外部 SIGKILL→重启→前端重试 | 真实 `.copying` 中途强杀；重启清理临时文件，来源不变，重试后哈希一致 |

## Implementation Tasks

- [x] 建立隔离场景、确定性 Provider 和证据采集基座。
- [x] 完成 F01-F03 正常电影、电视剧字幕和兜底前端链路。
- [x] 完成 F04-F06 三种重复决策及回收证据。
- [x] 完成 F07-F08 两种来源处置闭环。
- [x] 完成 F09-F11 中断、重试和恢复闭环。
- [x] 完成 F12 外部 SIGKILL、同库同配置重启和前端重试闭环。
- [x] 运行完整 Chromium 矩阵，修复验收脚本接缝并全量重跑。
- [x] 更新测试矩阵、验收台账和需求状态；归档计划与提案。

## Test Plan

- 专项：`.venv/bin/python -m pytest -q tests/test_full_frontend_flow_matrix_browser_ui.py -s`
- 文件安全回归：来源处置、目标冲突、字幕包、重启恢复、文件流矩阵。
- 全量：`.venv/bin/python -m pytest -q tests/`
- 质量门禁：Ruff、compileall、架构护栏、文档检查和 `git diff --check`。
- 浏览器门禁：页面异常和 HTTP 5xx 为 0；390px 页面及弹窗横向溢出为 0。

## Acceptance Criteria

1. 12 个场景均从隔离真实文件开始，并通过前端用户动作推进到预期结果。
2. 每个场景都有 before/after 文件树与 SHA-256、最终任务 JSON、浏览器错误 JSON 和至少一张截图。
3. 所有目标片库既有文件的变化均能由明确冲突动作和本地回收记录解释；无通用删除。
4. 确认前不得出现目标大文件；来源处置只发生在文件包提交成功之后。
5. 专项矩阵、相关安全回归和全量测试全部 PASS；跳过项单独列出，不能算 PASS。
6. 报告分别给出 LOCAL_E2E、REAL_TMDB、FNOS_UAT 状态。

## Decision Rationale

确定性 Provider 让文件流和前端合同可重复，真实文件系统和真实 HTTP/Chromium 则保留最容易出错的进程边界。相比把每个外部不稳定因素混入一个长用例，这种方式能在不接触用户数据的前提下给出更强、可持续复跑的证据。

## Constraints And Boundaries

- 严格遵守目标片库禁止通用删除、来源永久删除隔离认领和 no-replace 发布规则。
- 测试只能操作测试创建且 realpath 位于专属临时根的文件。
- 不读取用户现有片库，不访问 fnOS，不在证据中写密钥。
- 不并行运行共享 SQLite/文件系统的场景。

## Assumptions

| Assumption | Status | Evidence / Action |
|---|---|---|
| 本地 API 服务可在测试线程独立启动 | Verified | 现有多个 `*_browser_ui.py` 使用该模式 |
| 外部 Provider 可在工厂边界确定性替换 | Verified | `MatrixFixtureProvider` 只替代外部返回，runner 与文件流未 mock |
| 前端能从首页触发扫描并在任务页完成所有动作 | Verified | F01-F12 均由 Chromium 点击扫描、详情、确认或重试推进 |
| 外部 SIGKILL 可命中正式复制窗口 | Verified | F12 在 64 MiB 源文件复制至 1 MiB 时由父进程对精确服务 PID 发送 SIGKILL，退出码为 -9 |
| 小型真实文件可证明文件安全和状态边界 | Verified with limit | 哈希/no-replace/回收可证明；性能和断电仍需 fnOS 大文件验收 |

## Risk Analysis

| Risk | Impact | Mitigation |
|---|---|---|
| 异步任务导致用例偶发 | 假失败或漏检 | 等待明确任务状态和文件事实，不使用固定长 sleep |
| fixture 注入过深绕过真实逻辑 | 形成假 E2E | 只替代外部 Provider 返回；扫描到文件提交全部真实执行 |
| 故障注入误删非测试文件 | 严重 | 每次操作前校验专属临时根；tearDown 只清理该根 |
| 证据只在成功时保存 | 失败无法复盘 | finally 中采集文件树、任务和浏览器错误 |
| 一个超长用例互相污染 | 难定位 | 每个场景独立配置、数据库、服务和文件根 |

## Rejection Criteria

- 从 API 或数据库直接创建普通业务任务，再称为前端全流程。
- 只检查页面文案，不检查真实文件位置和哈希。
- 用跳过、mock 整条 pipeline 或手工观察代替场景 PASS。
- 删除测试专属根以外的任何文件。

## Required Preview Artifacts

- 每个场景的关键任务页/详情页截图。
- 每个场景的 before/after 文件树与 SHA-256 JSON。
- 汇总 `matrix-summary.json`，明确 PASS/FAIL/NOT_RUN 和失败原因。

## Implementation Evidence

- 本地真实 Chromium 矩阵：F01-F12 共 12/12 PASS，证据根为 `output/full-frontend-flow-matrix/20260902T205532/`。
- 证据完整性：每场均保存 `prepared/after` 文件树及 SHA-256、最终任务 JSON、浏览器错误 JSON 和截图；故障场景额外保存中断现场与离线任务快照，共 14 张截图。
- F12 外部强杀证据：64 MiB 源文件复制到 1 MiB 时对精确子服务 PID 发送 SIGKILL，进程退出码 -9；重启清理 `.copying` 后由前端重试成功，源和片库 SHA-256 一致。
- 安全专项：72/72 PASS（目标冲突、字幕文件包、来源处置、永久删除、校验复制和重启恢复）。
- 全量回归：1001/1001 PASS，耗时 136.78 秒。
- 浏览器检查：12 场 page error=0、HTTP 5xx=0，最终 390px 页面横向溢出为 0。
- REAL_TMDB：NOT_RUN；确定性 Provider 不代表真实 TMDB 网络与账号验收。
- FNOS_UAT：NOT_RUN；本地进程故障注入不代替真机多 GB 文件、断电和挂载故障验收。

## References

- [文件全流程测试矩阵](../../testing/file-flow-matrix.md)
- [取消中心中转与整任务恢复计划（已归档）](../2026-09-02-remove-central-staging-and-whole-task-restart/2026-09-02-refactor-remove-central-staging-and-restart-recovery-plan.md)
- [文件安全规范](../../standards/safety.md)
- [本轮提案](2026-09-02-local-full-frontend-flow-matrix.md)
