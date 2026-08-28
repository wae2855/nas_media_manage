---
title: "simplification roadmap（Phase 0-4）"
type: plan
date: 2026-08-22
status: approved
confidence: high
requirement: REQ-20260822-000003
---

# 功能简洁化执行路线图

一行摘要：按评估提案（[proposal](../proposals/2026-08-22-simplification-assessment.md)）分期执行减法——工程基础 → Hermes/AI 刮削移除 → 状态机重构 → 配置面简化 → 收尾验收。

> 业务输入已由用户 2026-08-22 拍板（见提案 §5）。技术执行顺序为本计划职责。状态机重构独立为 REQ-20260822-000004，其详细设计文档在 Phase 2 启动时产出。

## Phase 0 工程基础（零业务风险）

- [x] T1 删除 36 个未加载前端文件（9,376 行，已核实无动态加载引用）— 88→52 文件
- [x] T2 删除 `media_importer/scraper/` 兼容层 — 15 个测试文件迁移至 features/* 新路径；guard 升级为「目录不得复活 + 全库禁 import」；顺带修复 conftest UI gate 遗漏（test_ai_config_ui/test_cinema_ui_smoke 此前未被 gate，污染非 UI 回归）
- [x] T4 落地 `pyproject.toml` + Ruff（requirements-dev 纳入；AGENTS.md/coding.md 命令更新）。存量 600+ lint 问题留 Phase 4 清零；Prettier 与 CSS 合并同 Phase 执行
- [x] T5 `core/safety.py` facade 删除（生产 0 引用）；`core/__init__.py` safety re-export 段移除；guard 改为「facade 不得复活」

测试计划：每步后跑非 UI 回归 + `test_architecture_guards.py`；T1 后浏览器 smoke 验证页面正常。

## Phase 1 功能删减（业务已拍板）

- [x] H1 Hermes 全移除：`notify/hermes_hook.py`、`/api/skill`+`/api/skills`+`/api/config/test-hermes`、`hermes` 配置块（loader/validator/view/migration）、前端 hermes 配置卡片、根目录 `hermes/` skills 目录、deploy 引用、README 章节
- [x] A1 AI 刮削移除（按 [ADR-0010](../decisions/0010-remove-ai-scraping.md)）：删 `llm_match_assist`/`web_search_config`/刮削场景策略；`llm_scraper` 退役（清理器改 `llm_client` + 内置清理提示词）；`metadata_scrape_flow` TMDB 主导化；match_engine Tier2 退役为两级
- [x] A2 `llm_client` 迁 `infrastructure/`（新建 `infrastructure/llm/LLMClient`，清理器直连）；`features/prompts` 收缩并入清理器服务；prompt 相关 API（prompt-defaults）按保留界面评估去留
- [x] A3 AI 配置界面收缩为「LLM 连接」单卡（清理器提示词为内置常量无需界面）；前端三区域/demo 弹窗/场景策略全删，JS 语法全检通过
- [x] A4 标准与文档重写：`scrape-matching.md`（两级）、`ai-prompt-design.md`（仅清理器契约）、features/scraping|ai-config|prompts 文档、ai-map、config.yaml.example
- [x] A5 失效测试清理：prompt/ai_config/scene/tier2 系列测试按新契约重写或删除

测试计划：非 UI 全量回归；刮削主流程（TMDB mock）+ 清理器 LLM（mock）专项；UI smoke。

### Phase 1 评审轮（2026-08-23，用户要求）

删码 ≠ 功能闭环。系统评审发现并修复 9 项：

| # | 问题 | 修复 |
|---|------|------|
| F1 | SECTION_MAP 无 llm 映射（保存 LLM 配置必失败） | 补 `llm` section |
| F2 | /api/health 残留 ai_assist/ai_search 检查 | 改为 llm 单项（warning 级） |
| F3 | **安全问题**：旧配置 fast_api_key 明文返回前端 | mask_sensitive 覆盖 llm 块全部 *_api_key 字段 |
| F4 | config GET 返回退役块（ai_assist/ai_scene_strategy/ai_search/confidence） | 视图层剥离（RETIRED_CONFIG_SECTIONS） |
| F5 | 刮削成败误记 record_llm_call（指标语义错） | 删除调用 |
| F6 | scrape_trace 恒写 ai_invoked=False 死字段；前端 4 处空 ai_reason 展示 | 后端注入删除 + 前端分支清理（保留模型字段兼容历史任务数据） |
| F7 | features/prompts 包 + prompt-defaults 端点残留 | 整体删除 |
| F8 | 维度 source_type 仍为 ai/ai+provider；维度弹窗 trust_ai 开关失效 | 种子+migration 收敛为 provider/file；前端开关与 ai_prompt 编辑区删除 |
| F9 | 导航文案「AI配置」等 UI 残留 | 改「LLM 配置」 |

验证：服务启动冒烟 + health/config/llm-section/维度/任务 API 闭环 + Playwright 浏览器验证（LLM 卡加载"已配置"、旧 AI 三区域消失、任务详情"AI 怎么说"区块消失、全页无 JS 错误）+ 564 tests passed。

事故记录：验证 llm section 保存时用测试数据覆盖了用户 config.yaml 的 llm 块（含 bigmodel api_key 丢失）。已恢复为 deploy 副本中已知自洽的 minimax 配置（M2.7 主 + M2.5 备）。教训：**对用户真实配置文件的写接口验证必须先备份**。

## Phase 2 状态机重构（REQ-20260822-000004，设计先行）

- [x] S0 产出设计文档（[proposal](../proposals/2026-08-23-state-machine-redesign.md)）：文件全流程状态机（拷贝→临时区→刮削→分类→入库→清理）的回退/继续/重试/幂等/崩溃恢复语义；输入含 `_drafts/2026-06-18-file-flow-cartesian-product.md` 矩阵
- [x] S1 转换表集中化：`features/tasks/transitions.py` 唯一事实源（12 动作转换表+诚实 file_location 规则+TransitionError）；task_lifecycle 降级为兼容层；全组合负向测试自动生成（16 测试）
- [x] S3 CAS 原子守护：`compare_and_update_task`（db 层）+ confirm claim（confirm_start AWAIT_REVIEW→RUNNING）+ retry/cancel 原子化；retry-all 默认仅 FAILED（D2）；import 同指纹幂等
- [x] S2 断点续跑：retry 保留 temp checkpoint（resume 默认开）+ _step_copy 检测跳过复制 + 失效自动降级
- [x] S5 确认流复用主流程步骤（_step_import_from_confirm 收敛）
- [x] S2 测试矩阵落地：`testing/file-flow-matrix.md` 转正（两级化）+ `tests/test_file_flow_matrix.py`（12 主路/异常注入）+ `tests/test_task_concurrency_and_resume.py`（8 并发/续跑/幂等）
- 意外收获：修复 `allowed_dirs_from_config` 不含 fallback_dir 的历史产品 bug（无 path_rules 配置下 fallback 入库必被安全检查拒绝）

## Phase 3 配置面简化

- [x] C1 hooks 保留（公开发布下高级用户合法扩展点，Hermes 移除后唯一钩子机制；注释定位为高级配置）
- [x] C2 manual_review 保留（AUTO_PASS→强制人工确认的合法开关，语义与两级匹配一致）
- [x] C3 配置收敛：用户 config.yaml 剥离退役块与 llm 内 7 个退役键（备份 /tmp/config.yaml.bak-phase3）；example 19 块全有效（每块有运行时消费者）
- [ ] C3 配置 API/界面随块收敛

## Phase 4 收尾

- [x] F1 CSS 合并重组：16 个存活 CSS → 6 个语义文件（tokens/layout/components/pages/config/dimensions），同步 index.html；删除 18 条已确认死规则
- [x] F2 monitor 保留现状：watcher 与权限检查仍被 API/清理器/配置直接使用，暂不做无收益迁移；notify 仅保留 hooks
- [x] F3 README.md 重写（130 行）：当前 TMDB 两级匹配、LLM 仅清理器、状态机、测试、fpk 发布均已同步
- [x] F4 Ruff 存量清零：先前 426 项问题经安全修复和逐项处理后 `ruff check media_importer tests` 全部通过；Prettier 当前未安装，前端格式化不强行引入依赖，保留为后续工具链事项

## 验收标准

- 每个 Phase 独立 commit 批次，非 UI 回归全绿 + 架构护栏通过 + check_docs 通过。
- Phase 1 后：全库无 Hermes/AI 刮削生产引用（grep 验证），配置块数下降，刮削主流程测试通过。
- Phase 4 后：fpk 构建产物可安装启动。

## 风险

- A1 清理器改造牵连 `PromptDefaults`（config 合并逻辑）——保留最小路径，避免配置迁移连锁。
- H1 deploy 脚本可能引用 hermes 目录——构建脚本同步修改并验证。
- Phase 2 触及 DB 迁移——设计文档先行评审。
