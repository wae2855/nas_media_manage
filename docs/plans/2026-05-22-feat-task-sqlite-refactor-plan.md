---
title: "feat: 任务系统 SQLite 重构 + 人工确认 + 隔离区 + Hermes API"
type: plan
date: 2026-05-22
status: approved
brainstorm: docs/brainstorms/2026-05-22-task-sqlite-redesign-brainstorm.md
confidence: medium
---

# 任务系统 SQLite 重构

## 一、Problem Statement

当前任务系统采用"内存字典 + JSON 文件"存储，无法去重、无历史追溯、字幕无独立身份、无人工确认机制。

## 二、Target End State

1. 任务数据持久化到 SQLite，支持分页查询、历史追溯、源端去重
2. 字幕独立为 task_subtitles 子表，每个字幕有独立状态和入库路径
3. 源端去重 + 隔离区机制：防止重复处理和 AI Token 浪费
4. 人工确认机制：启用后停在 classify，用户确认后才入库
5. WebUI 新任务面板：分页、状态筛选 Tab、详情/字幕/回退弹窗、维度编辑
6. 全部操作通过 REST API 暴露，Hermes 可调用

## 三、Scope

### In Scope
- db.py 数据库模块（全新）
- task_manager.py 全面重写
- pipeline.py 核心流程改造（分流点、字幕子记录、确认暂停）
- api_server.py 新增 7 个端点 + 改造 4 个
- file_scanner.py 源端去重逻辑
- config_loader.py 新增 2 个配置项
- WebUI app.js 全面重写任务模块
- WebUI index.html 新任务面板 HTML
- WebUI styles.css 弹窗/分页/状态筛选/双行表格样式
- deploy/ 目录同步

### Out of Scope
- 配置迁移数据库
- 日志迁移数据库
- 旧数据迁移（tasks.json → SQLite）
- 并发处理
- fnOS 文件管理器集成
- 隔离区自动清理

## 四、Proposed Solution

新建 `db.py` 封装 SQLite 操作，`task_manager.py` 重写为薄封装层。Pipeline 在 classify 后分流：未启用确认则继续 dedup→import；启用确认则停为 CONFIRMING，文件在 temp，待用户确认后继续。字幕独立入 task_subtitles 表。WebUI 用弹窗模式展示详情/字幕，支持维度编辑和回退。

## 五、Implementation Tasks

### Phase 1: 数据库基础设施（基础依赖，必须最先完成）

- [ ] 1.1 新建 `media_importer/db.py`
  - 建表 SQL：tasks 表（35 字段 + 3 索引）+ task_subtitles 表（11 字段 + 2 索引）
  - `init_db(db_path)` 函数：打开/创建 SQLite，PRAGMA journal_mode=WAL，执行建表
  - `get_conn()` 返回线程安全的 connection（check_same_thread=False + WAL 支持并发读）
  - 所有数据操作封装为 `_execute(sql, params)` 内部方法
  - **验收**：执行 init_db 后两个表存在，索引存在

- [ ] 1.2 db.py CRUD 方法 — tasks 表
  - `create_task(source_path, source_filename, file_size_mb) → dict`：INSERT + 返回带 task_id 的记录
  - `get_task(task_id) → dict/None`：SELECT * WHERE task_id=?
  - `find_by_source_path(source_path) → dict/None`：源端去重查询
  - `list_tasks(page, page_size, status) → (list, total)`：分页 + 状态筛选 + 倒序
  - `update_task(task_id, **fields)`：动态 UPDATE 指定字段
  - `count_by_status() → dict`：各状态计数
  - **验收**：CRUD 操作可独立测试，返回数据格式正确

- [ ] 1.3 db.py CRUD 方法 — task_subtitles 表
  - `create_subtitles(task_id, subtitle_paths: list) → list`：批量 INSERT，返回插入记录
  - `get_subtitles_by_task(task_id) → list`：按 task_id 查所有字幕
  - `update_subtitle(subtitle_id, **fields)`：更新单条字幕
  - `update_subtitles_by_task(task_id, **fields)`：批量更新某任务所有字幕
  - `count_subtitles_by_task(task_id) → (total, success)`：字幕统计
  - **验收**：字幕 CRUD 正确关联 task_id

