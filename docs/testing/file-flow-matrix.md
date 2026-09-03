---
title: "文件全流程文档:从源目录到入库的笛卡尔积"
type: process-doc
date: 2026-06-18
status: draft
confidence: high
related:
  - docs/architecture/import-pipeline.md
  - docs/architecture/task-lifecycle.md
  - docs/architecture/scraping.md
  - docs/standards/scrape-matching.md
  - docs/standards/info-architecture.md
  - docs/features/import-flow.md
  - docs/features/tasks.md
  - docs/features/source-files.md
  - docs/_drafts/2026-06-18-spec-code-mismatch-review.md
---

---
title: file-flow-test-matrix
type: standard
date: 2026-08-25
status: accepted
---

# 文件全流程测试矩阵（笛卡尔积覆盖）

> Phase 2 S4 转正（原 _drafts 草稿）。ADR-0010 两级匹配更新：
> B10-B14（AI 分支）已退役，等价替换为 Tier1 低匹配→英文回退→仍低→NEEDS_CONFIRM；
> M02 的 CONTEXT_PASS 路径收敛进 M01（AUTO_PASS）。回归套件落地：tests/test_file_flow_matrix.py。

> 目的:把"一个映射文件从源目录到入库(或失败/取消)所有可能路径"列成一张完整的笛卡尔积矩阵,
> 作为前台/后台/Playwright 自动化测试用例设计的**单一事实源**。
> 任何"文件流程"的回归脚本必须能映射到本文档的某个组合。

---

## 0. 阅读指引

- **维度(A)**:Pipeline 环节(scan / scrape / validate / classify / dedup / rename / confirm / import / source-clean / notify / record)。大文件复制只属于 import，不再有独立中心中转步骤。
- **维度(B)**:每环节的"分支条件"(数据形态、Provider/AI 状态、用户操作)。
- **维度(C)**:每环节的"异常/边界"(文件不存在、权限、磁盘、配置缺失、用户取消)。
- **维度(D)**:状态结果(status+stage)与文件位置(file_location) 终结态。
- 每一格 = (A, B, C) 的一种组合,对应一个 Playwright 用例或后台单测。

---

## 1. 维度定义(8 维)

### A · Pipeline 环节

| 代号 | 环节 | 入口 | 必触后端 | 前台可见性 |
|:----:|------|------|----------|------------|
| A1 | scan(扫描源目录) | `POST /api/run`,`POST /api/queue/retry-all`,watcher | `features/import_flow/scan_service` | 首页"立即扫描",任务工作台列表 |
| A2 | target-stage(目标侧任务暂存) | 全部决策完成后的普通入库 | `features/import_flow/services/file_operations` | 确认前不复制；确认后直接写目标任务暂存并显示真实字节进度 |
| A3 | scrape(刮削) | pipeline runner | `features/scraping/_match_tiers_impl` | 任务卡片"AI 怎么说/最终用了",详情 L1-L4 |
| A4 | validate(决策) | pipeline runner | `features/import_flow/services/review` | 任务状态变 PENDING/AWAIT_REVIEW 或自动走 |
| A5 | classify(分类) | pipeline runner | `features/import_flow/services/classification` | 详情"入库预览" import_path |
| A6 | dedup(去重) | pipeline runner | `features/import_flow/services/dedup` | 详情 dedup 块(未实现迁移,见评审 §3.7) |
| A7 | rename(重命名) | pipeline runner | `features/import_flow/services/naming` | final_filename |
| A8 | import(入库) | pipeline runner + confirm | `features/import_flow/services/import_service` | 跨盘写入、校验和发布阶段可见；来源策略记录后才变 SUCCESS |
| A9 | notify(通知) | pipeline runner | `notify/hermes_hook` | Hermes 配置页 |
| A10 | record(记录) | pipeline runner | `core/db` + `core/metrics` | dashboard 指标,任务记录 |
| A11 | confirm(人工确认) | 用户操作 | `features/import_flow/confirm` | 任务详情弹窗"确认入库"按钮 |
| A12 | source-clean(源清理) | 用户操作 / watcher | `features/source_cleaning/cleaner` | 源目录清理页,records |

