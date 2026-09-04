# Completed Items

用户验收后的事项记录在这里。记录应简短说明完成内容、关键提交、验证结果、规范回写和后续事项。

| Item | Accepted at | Commit | Summary | Verification | Follow-up |
|------|-------------|--------|---------|--------------|-----------|
| REQ-20260904-234308 发布 fnOS 0.3.31 GitHub Release | 2026-09-05 | `82012d4` / tag `v0.3.31` | 将 0.3.31 FPK 与 SHA-256 发布到公开 GitHub Releases；[发布计划](../_archive/2026-09-05-fnos-0-3-31-github-release/2026-09-04-chore-publish-fnos-0-3-31-release-plan.md) | 47 项发布专项、包内容、源码指纹和校验门禁 PASS；匿名回下载 11,818,856 字节且 SHA-256 `bb9a9a71d4d9d955a973af76931afbea4e4282ebfdc32f096c62f4d4f70c3c3d`；用户确认 `FNOS_UAT PASS` | 已登记为最近 fnOS 验收正常版本并转为正式 Latest Release |
| REQ-20260903-234230 互联网媒体命名场景覆盖与真实刮削验收 | 2026-09-04 | `add3765` | 以 Plex/Jellyfin/Servarr/TRaSH/Kodi 公开规范建立 43 个电影/剧集场景族、129 个正向样本和 21 个安全负例；加固日期集、动漫绝对集、中文季度目录、目录 Provider ID、官方翻译别名和多候选裁决；[计划](../_archive/2026-09-04-internet-media-name-coverage/2026-09-03-test-internet-media-name-coverage-plan.md)、[方案](../_archive/2026-09-04-internet-media-name-coverage/2026-09-03-internet-media-name-coverage.md)、[报告](../testing/internet-media-name-coverage.md) | REAL_TMDB 124/129（96.12%）、场景族 40/43（93.02%）、安全负例 21/21；本地专项 100、完整含 Chromium 1108、架构护栏 18、Ruff/compileall/JS/文档/diff PASS；LOCAL_BUILD 0.3.27 PASS，FPK SHA-256 `33723d41a7209a000e4fdda379420e03fe2db9590f6bf4aa5e5fbbb0c8a7ada7` | 用户接受 3 个 `VIDEO_TS/*.VOB`、单一繁中标题及季度语义冲突共 5 个样本保留人工确认；fnOS UAT/生产仍未执行 |
| REQ-20260609-STATUS01 | 2026-06-10 | - | Status+Stage 双层任务状态模型重构：新增 stage 字段(PENDING/QUEUED/RUNNING/AWAIT_REVIEW/DONE)，DB 迁移逻辑，前端筛选映射，B/C 类测试文件 | stage 转换测试、DB 迁移测试通过 | 已归档 |
| REQ-20260608-BC001 | 2026-06-10 | - | 前端 B/C 类功能增强：B1任务批量动作、B2详情弹窗增强、B3回收批量操作；C1海报细化、C2提示词维度重写、C3模块化设计系统 | 代码检查通过 | 已归档 |
| 2026-06 AI 配置系列（redesign/restructure/tier2） | 2026-08-22 批量归档 | 8a5e425, cb59d55, 4e745cc 等 | AI 配置重设计、三区域改造、Tier2 上下文匹配 | 627+ tests pass（历史记录） | 已归档至 `_archive/2026-08-22-plans-cleanup/` |
| 2026-06 刮削系列（info-split/multi-match/behavior-normalization/field-propagation/user-prompt） | 2026-08-22 批量归档 | dbf6e74, 028a7c6, 3c403f5 等 | 信息职责 6 层拆分、多匹配规则、行为规范化、字段透传、user_prompt 统一管理 | 632 tests pass（历史记录） | 已归档至 `_archive/2026-08-22-plans-cleanup/` |
| 2026-06 清理迁移主计划 Phase 1-6 | 2026-08-22 批量归档 | 7fc7677…b8f6ccc 共 14 commits | 前端 P0 修复、旧任务 JS 归档、confirm_reason 退役、scraper 整包迁移、core.db→infrastructure.db facade | pytest 通过 + architecture guards | 已归档至 `_archive/2026-08-22-plans-cleanup/` |
| 2026-06 修复与优化系列（dimension/simulator/file-split 等 8 项） | 2026-08-22 批量归档 | d4fc4f5, b090488 等 | 维度开关、模拟器/源清理/任务卡片五项修复、文件拆分、优化项、兼容化清理、验收测试计划 | 对应测试存在 | 已归档至 `_archive/2026-08-22-plans-cleanup/` |
| 停摆前 5 项待验收（feature-first 重组 / AI-efficient 收尾 / Status+Stage / AI 配置三区域 / 清理迁移主计划） | 2026-08-22 批量豁免 | 42c88b9…b8f6ccc | 2026-06-02 至 06-20 全部已实施事项 | 用户授权工程验收 AI 自判；代码稳定运行至今 + 历史测试记录 | 前端全流程验收并入前端方向重估（backlog-reevaluation §1） |
| REQ-20260616-000001 待确认流程端到端整治 | 2026-08-22 关闭 | 35fe408, a21fe9f 等 | P0 数据正确性 + 确认交互重构 + 决策路径优化 | `tests/test_p0_confirm_workflow_fixes.py` 存在；ADR-0009 落地 | 无 |
| REQ-20260822-000002 文档治理与 AI 导航收敛 | 2026-08-22 | 未单独提交（文档批变更） | 断链修复、30+ 文件归档、INDEX 并入 ai-map、AGENTS.md 重写、轻量开发流程规范、check_docs.py 防漂移、backlog-reevaluation 重估清单 | `check_docs.py` OK 91 文件；架构护栏 18 passed；新会话模拟导航自验通过 | 无（用户豁免） |
| REQ-20260822-000001 全项目功能简洁化评估 | 2026-08-22 | 未单独提交（文档批变更） | 实测盘点（前端 25k 行含 37% 死代码、69 端点、20 配置块）、业务拍板（B1 只做减法/B2 移除 Hermes+AI 刮削/B3 公开发布）、ADR-0010、简洁化路线图（Phase 0-4）、注册 REQ-20260822/000004/000005 | `check_docs.py` OK；提案+计划+ADR 齐备 | 进入 REQ-20260822-000003 执行 |
| 简洁化 Phase 0 工程基础 | 2026-08-22 | 未提交 | T1 删 36 前端死文件（-9,376 行）；T2 删 scraper/ 兼容层（15 测试迁移）；T4 pyproject+Ruff 落地；T5 删 core/safety.py facade；修复 conftest UI gate 遗漏 | 710 passed（当时）/ guards 18 passed / ruff 新改文件通过 | — |
| 简洁化 Phase 1 功能删减 | 2026-08-22 | 未提交 | H1 Hermes 全移除（notify/hermes_hook+3 API+配置块+前端+hermes/ 目录+deploy）；A1 AI 刮削移除（llm_scraper 等 5 文件删、Tier2 退役两级化、模拟器两级、~20 测试文件删除/重写）；A1+ 限制级 9 国分级增强+维度 default_value 机制（13 新测试）；A2 config 双块收缩为 llm 块；A3 AI 配置界面三区域→LLM 单卡；A4 scrape-matching/ai-prompt-design 标准重写、features/prompts+ai-config 归档 | 566 passed / check_docs 88 文件 OK / 全部 JS node --check 通过 待启动 |