### Phase 2: TaskManager 重写 + FileScanner 适配

- [ ] 2.1 重写 `media_importer/task_manager.py`
  - 删除 `Task` dataclass — 改用普通 dict
  - 删除 `_tasks` 字典、`_save_tasks()`、`_load_tasks()`
  - 删除 `_cleanup_success_task()`
  - 保留对外接口签名兼容，内部改为调 db.py：
    - `create_task(video_path, video_file, subtitles, file_size) → dict`
      → db.create_task + db.create_subtitles
    - `get_task(task_id) → dict` → db.get_task
    - `update_task(task) → db.update_task(task_id, **task)`
    - `list_tasks(...)` → db.list_tasks
    - `has_active_tasks()` → db.count_by_status
    - `count_by_status()` → db.count_by_status
  - **验收**：外部调用者（pipeline/api_server）接口不变，功能正常

- [ ] 2.2 task_manager.py 新增去重 + 隔离区方法
  - `check_source_duplicate(source_path) → dict/None`：查历史记录，返回含决策信息的 dict
    ```python
    {
      "exists": True,
      "task_id": "...",
      "old_status": "SUCCESS",
      "old_retry": 0,
      "action": "QUARANTINE",  # QUARANTINE / RETRY / SKIP / CREATE
      "reason": "历史已处理"
    }
    ```
  - `move_to_quarantine(task_id, source_path, subtitle_paths, quarantine_dir)`：
    → shutil.move 视频+字幕到隔离区
    → db.update_task status=NEEDS_REVIEW
    → db.update_subtitles_by_task status=NEEDS_REVIEW
  - **验收**：去重决策矩阵正确（SUCCESS→隔离区, FAILED<3→重试, FAILED≥3→隔离区）

- [ ] 2.3 改造 `media_importer/file_scanner.py`
  - `scan_source_dir()` 返回前对每个 group 调 `task_manager.check_source_duplicate()`
  - QUARANTINE → 调 move_to_quarantine → 从 groups 移除
  - SKIP → 从 groups 移除
  - CREATE → 保留
  - 返回过滤后的 groups + 统计信息（跳过原因）
  - **验收**：源目录扫到历史文件 → 移到隔离区，不创建任务

### Phase 3: Pipeline 核心流程改造

- [ ] 3.1 改造 `scan_and_create_tasks()`
  - 调用 file_scanner 过滤后的 groups
  - 创建任务时同步调 db.create_subtitles
  - 返回实际创建的任务列表 + 跳过统计
  - **验收**：创建任务时字幕子记录正确入库

- [ ] 3.2 步骤级字幕处理
  - copy 步骤：视频拷贝后，逐个字幕 copy → 更新 task_subtitles 单条记录的 status
    - 单个字幕失败不阻塞视频，记录错误到该字幕的 error_message
  - import 步骤：视频移动后，逐个字幕 move → 更新 task_subtitles.import_path + status=SUCCESS
  - **验收**：3 个字幕中 1 个失败，2 个成功入库并正确记录

- [ ] 3.3 process_one 增加分流点（classify 之后）
  ```
  classify 完成后:
    if not manual_review.enabled:
      → 继续 dedup → rename → import → SUCCESS
    else:
      → 停止，status = CONFIRMING，文件在 temp
      → 源文件不删除
      → 记录 import_path（已验证）
  ```
  - **验收**：启用确认时，文件在 temp 目录，任务状态 CONFIRMING

- [ ] 3.4 新增 confirm 流程（从 CONFIRMING 到 SUCCESS）
  - `confirm_task(task_id)`：
    1. 从 db 加载 task + subtitles
    2. 执行 dedup 检查（如匹配到同名 → 根据策略处理）
    3. rename 生成 final_filename
    4. import 从 temp 移到目标目录（视频+字幕）
    5. 清理源目录文件
    6. db.update_task status=SUCCESS
    7. db.update_subtitles_by_task status=SUCCESS
  - **验收**：confirm 后文件正确出现在目标目录