### B · 数据/环境分支(每环节独立)

| 代号 | 分支 | 含义 | 影响环节 |
|:----:|------|------|---------|
| B1 | 文件名清晰 | 形如 `Title.Year.Quality.ext` | A3 |
| B2 | 文件名脏 | 含多余字符、年份误提 | A3 |
| B3 | 文件名纯中文 | 中文译名(无英文原名) | A3 |
| B4 | 文件名含季集 | `S01E02` / `第3季` | A3+A5 |
| B5 | 文件名随机字符 | 不可识别 | A3 → FAILED |
| B6 | 同名文件重复扫描 | 已存在 task | A1 |
| B7 | Provider 唯一精确 | Tier 1 1 匹配 | A3 → AUTO_PASS |
| B8 | Provider 多精确 | Tier 1 ≥2 匹配 | A3 → NEEDS_CONFIRM, tier=1 |
| B9 | Provider 模糊/无 | Tier 1 fallback | A3 → Tier 2 |
| B10 | AI 高确定性 | certainty=high | A3 → CONTEXT_PASS |
| B11 | AI 中确定性 | certainty=medium | A3 → NEEDS_CONFIRM, tier=2 |
| B12 | AI is_valid=false | 垃圾文件 | A3 → FAILED |
| B13 | AI 不可用 | 异常/超时 | A3 → Tier 3 |
| B14 | Tier 3 降级有候选 | first_candidate | A3 → NEEDS_CONFIRM, tier=3 |
| B15 | Tier 3 无候选 | Provider 全无 | A3 → NEEDS_CONFIRM, 无 selected_candidate |
| B16 | 维度完整 | Provider 命中全部 | A5 直接分类 |
| B17 | 维度缺失 | AI 联网补全 / 进入 review | A5 → review |
| B18 | 源文件无字幕 | 视频单文件 | A8 |
| B19 | 源文件带字幕 | 视频+同名字幕 | A8 + 字幕入库 |
| B20 | 入库目录同名 | 目标已存在同名 | A6 dedup 决策 |
| B21 | 入库目录无写权限 | IOError | A8 → FAILED |
| B22 | 跨设备移动 | os.rename 失败 | A8 fallback copy+delete |
| B23 | 用户结束排队/运行任务 | `POST /api/tasks/{id}/dispose` | 排队直接 CANCELLED；运行中 202 后在安全检查点 CANCELLED |
| B24 | 用户放弃待确认/失败任务 | `POST /api/tasks/{id}/dispose` | status → SKIPPED，并明确来源保留/回收/永久删除 |
| B25 | 用户重试 | `POST /api/tasks/{id}/retry` | status → PENDING+QUEUED |
| B26 | 用户改维度保存 | `POST /api/tasks/{id}/preview` | A5 重跑分类 |
| B27 | 用户重新刮削 | `POST /api/tasks/{id}/rescrape` | A3 重跑 |
| B28 | 用户改名 | `POST /api/tasks/{id}/rename` | 文件改名 |
| B29 | 用户删除任务记录 | `POST /api/tasks/{id}/delete` | 只删已结束记录；来源与片库文件不变 |
| B30 | 手动扫描指定文件 | `POST /api/run/file` | A1 单文件 |

### C · 异常/边界