## Rules

- 只有用户确认验收后才能写入本文件。
- 如果本次工作沉淀出长期规则，必须同步更新 `docs/standards/` 或 `AGENTS.md`。
- 已完成或被替代的 plan/proposal 应移入 `docs/_archive/`，避免 AI 后续优先扫描旧方案。
| REQ-20260822-000004 状态机重构 | 2026-08-25 | 未提交（本批） | S1 转换表集中化（transitions.py 唯一事实源+负向全组合测试）；S3 CAS 原子守护（confirm claim/retry/cancel/retry-all 收敛/import 幂等）；S2 copy-checkpoint 断点续跑；S5 确认流复用；测试矩阵转正+12 主路回归+8 并发续跑测试；修复 allowed_dirs 缺 fallback_dir 历史 bug | 599+ tests passed（新增 36 个生命周期测试）/ ruff 本次改动文件通过 | — |
| 简洁化 Phase 4 收尾 | 2026-08-26 | 未提交（本批） | CSS 16→6 语义文件、F2 monitor 保留评估、README 562→130 行、Ruff 全量清零、fpk 0.2.0 构建成功（8.2M）；Prettier 未安装，暂不引入依赖 | check_docs 89 文件 OK；专项状态机回归 36 passed；FPK 打包成功 | Ruff 剩余 179 项历史基线，后续独立清零 |
| 二轮文档治理（简洁化完成后） | 2026-08-27 | 未提交（本批） | 路线图+5 proposal 归档（活跃目录清零）；新增 standards/frontend.md（CSS 6 文件/视图模型/文案红线/工具复用）与 standards/backend.md（分层/状态机/两级匹配/LLM 边界/质量门禁）；回归补口 13 测试（naming/dedup/watcher）并修复 ignore_patterns 不生效 bug | check_docs 86 文件 OK（含退役词扫描）/ 613 tests | — |