- [ ] 3.5 失败处理适配
  - Exception → FAILED + retry_count+1
  - retry_count >= max_auto_retries → move_to_quarantine + NEEDS_REVIEW
  - **验收**：重试 3 次失败 → 文件进隔离区

### Phase 4: API 层

- [ ] 4.1 改造 `GET /api/tasks`
  - 参数：page(默认1)、page_size(默认20)、status(默认all)
  - 返回：{ tasks: [简要字段], total, page, page_size, total_pages }
  - 简要字段：task_id, source_filename, status, percentage, scrape_title_cn,
    scrape_title_en, scrape_year, subtitle_total, subtitle_success,
    import_path, final_filename, skip_reason, error_message,
    created_at, completed_at
  - **验收**：分页正确，total_pages=向上取整(total/page_size)

- [ ] 4.2 改造 `GET /api/tasks/{id}`
  - 返回 tasks 全字段 + subtitle_list（call db.get_subtitles_by_task）
  - **验收**：弹窗可用完整数据渲染

- [ ] 4.3 新增 API 端点
  - `POST /api/tasks/{id}/confirm`
    → call pipeline.confirm_task → 返回 { import_video_path, final_filename }
  - `POST /api/tasks/{id}/reclassify`
    → Body: { dimensions } → re-classify → db.update_task import_path
    → 返回 { new_import_path }
  - `POST /api/tasks/{id}/rollback`
    → 删除 temp 文件（视频+字幕）→ db.update_task ROLLBACK
    → 返回 { message }
  - `POST /api/tasks/{id}/retry`
    → 适配 NEEDS_REVIEW/FAILED → PENDING（需文件在源目录）
  - `POST /api/tasks/{id}/ignore`
    → NEEDS_REVIEW → SKIPPED（终态）
  - `POST /api/tasks/confirm-all`
    → 批量 confirm all CONFIRMING tasks
  - `GET /api/tasks/stats`
    → 返回各状态计数 { total, pending, processing, success, confirming,
      failed, skipped, needs_review, rollback }
  - `GET /api/tasks/{id}/subtitles`
    → 返回字幕列表 + 汇总统计
  - **验收**：每个端点 200 响应，数据格式正确

- [ ] 4.4 改造 `GET /api/metrics`
  - 改用 SQL COUNT 查询
  - 返回值增加各状态分类计数
  - **验收**：概览面板统计正确

### Phase 5: WebUI 前端

- [ ] 5.1 改造任务面板 HTML（index.html）
  - 表格列头：文件名/刮削结果 | 字幕 | 状态 | 入库路径 | 操作
  - 状态筛选 Tab 条：9 个 Tab（全部/待处理/处理中/成功/确认中/失败/跳过/需介入/已回退）
  - 分页控件 div
  - 3 个弹窗容器（task-detail-modal / subtitle-detail-modal / rollback-confirm-modal）
  - **验收**：HTML 结构正确，弹窗默认隐藏

- [ ] 5.2 任务列表 JS（app.js）
  - `loadTasks(page, status)`：分页请求 + 状态筛选
  - `loadTaskStats()`：加载 Tab 角标数字
  - `renderTable(tasks)`：双行布局表格
    - 第一行：源文件名（灰色小字，超 40 截断 hover 显示）
    - 第二行：刮削标题 (年份) 或 (刮削失败) / (待处理)
  - `renderPagination(total, page, status)`：分页控件
  - `switchTaskTab(status)`：切换 Tab → 重置 page=1 → loadTasks
  - **验收**：列表正确分页，Tab 切换正常

- [ ] 5.3 操作按钮动态渲染
  - 每行根据 status 动态生成不同按钮
  - CONFIRMING: [◎详情] [✓确认] [✎修改分类] [↩回退]
  - FAILED: [◎详情] [↻重试]
  - NEEDS_REVIEW: [◎详情] [↻重试] [⊘忽略]
  - SUCCESS: [◎详情] [📋复制路径]
  - 有字幕: 字幕列显示蓝色可点击 N/M
  - **验收**：每种状态按钮正确显示