| 代号 | 异常 | 检测位置 | 预期行为 |
|:----:|------|---------|---------|
| C1 | 源文件不存在 | A3 / A8 | PipelineError → FAILED；目标片库不变 |
| C2 | 目标任务暂存不可写 | A2/A8 | FAILED；来源保持，正式片库文件不变 |
| C3 | 目标片库空间不足 | A2/A8 | 传输前失败关闭；来源保持，不创建正式文件 |
| C4 | Provider 不可用 | A3 | 降级 Tier 2 |
| C5 | LLM 不可用 | A3 | 降级 Tier 3 |
| C6 | LLM 超时/429 | A3 | 重试 → Tier 3 |
| C7 | SQLite 锁 | A10 | 重试或 PipelineError |
| C8 | 目标文件被占用 | A8 | IOError → FAILED |
| C9 | 文件名含 `../` | A1 / A7 | 路径安全检查拦截 |
| C10 | 文件名含特殊 Unicode / emoji | A3 | 正常处理 |
| C11 | 空文件名 | A1 | 过滤或拒绝 |
| C12 | 超长文件名 (>255 字符) | A1 | 截断或拒绝 |
| C13 | 零字节视频 | A3 | 刮削可继续(仅用文件名) |
| C14 | 损坏的视频头 | A3 | 维度推导失败,降级 |
| C15 | GBK/Shift-JIS 编码 | A1 | 正确解码 |
| C16 | 源目录符号链接循环 | A1 | 深度限制生效 |
| C17 | source_dir 为空 | A1 | 返回 0 任务 |
| C18 | source_dir 不存在 | A1 | 错误但不崩溃 |
| C19 | recycle_dir 不可写 | A6 replace 模式 | PipelineError → FAILED |
| C20 | Hermes URL 不可达 | A9 | 日志记录,不阻断 |
| C21 | config 非法 | 启动 | validate 拦截 |
| C22 | path_rules 为空 | A5 | 兜底目录生效 |
| C23 | 模拟器 vs 正式字段不一致 | scrape_preview_job vs scrape.py | 不应发生;测试断言 |
| C24 | 服务异常崩溃(KILL) | 启动 | 孤儿任务 FAILED(见 task-lifecycle.md §Orphan) |
| C25 | 暂停队列中触发扫描 | A1 | 任务入队但不执行,resume 后执行 |
| C26 | AI 联网搜索失败 | A3 维度补充 | 降级到 ai_assist |
| C27 | confirm 后来源被外部删除 | A11/A8 | FAILED；不创建目标暂存或正式文件 |
| C28 | 回收站记录与文件不一致 | recycle | UI 标"文件不存在" |

### D · 终结态

| status | stage | file_location | 触发 |
|--------|-------|---------------|------|
| `PENDING` | `QUEUED` | `source` | A1 完成,等待 |
| `PENDING` | `RUNNING` | `source` | 识别、确认后传输或来源处理进行中；目标临时文件不改变业务位置 |
| `PENDING` | `AWAIT_REVIEW` | 通常 `source` | 识别/规则/冲突需确认，尚未传输大文件 |
| `SUCCESS` | `DONE` | `import` | A8 完成,文件入库 |
| `SKIPPED` | `DONE` | `source` | B24 / 去重 skip / 用户忽略 |
| `FAILED` | `DONE` | `source` | 任何 C 异常 / B12 / B23；歧义恢复另以 `bundle_state=RECOVERY_REQUIRED` 提示人工检查 |
| `CANCELLED` | `DONE` | `source` | B23 |
| `CANCELLED`/`SKIPPED` | `DONE` | `source`/`recycle`/`deleted` | dispose 后按用户选择记录来源结果 |

---

## 2. 笛卡尔积主矩阵(精简版 32 路)

> 只列出"功能正常分支"的主要场景,用于产品 happy-path 自动化测试设计;
> 异常分支在 §3 单列。所有组合覆盖一个真实文件从源目录到入库(或失败/取消)的所有可能。

### 2.1 自动通过(AUTO_PASS / CONTEXT_PASS,不需用户干预)

| # | 流程 | 数据形态 | 期望终结态 | 前台可见性 |
|---|------|---------|-----------|-----------|
| M01 | scan → scrape(B7)→ classify(B16)→ dedup → [confirm] → direct import | `Inception.2010.1080p.mp4` | 正式规则命中为 `SUCCESS/DONE`；只命中兜底则先 `AWAIT_REVIEW`，明确接受后 `SUCCESS/DONE + FALLBACK_PENDING` | 决策完成前来源保持原位且目标零写入；传输时显示真实字节进度 |
| M02 | scan → scrape(B10)→ import | `Dune.Part.Two.2024.1080p.mkv`(AI 命中) | `SUCCESS/DONE` | 同上 |
| M03 | 季集文件入库 | `Breaking.Bad.S01E02.1080p.mkv` | `SUCCESS/DONE`,import_path=电视剧/Season 01/ | 详情 final_filename 补零 |
| M04 | 字幕伴生入库 | `Movie.mkv` + `Movie.srt` 同目录 | `SUCCESS/DONE`,目标目录含 srt | 详情显示 subtitle 列表 |
| M05 | 模拟器验证字段一致 | 任何清晰文件名 | scrape_preview_job 与 scrape.py 同字段 | 模拟器页面 6 步完整 |