- [ ] 5.4 任务详情弹窗
  - `showTaskDetail(taskId)`：GET /api/tasks/{id} → 渲染分区卡片
  - 按状态不同展示不同卡片（基本信息必显）
  - CONFIRMING 状态下维度可编辑（4 个下拉框）
  - 维度下拉选项：media_type(movie/tv)、documentary(true/false)、
    animation(true/false)、restricted_level(0-6/7-12/13-15/17+)
  - [✎重新分类] 按钮 → POST reclassify → 刷新入库信息
  - [↩回退] 按钮 → 打开回退确认弹窗
  - [✓确认入库] 按钮（底部）→ POST confirm → toast → 列表刷新
  - **验收**：弹窗正确展示，维度编辑后 reclassify 成功

- [ ] 5.5 字幕详情弹窗
  - `showSubtitleDetail(taskId)`：GET /api/tasks/{id}/subtitles
  - 表格：序号 | 源文件名 | 语言 | 状态 | 入库后文件名 | 复制路径
  - 底部汇总：N/M 成功，X/Y 失败
  - **验收**：字幕列表正确，复制路径可用

- [ ] 5.6 回退确认弹窗
  - 列出 temp 目录中待删除的视频+字幕文件清单
  - 提示"源文件未受影响"
  - 确定 → POST /api/tasks/{id}/rollback → toast → 列表刷新
  - **验收**：回退后 temp 文件清理，列表状态变为已回退

- [ ] 5.7 分页控件交互
  - 当前页=1 时"上一页"置灰
  - 当前页=末页时"下一页"置灰
  - 跳转输入框 + Go 按钮
  - 切换 Tab 重置为第 1 页
  - **验收**：分页交互正常

- [ ] 5.8 CSS 样式（styles.css）
  - `.modal-overlay` / `.modal-dialog` 弹窗系统
  - `.task-row` 双行布局
  - `.status-tab-bar` / `.status-tab` 状态筛选（active 色对应状态色）
  - `.status-badge` 8 种颜色角标
  - `.detail-card` / `.detail-grid` 详情卡片
  - `.dim-select` 维度下拉（只读灰色 / 可编辑蓝色）
  - `.pagination-controls` 分页
  - `.confirm-btn`(绿色) / `.reclassify-btn`(蓝色) / `.rollback-btn`(橙色)
  - **验收**：视觉风格与现有设计一致

### Phase 6: 配置 + 部署同步

- [ ] 6.1 config_loader.py 新增配置项
  - `source_dedup.enabled`（默认 true）
  - `source_dedup.quarantine_dir`（默认 "/vol1/影视/_待处理/"）
  - `source_dedup.max_auto_retries`（默认 3）
  - `manual_review.enabled`（默认 false）— 已有配置项，确认字段名一致性
  - **验收**：配置加载正确，validate 通过

- [ ] 6.2 WebUI 配置界面
  - 隔离区路径字段在"入库设置"子页签（和 source_dir/temp_dir 同组）
  - 路径权限测试按钮
  - **验收**：配置界面可修改隔离区路径

- [ ] 6.3 deploy/ 目录全量同步
  - 所有 media_importer/ 下改动同步到 deploy/nas-media-importer/app/server/media_importer/
  - 新增 config.yaml.example 中的新配置项同步
  - **验收**：deploy 目录与源目录一致

## 六、Decision Rationale

### 为什么 SQLite 而不是继续 JSON
- 去重需要高效查询（JSON 需全量遍历 O(n)）
- 分页需要 SQL OFFSET/LIMIT
- 子表关联需要外键

### 为什么 manual_review 停在 classify
- 文件在 temp 不动 → 修改分类只需重算路径不需移动 → 回退只需删 temp
- 如果 import 到目标目录再加 .temp → 修改分类要跨目录移动 → 回退要恢复文件名搬回源目录
- 停在 classify 是**最少文件移动**的方案