### 2.2 需用户确认(NEEDS_CONFIRM → AWAIT_REVIEW → confirm → SUCCESS)

| # | 流程 | 数据形态 | 期望终结态 | 前台可见性 |
|---|------|---------|-----------|-----------|
| M06 | scan → scrape(B8)→ AWAIT_REVIEW → 用户选候选 → confirm | `美丽人生.mkv`(7 同名) | `SUCCESS/DONE` | 任务卡"待确认",详情显示候选列表,确认后入库 |
| M07 | scrape(B11)→ AWAIT_REVIEW → 用户改维度 → preview → confirm | `Movie.1080p.mkv`(AI 模糊) | `SUCCESS/DONE` | 详情可改维度,预览后确认 |
| M08 | scrape(B13/B14)→ AWAIT_REVIEW → 用户手动选择 | `Unknown.2024.mkv`(AI 不可用) | `SUCCESS/DONE` | 详情显示 Provider 候选,用户选 |
| M09 | AWAIT_REVIEW → 用户重新刮削(B27)→ 选候选 → confirm | 任意 AWAIT_REVIEW | `SUCCESS/DONE` | 详情"手动刮削"按钮,选 candidate 后入库 |
| M10 | AWAIT_REVIEW → 用户改名(B28)→ confirm | `* (junk).mkv` | `SUCCESS/DONE` | 详情文件名可编辑 |
| M10a | SUCCESS/FALLBACK_PENDING → 创建关联重新整理 → 改维度/重刮 → confirm | 已在待整理区的影片 + 字幕 | 父任务保持 SUCCESS；新任务 SUCCESS/DONE，父子 ORGANIZED | 原任务显示“已安全入库，等待整理”，新任务显示正式规则预览和整组移动进度 |

### 2.3 失败/取消/跳过

| # | 流程 | 触发 | 期望终结态 | 前台可见性 |
|---|------|------|-----------|-----------|
| M11 | scrape(B12)→ FAILED | `123uyyt.mkv` | `FAILED/DONE`,file_location=source | 任务卡 ❌ + ai_reason + 🔄 重试 |
| M12 | 用户结束 | QUEUED/RUNNING 时 dispose | `CANCELLED/DONE`，运行中先显示“正在安全停止” | 来源去向弹窗；片库不变 |
| M13 | 用户不再处理 | AWAIT_REVIEW/FAILED 时 dispose | `SKIPPED/DONE` | 明确选择保留、回收或已启用的永久删除新资源 |
| M14 | 用户删除记录 | 任一已结束任务 delete | 记录消失，来源与片库文件不变 | 二次确认明确“只删除记录” |
| M15 | 重试失败 | FAILED 任务 retry | `PENDING/QUEUED` → 重新走流程 | 任务卡回到"排队中" |
| M16 | 重试全部失败 | 仪表盘 retry-all | 全部 FAILED/SKIPPED/CANCELLED → QUEUED | dashboard 按钮 |

### 2.4 批量操作

| # | 流程 | 触发 | 期望 | 前台可见性 |
|---|------|------|------|-----------|
| M17 | 批量入库 | 普通 AWAIT_REVIEW 多任务 confirm-all | 普通任务 → SUCCESS；兜底、重新整理和冲突任务排除 | 工具栏“批量入库”只对可批量项出现 |
| M18 | 批量重试 | FAILED/SKIPPED/CANCELLED 多选 retry | 全部 → QUEUED | 工具栏"批量重试" |
| M19 | 批量结束处理 | 活动/异常任务多选 dispose | 按状态 CANCELLED/SKIPPED，逐项来源结果 | 工具栏“结束处理”统一选择来源去向 |
| M20 | 批量删除记录 | 已结束任务多选 delete | 仅记录删除，所有文件不变 | 工具栏“删除记录” |
| M21 | 批量清空选择 | clear | 工具栏隐藏 | 工具栏"清空选择" |
| M22 | 批量超限 | 选中 >50 | Toast 警告 | 工具栏提示 |

### 2.5 源目录清理(独立流程)

| # | 流程 | 数据 | 期望 | 前台可见性 |
|---|------|------|------|-----------|
| M23 | 源清理预览 | 源目录混合文件 | preview 返回垃圾列表 | 源清理页 preview |
| M24 | AI 辅助源清理 | 启用 ai_assist | preview 含 AI 标记 | AI 预览 |
| M25 | 执行源清理 | 预览确认 | 垃圾文件入回收 | 执行按钮 + records |
| M26 | 源清理记录查询 | 历史 records | 列表正常 | records 列表 |

### 2.6 回收站

| # | 流程 | 触发 | 期望 | 前台可见性 |
|---|------|------|------|-----------|
| M27 | 回收列表 | 任何回收项 | list 返回 | 回收站页 |
| M28 | 回收恢复 | 单条 restore | 文件回原位 | 行操作 |
| M29 | 回收永久删除 | 单条 delete(force) | 文件物理删除 | 行操作 |
| M30 | 清理过期项 | 30 天前 records | 自动清理 | 顶栏"清理过期项" |

### 2.7 模拟器与配置

| # | 流程 | 数据 | 期望 | 前台可见性 |
|---|------|------|------|-----------|
| M31 | 模拟器 6 步时间轴 | 任意清晰文件名 | 步骤逐步显示 | 模拟器页 |
| M32 | 模拟器 NEEDS_CONFIRM 展示 | 多候选文件名 | 显示候选第一名 + 确认原因 | 模拟器结果区 |

---

## 3. 异常矩阵(每环节关键异常)

> 用于"故障注入"测试用例设计。每条都标注关键检测位置。

### 3.1 A1 扫描

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E1.1 | source_dir 不存在(C18) | watcher / `POST /api/run` | 错误提示,不崩溃 |
| E1.2 | source_dir 空(C17) | 同上 | 0 任务 |
| E1.3 | 重复扫描同名(B6) | scan_service | 已存在则跳过 |
| E1.4 | 符号链接循环(C16) | scan_service | 深度限制 |
| E1.5 | 文件名 `../`(C9) | 文件名清洗 | 拦截 |
| E1.6 | 超长文件名(C12) | scan_service | 截断/拒绝 |
| E1.7 | GBK/Shift-JIS 编码(C15) | 文件名解码 | 正常处理 |
| E1.8 | 源文件无读权限 | scan_service | 跳过 |

### 3.2 A2 目标侧任务暂存与中断恢复

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E2.1 | 确认前来源消失(C1) | import flow | FAILED；不创建目标暂存 |
| E2.2 | 目标暂存不可写(C2) | target readiness + verified copy | FAILED；来源保持，正式目标不变 |
| E2.3 | 目标空间不足(C3) | target readiness | 传输前 FAILED；不创建正式目标 |
| E2.4 | 直接目标复制中停止 | phase callback + bundle journal | 删除本任务 `.copying/.bundle.tmp`，来源和片库现有文件不变 |
| E2.5 | 服务在提交前中断 | startup bundle recovery | 清理任务清单证明归属的临时成员，任务 FAILED，可从来源整任务重来 |
| E2.6 | 服务在完整提交后中断 | startup bundle recovery | 逐成员 SHA-256 复核后 SUCCESS，不重复复制且保留来源 |
| E2.7 | 部分提交或指纹变化 | startup bundle recovery | 文件全部保留，任务进入人工检查，禁止自动继续 |

### 3.3 A3 刮削

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E3.1 | Provider 不可用(C4) | match_engine | 降级 Tier 2 |
| E3.2 | LLM 不可用(C5) | LLMScraper | 降级 Tier 3 |
| E3.3 | LLM 超时/429(C6) | retry → fallback | 降级 Tier 3 |
| E3.4 | 零字节视频(C13) | pipeline | 刮削继续(仅用文件名) |
| E3.5 | 损坏的视频头(C14) | file_analyzer | 维度推导失败 |
| E3.6 | AI 联网搜索失败(C26) | web_search | 降级 ai_assist |
| E3.7 | Tier 3 无候选(B15) | match_engine | NEEDS_CONFIRM, 无 selected_candidate |
| E3.8 | AI 字段契约违反(C23) | scrape.py | 不应发生(测试断言) |