### 为什么不做旧数据迁移
- 旧 tasks.json 是当时运行快照，结构差异大
- 新 SQLite 从零开始，第一轮扫描自然创建新记录
- 迁移脚本开发+测试有额外成本，收益有限

## 七、Constraints and Boundaries

1. Python 3 标准库 sqlite3，不引入第三方 ORM
2. SQLite 文件路径：`{project_root}/data/tasks.db`（与旧 tasks.json 同级）
3. API 响应格式保持 `{ code, message, data }`
4. 所有文件操作必须在 `allowed_base_dirs` 白名单内
5. 字幕处理：单个失败不阻塞视频流程
6. 前端不引入第三方 UI 库（纯 CSS + Vanilla JS）

## 八、Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| Python sqlite3 在 fnOS 可用 | Verified | Python 3 标准库自带 |
| WAL 模式支持并发读写 | Verified | SQLite 官方文档，write 串行但 read 并发 |
| Pipeline 单线程执行 | Verified | 当前代码 process_one 串行 |
| 表数据量在 SQLite 能力范围内 | Verified | NAS 场景日增 < 100 条，SQLite 轻松百万级 |

## 九、Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|-----------|
| task_manager 接口签名变动导致 api_server/pipeline 调用失败 | 高 | 保留核心方法签名不变，仅内部实现切换 |
| SQLite 并发写入冲突 | 中 | WAL 模式 + 合理超时重试；Pipeline 本身就是单线程 |
| CONFIRMING 状态任务积压过多 | 低 | 提供 confirm-all 批量接口；Hermes 可定时提醒 |
| 隔离区文件持续增长占空间 | 低 | 用户手动清理；后续加自动清理策略 |

## 十、Acceptance Criteria

1. 启动后 SQLite 自动建表，tasks 表已存在且包含所有 35 个字段
2. 源目录扫到历史文件 → 文件进入隔离区，不创建新任务
3. 启用 manual_review 后，文件在 classify 后停在 CONFIRMING 状态，文件在 temp 目录
4. WebUI 任务列表：分页展示 20 条/页，状态筛选 Tab 9 个，角标数字正确
5. 详情弹窗：所有字段正确展示，维度下拉可编辑
6. 确认入库：文件从 temp 正确移动到目标目录，源文件清理
7. 回退：temp 文件删除，状态变为 ROLLBACK
8. 字幕子记录：独立追踪，单个失败不阻塞视频
9. 全部新 API 端点返回 200 且数据格式正确
10. 所有改动已同步到 deploy/ 目录

## 十一、Phased Implementation

| Phase | 内容 | 依赖 | 可并行 |
|-------|------|------|--------|
| Phase 1 | db.py | 无 | — |
| Phase 2 | task_manager + file_scanner | Phase 1 | — |
| Phase 3 | pipeline | Phase 2 | — |
| Phase 4 | API | Phase 2+3 | Phase 5 可并行 |
| Phase 5 | WebUI | Phase 4 | Phase 4 完成后启动 |
| Phase 6 | 配置 + 部署 | Phase 5 | Phase 5 完成后 |

**建议开发顺序**：Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

Phase 4 和 Phase 5 的 HTML/CSS 部分可以部分并行（HTML 结构设计不依赖 API 完成）。

## 十二、References

- Brainstorm: [2026-05-22-task-sqlite-redesign-brainstorm.md](file:///Users/wangwei/Documents/code/nas_media_manage/docs/brainstorms/2026-05-22-task-sqlite-redesign-brainstorm.md)
- 现有 TaskManager: [task_manager.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/task_manager.py)
- 现有 Pipeline: [pipeline.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/pipeline.py)
- 现有 API: [api_server.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/api_server.py)
- 现有 FileScanner: [file_scanner.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/file_scanner.py)
- 现有 WebUI: [app.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/app.js) / [index.html](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/index.html) / [styles.css](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/styles.css)