### 3.4 A4-A5 验证/分类

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E4.1 | path_rules 空(C22) | classification_rules | 兜底目录 |
| E4.2 | path_rules 不匹配 | classification | 兜底 |
| E4.3 | 维度不完整(B17) | review | AWAIT_REVIEW,用户补 |
| E4.4 | 维度来源不被信任 | review | AWAIT_REVIEW |

### 3.5 A6 去重

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E5.1 | 入库目录同名(B20) | dedup | 走策略(skip/replace/rename) |
| E5.2 | replace 时 recycle 不可写(C19) | dedup | PipelineError → FAILED |

### 3.6 A8 入库

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E6.1 | 目标无写权限(B21) | file_operations | IOError → FAILED |
| E6.2 | 目标文件被占用(C8) | import_service | IOError → FAILED |
| E6.3 | 跨设备移动(B22) | os.rename 失败 | fallback copy+delete |
| E6.4 | confirm 时文件已被外部删除(C27) | confirm.py | PipelineError → FAILED |

### 3.7 A10 记录

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E7.1 | SQLite 锁(C7) | db | 重试 |
| E7.2 | metrics 计数错 | metrics | 重新计算 |

### 3.8 A9 通知

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E8.1 | Hermes URL 不可达(C20) | hermes_hook | 日志记录,SUCCESS 不阻断 |
| E8.2 | 重复错误冷却 | hermes_hook | 抑制重复 |

### 3.9 启动/全局

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E9.1 | config 非法(C21) | validate_config | 启动拒绝 |
| E9.2 | 服务异常崩溃(C24) | 启动 | 孤儿 FAILED |
| E9.3 | 暂停队列时扫描(C25) | queue | 入队但不执行 |
| E9.4 | 回收站记录与文件不一致(C28) | recycle | UI 标"文件不存在" |

### 3.10 用户操作

| # | 异常 | 检测 | 期望 |
|---|------|------|------|
| E10.1 | cancel 非 PENDING/QUEUED | cancel_service | 400 拒绝 |
| E10.2 | reclassify 非 PENDING/AWAIT_REVIEW | review_service | 400 拒绝 |
| E10.3 | delete 非 batchable status | delete_service | 400 拒绝 |
| E10.4 | confirm 时任务不是 AWAIT_REVIEW | confirm | 400 拒绝 |

---

## 4. 终结态对照(给前台的"任务卡片显示规则"使用)

| status | stage | 主按钮 | 次按钮 | 详情按钮 | 文件名/维度可编辑 |
|--------|-------|--------|--------|---------|----------------|
| PENDING | QUEUED | 取消 | — | 详情 | 否/否 |
| PENDING | RUNNING | — | — | 详情 | 否/否 |
| PENDING | AWAIT_REVIEW | 去确认 | — | 详情 | 是/是 |
| SUCCESS | DONE | — | — | 详情 | 否/否 |
| FAILED | DONE | 去重试 | 移入回收 | 详情 | 否/否 |
| SKIPPED | DONE | 去重试 | — | 详情 | 否/否 |
| CANCELLED | DONE | 重新投入 | — | 详情 | 否/否 |

(本表与 `docs/architecture/api.md:111-128` 严格一致)

---

## 5. 与 6 层信息职责的对应

每个任务卡片 + 详情显示的字段必须能从 `scrape_result` 6 层中读到,不能从拼接串反解析(见 `standards/info-architecture.md §6`)。

| 视图 | 必备层 | 禁用 |
|------|--------|------|
| 任务卡片 | L1(match_level)+ L2(tier_short_reason)+ L3(ai_reason)+ L4(selected_candidate)+ 维度标签 | confirm_reason 拼接串、raw trace_steps |
| 详情弹窗 | L1-L6 全部 | 自行拼装(应走 `buildMatchPathData`) |
| 模拟器 | 同详情 | 同上 |

---

## 6. 测试覆盖映射(给 Playwright 自动化用)

每个 §2 编号 + 每个 §3 编号应对应至少 1 个 Playwright 用例或后台单测。

| 场景类型 | 数量 | Playwright 必需 | 后台单测必需 |
|---------|:----:|:----------------:|:------------:|
| §2 主矩阵 | 32 | ✅ 全部 | ✅ 全部 |
| §3.1 扫描异常 | 8 | E1.5 必查 | ✅ 全部 |
| §3.2 复制异常 | 3 | — | ✅ 全部 |
| §3.3 刮削异常 | 8 | E3.1/E3.2 至少 | ✅ 全部 |
| §3.4 验证/分类异常 | 4 | E4.1 | ✅ 全部 |
| §3.5 去重异常 | 2 | E5.1 | ✅ 全部 |
| §3.6 入库异常 | 4 | E6.1 | ✅ 全部 |
| §3.7 记录异常 | 2 | — | ✅ 全部 |
| §3.8 通知异常 | 2 | — | ✅ 全部 |
| §3.9 启动异常 | 4 | E9.2 | ✅ 全部 |
| §3.10 用户操作 | 4 | ✅ 全部 | ✅ 全部 |
| **合计** | **73** | **≥ 25** | **≥ 60** |

---

## 7. 现有覆盖与缺口(对照 §6)

| 类别 | 已有 | 缺口 |
|------|------|------|
| §2 主矩阵 Playwright | 关键文件流 9 场 | F01-F08 覆盖电影、剧集字幕、兜底、三种冲突决策和两种来源处置；F13 覆盖真实下载目录身份边界、广告/小片段过滤和待确认解释；批量、手动刮削等仍由独立 UI 用例覆盖 |
| §2 主矩阵 后台 | 多数有(feature_*_task_*.py) | 继续按具体行为补齐，不得用本矩阵代替全部 32 路 |
| §3 异常 Playwright | 4 场 | F09-F12 覆盖复制中断重试、完整提交恢复、目标变化人工检查，以及外部 SIGKILL 后重启与前端重试；其他异常仍以专项为主 |
| §3 异常 后台 | 文件安全主路径已有专项 | 文件名编码、跨设备和外部 Provider 故障继续由对应专项维护 |
| §3.10 用户操作 Playwright | 冲突确认、兜底确认、重试已覆盖 | 取消、批量等由任务处置与工作台 UI 套件覆盖 |

**本地证据基线（2026-09-03）**：`tests/test_full_frontend_flow_matrix_browser_ui.py`
从首页真实点击扫描开始完成 F01-F13，并逐场保存源目录、片库、回收区文件树、
SHA-256、任务 JSON、浏览器错误和截图到
`output/full-frontend-flow-matrix/<run-id>/`。它是关键文件安全旅程的 E2E 基线，
不是对 §2 全 32 路和 §3 全部异常的替代；未覆盖项仍必须由专项 UI/后台测试证明。
F12 使用正式分块复制，仅在进度回调处测试性降速；强杀动作来自父测试进程的
`SIGKILL`，并记录精确 PID、退出码、临时文件大小及重启后的文件哈希。
F13 使用根直属单片、中文发布目录+英文视频名、无关目录、季目录、BDMV、合集、
错误年份目录、动漫发布名、弱文件名和身份冲突等常见下载形态；广告视频、小体积
蓝光片段和未完成下载不得建任务。最新完整证据为
`output/full-frontend-flow-matrix/20260903T123229/`：13/13 场景通过、17 张浏览器截图，
F13 为 9 个自动完成、3 个待确认、3 个过滤，页面错误与 HTTP 5xx 均为 0。

---

## 8. 维护规则

- 任何"文件流程"新场景必须先在 §2 或 §3 加行,再写测试。
- 任何状态转换变更先改 §1D,再改 §4 矩阵。
- 任何新 API 端点必须在 §6 测试覆盖映射中加行。
- 文档与代码不一致时,以 `docs/_drafts/2026-06-18-spec-code-mismatch-review.md` 评审结论为准。
