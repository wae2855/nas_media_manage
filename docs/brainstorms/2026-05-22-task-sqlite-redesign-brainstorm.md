---
title: "任务系统 SQLite 重构"
type: brainstorm
date: 2026-05-22
participants: [用户, AI助手]
related: []
---

# 任务系统 SQLite 重构 v2

## Problem Statement

当前任务管理系统采用"内存字典 + JSON 文件"的混合存储方式，存在以下核心问题：

1. **不可追溯** — 成功任务可被自动删除（`auto_delete_success`），无法查询历史处理记录
2. **无法去重** — 没有历史记录支撑，同一文件可能被反复处理
3. **过程黑盒** — 任务只有最终状态，中间环节（刮削/查重/入库/确认）没有独立字段记录
4. **字幕无身份** — 字幕只是视频 Task 的一个 `subtitle_files` 列表字段，无法独立追踪状态
5. **无分页** — 前端一次加载 50 条，数据量大时性能差
6. **无人工审核** — 刮削结果直接入库，无法拦截错误分类
7. **刮削失败反复浪费** — 源目录里刮削不到信息的视频一直存在，每次轮询都重试，浪费 AI Token

## Context

### 现有架构

- **TaskManager**：内存字典 `_tasks` + JSON 文件持久化（`data/tasks.json`）
- **Task dataclass**：22 个字段，状态机 PENDING→PROCESSING→SUCCESS/FAILED/SKIPPED
- **Pipeline**：10 步串行处理（scan→copy→scrape→validate→classify→dedup→rename→import→notify→record）
- **字幕处理**：字幕作为视频的附属，在 copy/import 阶段跟随视频处理，无独立状态
- **配置存储**：YAML 文件 + ruamel.yaml 保留格式，WebUI 已有完整编辑界面
- **API**：`GET /api/tasks` 支持 status/limit/offset 参数，但底层是内存全量遍历

### 现有去重机制（两套独立逻辑）

1. **源端扫描去重**：无。每次扫描源目录，发现视频就创建新任务，不检查历史。
2. **入库端查重**（`dedup_checker.py`）：在目标入库目录做**模糊匹配**——按标题+年份+季集号匹配已入库文件。这是为了防止同一部电影的不同版本（如1080p→4K升级）重复入库。支持 skip/rename/replace/quality 四种策略。

---

## Chosen Approach

**SQLite 存储任务 + YAML 保留配置**：仅将任务系统迁移到 SQLite，配置系统保持 YAML 不变。

## Why This Approach

| 维度 | 方案A: 全量 SQLite（任务+配置） | 方案B: SQLite 任务 + YAML 配置 ✅ |
|------|------|------|
| 去重能力 | ✅ SQL 查询 | ✅ SQL 查询 |
| 分页效率 | ✅ OFFSET/LIMIT | ✅ OFFSET/LIMIT |
| 子表支持 | ✅ 外键关联 | ✅ 外键关联 |
| 配置可读性 | ❌ 需工具查看 | ✅ 人工可编辑 YAML |
| 改动范围 | 🔴 极大（配置读写全改） | 🟢 中等（仅任务层） |
| 配置迁移风险 | 🔴 高（WebUI/热重载/掩码全改） | 🟢 无 |

选择方案B：配置系统已有完善的 WebUI 编辑、热重载、敏感字段掩码、ruamel.yaml 格式保留等功能，迁移到 SQLite 收益不大但风险极高。

---

## 一、代码改动清单（逐文件详细说明）

### 新文件

#### `media_importer/db.py` — SQLite 数据库模块（全新）

```python
# 核心职责：
# - init_db(db_path): 建表 + 建索引 + 返回 connection
# - TaskCRUD 类: 封装所有 tasks/task_subtitles 表的 CRUD + 分页查询
# - migrate_from_json(json_path, db): 数据迁移（旧 tasks.json → SQLite）
```

提供的方法：
| 方法 | 说明 |
|------|------|
| `init_db(path)` | 创建/打开 SQLite，执行建表 SQL |
| `create_task(video_path, video_file, ...)` | INSERT INTO tasks |
| `create_subtitles(task_id, sub_paths)` | 批量 INSERT INTO task_subtitles |
| `find_by_source_path(path)` | SELECT WHERE source_path=? 去重查询 |
| `find_by_source_filename(name)` | SELECT WHERE source_filename=? 同名查询 |
| `get_task(task_id)` | 单条查询 |
| `update_task(task_id, **fields)` | 更新指定字段 |
| `update_subtitle(id, **fields)` | 更新字幕字段 |
| `list_tasks(page, page_size, status)` | 分页+状态筛选 |
| `count_tasks(status)` | 计数 |
| `find_failed_too_many(max_retries)` | 找出反复失败的"卡住"文件 |
| `get_subtitles_by_task(task_id)` | 查某视频的所有字幕 |

### 修改文件

#### 1. `media_importer/task_manager.py` — 全面重写

**改动性质**：删掉 dataclass + 内存字典 + JSON 文件，改为纯操作 db.py 的薄封装层。

**保留的接口**（外部调用者不变）：
- `create_task(video_path, video_file, subtitles, file_size)` → 改为调用 db.create_task + db.create_subtitles
- `get_task(task_id)` → db.get_task
- `update_task(task)` → db.update_task（抛弃 Task 对象，改传字段 dict）
- `list_tasks(status, limit, offset)` → db.list_tasks + COUNT
- `has_active_tasks()` → db.count_tasks
- `count_by_status()` → db.count 分组

**删除的接口**：
- `_save_tasks()` / `_load_tasks()` — 不再需要 JSON 文件
- `_tasks` 字典 — 不再需要内存存储
- `_cleanup_success_task()` — 不再自动删除成功任务
- `Task` dataclass — 改为普通 dict 或轻量 namedtuple

**新增的接口**：
- `check_source_duplicate(source_path)` → 返回历史记录或 None
- `update_skip_for_duplicate(task_id, reason)` → 更新 last_seen_at + skip_reason

#### 2. `media_importer/file_scanner.py` — 新增源端查重

**改动性质**：最小改动，在 `scan_source_dir` 末尾增加查重步骤。

```
现有逻辑：
  os.walk → 发现视频 → 找字幕 → 返回 groups

新增逻辑（在返回前插入）：
  for each group:
    source_path = group['video']   # 完整路径含文件名
    history = task_manager.check_source_duplicate(source_path)
    if history:
      → 根据历史状态决定：跳过/标记/重新创建
      → 更新 last_seen_at
    else:
      → 正常返回 group（后续创建任务）
```

**`check_source_duplicate(source_path)` 的去重决策矩阵**（详见第三节）：

| 历史状态 | 本次行为 |
|----------|---------|
| SUCCESS / CONFIRMED | **移入隔离区** + 标记 NEEDS_REVIEW，原因="历史已处理" |
| FAILED + retry < N | 更新状态为 PENDING，重新处理 |
| FAILED + retry >= N | **移入隔离区** + 标记 NEEDS_REVIEW，原因="刮削多次失败" |
| SKIPPED | 同 FAILED 逻辑 |
| PROCESSING | 跳过（防止重复处理） |
| CONFIRMING | 跳过（等待用户确认或修改分类） |
| 不存在 | 正常创建新任务 |

**移入隔离区操作**（含字幕）：
```
1. 在隔离区创建同名文件（shutil.move）
2. 同样移动关联的字幕文件
3. 更新 task.video_path 和 task.subtitle_files 指向隔离区路径
4. 清理源目录空文件夹（如有）
5. 任务标记 NEEDS_REVIEW
```

#### 3. `media_importer/pipeline.py` — 核心流程改造

**3a. scan_and_create_tasks 改动**

```
现有：扫描 → 全部创建 task → 返回
改为：
  扫描 → 对每个视频做源端去重（调 task_manager.check_source_duplicate）
       → 如果历史已处理或失败超限：文件移入隔离区 + 标记 NEEDS_REVIEW
       → 如果正在处理或待确认：跳过，不创建任务
       → 如果正常：创建 task + 创建字幕子记录
  返回实际创建的任务列表
```

**3b. process_one 流程图**

```
process_one(task) 调用前:
  ┌─ 先检查 task 是否有未处理的字幕子记录 ─┐
  │  SELECT * FROM task_subtitles          │
  │  WHERE task_id=? AND status='PENDING'  │
  │  如果有 → 补充到 task.subtitle_files    │
  └────────────────────────────────────────┘

process_one(task) 主流程:
  PENDING → PROCESSING
  │
  ├─[step: copy] 复制视频+所有字幕到 temp
  │   → 字幕 copy 成功/失败各自记录到 task_subtitles
  │
  ├─[step: scrape] AI 刮削视频元数据
  │   → 将完整结果写入 task.scrape_* 字段
  │   → 字幕直接复用视频的刮削结果（标题等信息）
  │
  ├─[step: validate] 验证刮削结果
  │   → 刮削不完整 → FAILED，不继续
  │
  ├─[step: classify] 维度匹配 → 确定入库路径
  │   → 写入 classify_result 和 import_path
  │
  └─[分流点: manual_review.enabled?]
     │
     ├─ NO（不启用确认）:
     │   ├─[step: dedup] 入库目录同名检测
     │   ├─[step: rename] 生成目标文件名
     │   ├─[step: import] 移动文件从 temp → 目标目录
     │   │   → 视频 + 字幕一起移动
     │   │   → 清理源目录文件
     │   ├─[step: notify]
     │   └─[step: record] → SUCCESS
     │
     └─ YES（启用确认）:
         → 停止处理，文件留在 temp
         → task.status = CONFIRMING, confirm_status = PENDING
         → task.import_path 已确定（classify 产出）
         → 源文件仍在源目录（未删除）
         → 记录当前步骤 = 5

  CONFIRMING 文件的三个操作入口（WebUI/API）:

  ① 确认入库（✓）:
     → 继续 pipeline: dedup → rename → import（从 temp 到目标目录）
     → 移动视频 + 字幕到目标目录
     → 清理源目录文件
     → task.status = SUCCESS, confirm_status = CONFIRMED

  ② 修改分类（✎）:
     → 用户修改维度值 → 重新 classify → 更新 import_path
     → 文件不动（仍在 temp），仅更新分类结果
     → 仍 CONFIRMING，用户可再确认

  ③ 回退（↩）:
     → 删除 temp 目录中的视频 + 字幕文件
     → task.status = ROLLBACK
     → 源文件未受影响（仍在 source_dir）
     → 下一轮扫描自动发现 → 重新创建任务

异常处理:
  └─ PipelineSkipError → SKIPPED + 清理 temp
  └─ Exception → FAILED + retry_count+1
     → 如果 retry_count >= max_auto_retries:
       → 文件移入隔离区
       → 标记 NEEDS_REVIEW
```

**3c. 字幕处理详细流程**

每个字幕的处理伴随视频各步骤：

```
copy 步骤:
  for each subtitle_path in task.subtitle_files:
    try:
      dest = copier.copy_subtitle(subtitle_path, temp_dir)
      更新 task_subtitles 记录: status=COPIED, temp_path=dest
    except:
      更新 task_subtitles 记录: status=FAILED, error=...
      # 字幕失败不阻塞视频处理，继续

import 步骤:
  for each subtitle record in task_subtitles:
    try:
      lang = detect_lang(subtitle.source_filename)
      dest_name = f"{final_video_name}.{lang}{ext}"
      dest_path = f"{import_path}/{dest_name}"
      shutil.move(temp_path, dest_path)
      更新 task_subtitles: import_path=dest_path, status=SUCCESS
    except:
      更新 task_subtitles: status=FAILED, error=...

record 步骤:
  所有字幕 status 同步为视频的最终状态:
  - 视频 SUCCESS → 字幕 SUCCESS
  - 视频 CONFIRMING → 字幕 CONFIRMING
  - 视频 FAILED → 字幕 FAILED
```

#### 4. `media_importer/api_server.py` — API 层适配

**改动点**：

| 接口 | 改动 |
|------|------|
| `GET /api/tasks` | 分页+状态筛选；列表返回简要字段 + 字幕数量统计 |
| `GET /api/tasks/{id}` | 任务全字段 + 关联字幕子记录清单（供详情弹窗） |
| `GET /api/tasks/{id}/subtitles` | **新增**：任务的完整字幕列表（供字幕弹窗） |
| `POST /api/tasks/{id}/confirm` | **新增**：确认入库（执行 dedup→rename→import） |
| `POST /api/tasks/{id}/reclassify` | **新增**：修改维度后重新分类入库（含字幕跟随） |
| `POST /api/tasks/{id}/rollback` | **新增**：回退到源目录（恢复原始文件名，含字幕） |
| `POST /api/tasks/{id}/retry` | 适配新状态机，支持 NEEDS_REVIEW → PENDING |
| `POST /api/tasks/{id}/ignore` | **新增**：忽略 NEEDS_REVIEW 任务，标记 SKIPPED |
| `POST /api/tasks/confirm-all` | **新增**：批量确认所有待确认任务 |
| `GET /api/tasks/stats` | **新增**：各状态计数（供前端 Tab 角标） |
| `GET /api/metrics` | 统计改用 SQL COUNT 查询 |

**人工确认 API**：
```
POST /api/tasks/{task_id}/confirm
  → 执行: dedup检查 → rename生成文件名 → import从temp移到目标目录
  → 移动视频 + 所有字幕到目标目录
  → 清理源目录文件
  → 更新 tasks.status=SUCCESS, confirm_status=CONFIRMED
  → 更新所有 task_subtitles.status=SUCCESS
  → 返回 { import_video_path, final_filename, subtitle_paths }
```

**修改分类 API**：
```
POST /api/tasks/{task_id}/reclassify
  Body: { dimensions: { restricted_level: "17+", ... } }
  → 用新维度重新 classify（匹配路径规则）
  → 更新 task.scrape_dimensions、import_path
  → 文件仍在 temp 目录，不动
  → 状态保留 CONFIRMING（用户可再确认）
  → 返回 { new_import_path }
```

**回退 API**（新增）：
```
POST /api/tasks/{task_id}/rollback
  → 删除 temp 目录中的视频 + 字幕文件
  → 清理 temp 空目录
  → 更新 task: status=ROLLBACK, confirm_status=NONE
  → 更新所有 task_subtitles: status=ROLLBACK
  → 源文件不受影响（仍在 source_dir）
  → 返回 { message: "已回退" }
```

#### 5. `media_importer/webui/app.js` — 前端脚本

新增/修改函数：

| 函数 | 说明 |
|------|------|
| `loadTasks(page, status)` | 分页请求 + 状态筛选，调用 `GET /api/tasks` |
| `loadTaskStats()` | 加载各状态计数角标，调用 `GET /api/tasks/stats` |
| `renderTable(tasks)` | 渲染表格行（双行布局：源文件名 + 刮削标题） |
| `renderPagination(total, page)` | 分页控件 HTML |
| `showTaskDetail(taskId)` | 打开详情弹窗，调用 `GET /api/tasks/{id}` |
| `showSubtitleDetail(taskId)` | 打开字幕弹窗，调用 `GET /api/tasks/{id}/subtitles` |
| `showRollbackConfirm(taskId)` | 打开回退确认弹窗 |
| `closeModal()` | 关闭弹窗 |
| `confirmTask(taskId)` | 确认入库 → `POST /api/tasks/{id}/confirm` |
| `reclassifyTask(taskId)` | 提交修改后的维度 → `POST /api/tasks/{id}/reclassify` |
| `rollbackTask(taskId)` | 回退 → `POST /api/tasks/{id}/rollback`（删除 temp 文件） |
| `retryTask(taskId)` | 重试失败任务 → `POST /api/tasks/{id}/retry` |
| `ignoreTask(taskId)` | 忽略需介入任务 → `POST /api/tasks/{id}/ignore` |
| `confirmAllTasks()` | 批量确认 → `POST /api/tasks/confirm-all` |
| `copyPath(path)` | 复制路径到剪贴板 + toast 提示 |
| `switchTaskTab(status)` | 切换状态筛选 Tab |

**操作按钮按状态动态渲染**：

| 状态 | 列表按钮 |
|------|---------|
| 所有 | 详情 ◎ |
| 有字幕记录 | 字幕 ▶ |
| CONFIRMING | 确认 ✓ / 修改分类（弹窗内 ✎） / 回退 ↩ |
| FAILED | 重试 ↻ |
| NEEDS_REVIEW | 重试 ↻ / 忽略 ⊘ |
| SUCCESS | 复制路径 📋 |

#### 6. `media_importer/webui/index.html` — 前端 HTML

新增/修改元素：
- 任务面板标题动态化（"共 N 条"）
- 表格列头精简为 5 列：文件名/刮削结果\|字幕\|状态\|入库路径\|操作
- 表格底部增加 `<div id="pagination-controls">` 分页控件
- 新增状态筛选 Tab 条 `<div id="task-status-tabs">`（全部/待处理/处理中/成功/确认中/失败/跳过/需介入/已回退）
- 新增"全部确认"按钮（确认中 Tab 可见）
- 页面底部新增 3 个弹窗容器（默认 `display:none`）：
  - `<div id="task-detail-modal" class="modal-overlay">` — 任务详情弹窗
  - `<div id="subtitle-detail-modal" class="modal-overlay">` — 字幕详情弹窗
  - `<div id="rollback-confirm-modal" class="modal-overlay">` — 回退确认弹窗

#### 7. `media_importer/webui/styles.css` — 样式

新增样式要点：
- `.modal-overlay` / `.modal-dialog` / `.modal-header` / `.modal-body` 弹窗系统
- `.task-row` 双行布局（`.task-source-name` + `.task-scrape-title`）
- `.status-tab-bar` / `.status-tab` 状态筛选 Tab（带彩色角标）
- `.status-badge` 状态角标（8 种颜色）
- `.detail-card` / `.detail-grid` 详情卡片分区
- `.dim-select` 维度下拉框（只读/可编辑两种状态）
- `.pagination-controls` 分页控件
- `.rollback-confirm` 回退确认弹窗样式
- `.confirm-btn`(绿色) / `.reclassify-btn`(蓝色) / `.rollback-btn`(橙色) 操作按钮

#### 8. `media_importer/classifier.py` — 无改动

（路径匹配逻辑保持不变）

#### 9. `media_importer/dedup_checker.py` — 无改动

（入库端模糊查重逻辑保持不变，仍然使用）

#### 10. `media_importer/config_loader.py` — 少量改动

**新增配置项**（加入 config.yaml.example）：
```yaml
source_dedup:
  enabled: true
  quarantine_dir: "/vol1/影视/_待处理/"   # 隔离区路径，WebUI 配置界面可修改
  max_auto_retries: 3

manual_review:
  enabled: false                          # 启用后 classify 后停止，等待确认才入库
```

**WebUI 配置界面**：
- `quarantine_dir` 字段放在配置面板中，和 source_dir 同属"入库设置"子页签
- 提供路径权限测试按钮（同 source_dir/temp_dir）

#### 11. `deploy/` 目录 — 同步所有改动

全部修改文件同步到 `deploy/nas-media-importer/app/server/media_importer/`。

#### 12. 数据迁移脚本（可选，一次性使用）

`migrate_to_sqlite.py`：读取 `data/tasks.json`，转换为 SQLite 记录。
运行时只执行一次，或通过 WebUI 触发。

---

## 二、字幕处理流程详解（重点）

字幕生命周期经历了**根本性改变**——从"视频的一个字段"变成"独立的子记录"。

### 旧流程（当前）vs 新流程（目标）

```
旧流程:
  Task { video_path, subtitle_files: ["sub1.srt", "sub2.srt"], ... }
  │
  └─ pipeline 处理整个 Task
     ├─ copy: 复制视频 + 所有字幕到 temp（一起操作，一起成功/失败）
     ├─ scrape: 只刮削视频
     └─ import: 移动视频 + 字幕到入库目录
                → 字幕文件名: {视频名}.{lang}.{ext}
                → 字幕和视频一起操作，无独立状态

  问题：
  1. 字幕 copy 失败会影响视频吗？目前是一起操作
  2. 某个字幕 copy 失败，无法知道是哪个
  3. 字幕入库路径没有记录

新流程:
  tasks 表:
    task_id="abc123", source_path="/src/BB.S01E01.mkv", status="PROCESSING"

  task_subtitles 表:
    id=1, task_id="abc123", source_path="/src/BB.S01E01.zh.srt", status="PENDING"
    id=2, task_id="abc123", source_path="/src/BB.S01E01.en.srt", status="PENDING"
    id=3, task_id="abc123", source_path="/src/BB.S01E01.ja.srt", status="PENDING"

  └─ pipeline process_one(task):
     ├─ [scan时] 创建 task + 3条 task_subtitles
     ├─ [copy] 复制视频到 temp
     │         → 字幕逐个复制:
     │           sub1 → 成功: status=COPIED, temp_path="/tmp/BB.S01E01.zh.srt"
     │           sub2 → 成功: status=COPIED, temp_path="/tmp/BB.S01E01.en.srt"
     │           sub3 → 失败: status=FAILED, error="文件不存在"
     │         （字幕失败不阻塞视频，继续处理）
     ├─ [scrape] 刮削视频 → 得到 title_cn="绝命毒师"、S01E01
     │         字幕不需要额外刮削，直接使用视频的标题
     ├─ [classify] → import_path="/vol1/影视/TV-R/绝命毒师 (2008)/Season 1/"
     ├─ [手动确认或自动分流]
     │   ├─ 自动: dedup → rename → import → SUCCESS
     │   └─ 手动: 停止，CONFIRMING，等待用户确认后执行 import

  WebUI 展示（弹窗方式）:
    点击字幕列 "3" → 弹出字幕详情窗口:
    ┌─────────────────────────────────────────┐
    │ 字幕详情 - BB.S01E01.mkv         [✕]    │
    │ # │源文件名     │语言│状态│入库后文件名   │
    │ 1 │BB...zh.srt │zh  │成功│绝命毒师..zh   │
    │ 2 │BB...en.srt │en  │成功│绝命毒师..en   │
    │ 3 │BB...ja.srt │ja  │失败│(文件不存在)   │
    └─────────────────────────────────────────┘
```

---

## 三、去重策略深入探讨

### 两种去重，分工不同

| 维度 | 源端去重（新增） | 入库端去重（现有，保留） |
|------|-----------------|------------------------|
| 查询依据 | `source_path`（完整路径含文件名） | 标题+年份+季集（模糊匹配） |
| 查询范围 | SQLite 历史记录 | 目标入库目录文件系统 |
| 目的 | 防止重复处理、标记卡住文件 | 防止同名影视重复入库 |
| 触发时机 | 扫描阶段 | import 步骤之前 |
| 例子 | 源目录里的 av.mp4 上次刮削失败，本次跳过 | 已有 1080p 版本，新来 4K 版本，quality 策略决定替换 |

**两个去重互补，互不替代。**

### 源端去重 + 隔离区：统一处理

**核心思路**：源端去重发现需要跳过的文件，**一律移到隔离区**。用户改完名重新放回源目录，下一轮扫描自动发现并重新处理。

#### 隔离区配置

```yaml
source_dedup:
  enabled: true
  quarantine_dir: "/vol1/影视/_待处理/"   # 统一隔离区
  max_auto_retries: 3
```

#### 场景A：刮削失败卡住 → 入隔离区

```
源目录 /downloads/av.mp4 重试3次刮削均失败
  → retry_count >= max_auto_retries
  → 将 av.mp4 从 /downloads/ 移到 /vol1/影视/_待处理/av.mp4
  → 任务标记 NEEDS_REVIEW，更新 video_path 为隔离区路径
  → 原因: "刮削信息不足，已移入隔离区等待人工处理"

用户操作：在文件管理器中将 av.mp4 改名为正确的视频名，放回 /downloads/
系统感知：下一轮扫描发现新文件 → source_path 不同 → 新任务，正常处理
```

#### 场景B：历史已处理 → 入隔离区（视频+字幕一起移动）

```
源目录 /downloads/BB.S01E01.mkv + BB.S01E01.zh.srt + BB.S01E01.en.srt
  → 查 source_path → 历史记录 status=SUCCESS（成功入库于半年前）
  → 将视频+所有关联字幕从源目录一起移到 /vol1/影视/_待处理/
  → 更新任务 last_seen_at，标记 NEEDS_REVIEW
  → 原因: "该文件历史上已成功入库（2025-12-01），已移入隔离区"

用户操作：
  如需重新导入 → 把视频+字幕一起放回 /downloads/
  如不需要 → 删除隔离区里的文件即可
```

#### 隔离区总结

| 入隔离区条件 | 连带移动 | 用户怎么恢复 |
|-------------|---------|-------------|
| 刮削失败 ≥N 次 | 视频+源目录同名字幕 | 改名 → 放回源目录 |
| 历史已成功入库 | 视频+源目录同名字幕 | 放回源目录（如需重新导入） |
| SKIPPED（之前跳过） | 视频+源目录同名字幕 | 改名或放回源目录 |

**关键规则**：
- 隔离区统一为 `/vol1/影视/_待处理/`（可配置）
- **所有操作始终视频+字幕绑定**：移入隔离区、回退源目录、重新分类入库
- 用户只需要**文件管理器**操作，不需要回 WebUI
- 放回源目录后下一轮扫描自动发现（source_path 变了 → 视为新文件）

### source_path 定义

**`source_path` = 源文件的完整绝对路径，包含文件名。**

例如：`/vol3/downloads/Movie.2026.1080p.mkv`（这是完整路径，不是目录）

这样两个不同位置但同名的文件不会冲突：
- `/vol3/downloads/Movie.2026.mkv` → 一条记录
- `/vol3/usb_backup/Movie.2026.mkv` → 另一条记录

### source_path 的局限性及应对

你提到的问题："如果用户重命名源文件，路径变了但内容相同，会被当作新文件"。

**这是刻意为之，不是 bug。原因：**

1. **精确匹配是最可靠的** — 基于路径判断"是不是同一个文件"，准确率 100%
2. **重命名是用户主动行为** — 用户改了文件名，系统应该认为这是新文件
3. **内容去重成本高** — 需要计算文件哈希（大文件非常慢），且同名不同内容也可能发生
4. **入库端已经有模糊匹配** — 即使源端去重漏了，入库端的 `dedup_checker` 还会在目标目录做模糊匹配

> **结论**：`source_path` 精确匹配 + 入库端模糊匹配，双层去重覆盖了所有场景。

---

## 四、数据库表结构（终版）

### tasks 表（视频任务主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| task_id | TEXT UNIQUE NOT NULL | 业务ID（uuid4[:12]），兼容现有 |
| source_path | TEXT NOT NULL | 源文件完整路径（含文件名），去重依据 |
| source_filename | TEXT NOT NULL | 源文件名（仅 basename） |
| file_size_mb | REAL DEFAULT 0 | 文件大小 MB |
| status | TEXT DEFAULT 'PENDING' | PENDING/PROCESSING/SUCCESS/FAILED/SKIPPED/CONFIRMING/NEEDS_REVIEW/ROLLBACK |
| retry_count | INTEGER DEFAULT 0 | 重试次数 |
| created_at | TEXT | 创建时间 ISO |
| started_at | TEXT | 开始处理时间 |
| completed_at | TEXT | 完成时间 |
| last_seen_at | TEXT | 最近一次扫描到的时间 |
| current_step | INTEGER DEFAULT 0 | 当前步骤 |
| total_steps | INTEGER DEFAULT 10 | 总步骤数 |
| step_name | TEXT DEFAULT '' | 当前步骤名称 |
| percentage | INTEGER DEFAULT 0 | 进度百分比 |
| bytes_copied | INTEGER DEFAULT 0 | 已复制字节数 |
| total_bytes | INTEGER DEFAULT 0 | 总字节数 |
| scrape_result | TEXT DEFAULT '{}' | 刮削完整结果 JSON |
| scrape_title_cn | TEXT | 中文标题 |
| scrape_title_en | TEXT | 英文标题 |
| scrape_year | TEXT | 年份 |
| scrape_media_type | TEXT | movie/tv |
| scrape_season | INTEGER | 季号 |
| scrape_episode | INTEGER | 集号 |
| scrape_dimensions | TEXT DEFAULT '{}' | 维度 JSON |
| scrape_confidence | REAL DEFAULT 0 | 置信度 |
| classify_result | TEXT DEFAULT '' | 分类匹配描述 |
| import_path | TEXT DEFAULT '' | 入库目标目录 |
| final_filename | TEXT DEFAULT '' | 最终文件名 |
| dedup_result | TEXT DEFAULT '{}' | 查重结果 JSON |
| dedup_existing_file | TEXT DEFAULT '' | 已有同名文件路径 |
| import_video_path | TEXT DEFAULT '' | 入库后视频完整路径 |
| import_success | INTEGER DEFAULT 0 | 入库成功 0/1 |
| confirm_status | TEXT DEFAULT 'NONE' | NONE/PENDING/CONFIRMED |
| confirmed_at | TEXT | 确认时间 |
| skip_reason | TEXT DEFAULT '' | 跳过原因 |
| error_code | INTEGER DEFAULT 0 | 错误码 |
| error_message | TEXT DEFAULT '' | 错误信息 |

索引：
- `idx_tasks_source_path` ON (source_path)
- `idx_tasks_status` ON (status)
- `idx_tasks_created_at` ON (created_at DESC)

### task_subtitles 表（字幕子表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| task_id | TEXT NOT NULL | 关联 tasks.task_id |
| source_path | TEXT NOT NULL | 字幕源文件完整路径 |
| source_filename | TEXT NOT NULL | 字幕文件名 |
| lang | TEXT DEFAULT '' | 检测语言 zh/en/ja/ko |
| status | TEXT DEFAULT 'PENDING' | PENDING/COPIED/SUCCESS/FAILED/CONFIRMING/NEEDS_REVIEW/ROLLBACK |
| import_path | TEXT DEFAULT '' | 入库后完整路径 |
| confirm_status | TEXT DEFAULT 'NONE' | NONE/PENDING/CONFIRMED |
| error_message | TEXT DEFAULT '' | 错误信息 |
| created_at | TEXT | 创建时间 |
| completed_at | TEXT | 完成时间 |

索引：
- `idx_subtitles_task_id` ON (task_id)
- `idx_subtitles_source_path` ON (source_path)

### 状态机（完整版）

```
          ┌─────────────┐
          │  扫描发现文件  │
          └──────┬──────┘
                 │
          ┌──────▼──────┐
          │  源端去重检查  │──── 历史SUCCESS ──→ 移入隔离区 + NEEDS_REVIEW
          │  (查SQLite)  │──── FAILED≥3次 ──→ 移入隔离区 + NEEDS_REVIEW
          └──────┬──────┘──── PROCESSING ───→ 跳过（正在处理）
                 │           ──── CONFIRMING ──→ 跳过（待确认）
                 │           ──── NEEDS_REVIEW → 跳过（已在隔离区）
          ┌──────▼──────┐
          │   PENDING    │←──── 人工重试（文件已放回源目录）
          └──────┬──────┘
                 │
          ┌──────▼──────┐
          │  PROCESSING  │
          └──────┬──────┘
                 │
        ┌────────┼────────┐
        │        │        │
   ┌────▼──┐ ┌──▼───┐ ┌──▼──────┐
   │SUCCESS│ │FAILED│ │SKIPPED  │    manual_review
   │(终态) │ │      │ │(终态)   │    未启用
   └───────┘ └──┬───┘ └─────────┘
                │
           retry<max?
           ┌────┴────┐
           │ YES     │ NO
      ┌────▼───┐ ┌──▼──────────────┐
      │PENDING │ │移入隔离区         │
      └────────┘ │+ NEEDS_REVIEW    │
                 │(源目录已无此文件)  │
                 └──────────────────┘

  manual_review 启用时:
  PROCESSING → 执行 copy+scrape+validate+classify
     → 文件在 temp 目录，import_path 已确定
     → 停止，不执行 dedup/rename/import
     → CONFIRMING (confirm_status=PENDING)
     → 源文件仍在 source_dir（未删除）
     
  CONFIRMING 的三个出口:
    ① 确认入库（✓）:
       → 执行 dedup → rename → import (temp → 目标目录)
       → 清理源目录 → SUCCESS (confirm_status=CONFIRMED)
    ② 修改分类（✎）:
       → 重新 classify → 更新 import_path
       → 文件不动 → 仍 CONFIRMING
    ③ 回退（↩）:
       → 删除 temp 文件
       → ROLLBACK（终态，源文件仍在 source_dir 等重新处理）

  NEEDS_REVIEW 的两个出口:
    ① 重试: 需用户先把文件从隔离区放回源目录
       → 下一轮扫描发现 → PENDING → 正常处理
    ② 忽略: → SKIPPED（终态，文件留在隔离区）

  ROLLBACK (终态):
    → 下一轮扫描发现源目录中的文件 → 新 source_path → 新任务
```

---

## 五、WebUI 任务面板详细设计

### 5.1 数据接口

前端通过以下 API 获取数据：
- `GET /api/tasks?page=1&page_size=20&status=all` → 列表数据（简要字段）
- `GET /api/tasks/stats` → 各状态 Tab 角标数字
- `GET /api/tasks/{id}` → 详情弹窗数据（全字段 + 字幕清单）

列表返回的 task 对象结构（简要版）：
```json
{
  "task_id": "abc123def456",
  "source_filename": "Breaking.Bad.S01E01.1080p.mkv",
  "status": "SUCCESS",
  "percentage": 100,
  "scrape_title_cn": "绝命毒师",
  "scrape_title_en": "Breaking Bad",
  "scrape_year": "2008",
  "subtitle_total": 3,
  "subtitle_success": 2,
  "import_path": "/vol1/影视/TV-R/绝命毒师 (2008)/Season 1/",
  "final_filename": "绝命毒师 S01E01.mkv",
  "skip_reason": "",
  "error_message": "",
  "created_at": "2026-05-20T14:30:00",
  "completed_at": "2026-05-20T14:35:00"
}
```

---

### 5.2 主列表布局

```
┌──────────────────────────────────────────────────────────────────┐
│  ● 任务列表                                      共 1,234 条      │
│                                                                  │
│  [ 全 部 ] [ 待处理 ] [ 处理中 ] [ 成 功 ] [ 确认中 ]            │
│    1000        3          1        980         2                  │
│  [ 失 败 ] [ 跳 过 ] [ 需介入 ] [ 已回退 ]             [ 🔄 刷新 ]│
│     10         5          2         0                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │   文件名 / 刮削结果      │字│状 态 │入库路径（截断） │操 作  ││
│  ├──────────────────────────────────────────────────────────────┤│
│  │ BB.S01E01.1080p.mkv     │  │      │                 │       ││
│  │ 绝命毒师 (2008)         │2/3│ 成功 │…/TV-R/绝命毒师…│◎  ▶  ││
│  │ ─────────────────────── │  │      │                 │       ││
│  │ av.mp4                  │  │      │                 │       ││
│  │ (刮削失败)              │ - │需介入│ (隔离区)        │◎     ││
│  │ ─────────────────────── │  │      │                 │       ││
│  │ 呼啸山庄 (2024).mkv     │  │      │                 │       ││
│  │ 呼啸山庄 (2024)         │ 1  │确认中│…/电影/2024/…   │◎ ✓✎↩││
│  │ ─────────────────────── │  │      │                 │       ││
│  │ Spirited.Away.2001.mkv  │  │      │                 │       ││
│  │ 千与千寻 (2001)         │ 1  │ 成功 │…/动漫电影/…    │◎  ▶  ││
│  │ ─────────────────────── │  │      │                 │       ││
│  │ Pokemon.S01E01.mkv      │  │      │                 │       ││
│  │ 宠物小精灵 (1997)       │ 0  │ 成功 │…/动漫/家庭向/… │◎     ││
│  │ ─────────────────────── │  │      │                 │       ││
│  │ Wuthering.H.2024.mkv    │  │      │                 │       ││
│  │ 呼啸山庄 (2024)         │ 1  │已回退│ (已退回源目录)  │◎     ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│   第 1 / 62 页    ◀ 上一页    下一页 ▶    跳转 [___] [Go]       │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 列表字段与行为详解

#### 列一：文件名 / 刮削结果（双行布局）

| 场景 | 第一行（源文件名） | 第二行（刮削结果） |
|------|-------------------|-------------------|
| 刮削成功 | 原始文件名（灰色小字） | 中文标题 (年份)，加粗 |
| 刮削失败 | 原始文件名 | (刮削失败)，灰色斜体 |
| 尚未刮削 | 原始文件名 | (待处理)，灰色 |
| 刮削跳过 | 原始文件名 | (已跳过) + 跳过原因截断 |

- 文件名超 40 字符截断，hover 显示全名（title 属性）
- 刮削标题超 25 字符截断

#### 列二：字幕

| 显示 | 含义 |
|------|------|
| `2/3` | 共 3 个字幕，2 个成功 |
| `1` | 1 个字幕，成功（无失败） |
| `0/2` | 2 个字幕，0 个成功 |
| `-` | 无字幕记录 |

- 蓝色可点击链接 → 打开字幕详情弹窗
- 灰色文本无链接

#### 列三：状态

| 状态值 | 显示文字 | 颜色 |
|--------|---------|------|
| PENDING | 待处理 | 黄色角标 |
| PROCESSING | 处理中 | 蓝色角标 + 微动画 |
| SUCCESS | 成功 | 绿色角标 |
| FAILED | 失败 | 红色角标 |
| SKIPPED | 跳过 | 灰色角标 |
| CONFIRMING | 确认中 | 橙色角标 |
| NEEDS_REVIEW | 需介入 | 紫色角标 |
| ROLLBACK | 已回退 | 蓝灰角标 |

#### 列四：入库路径

| 状态 | 显示 |
|------|------|
| SUCCESS/CONFIRMING | 入库目录路径（截断 30 字符） |
| 其他 | "--" 或 "(隔离区)" 或 "(已退回源目录)" |

#### 列五：操作（按状态动态显示）

| 按钮 | 图标 | 出现条件 | 调用的 API |
|------|------|---------|-----------|
| 详情 | ◎ | 所有任务 | 打开弹窗 GET /api/tasks/{id} |
| 确认 | ✓ | CONFIRMING | 确认入库（dedup→rename→import） |
| 修改分类 | ✎ | CONFIRMING | 重新 classify（文件在 temp 不动） |
| 回退 | ↩ | CONFIRMING | 删除 temp 文件 → ROLLBACK |
| 字幕 | ▶ | 有字幕记录 | GET /api/tasks/{id}/subtitles |
| 重试 | ↻ | FAILED/NEEDS_REVIEW | POST /api/tasks/{id}/retry |
| 忽略 | ⊘ | NEEDS_REVIEW | POST /api/tasks/{id}/ignore |
| 复制路径 | 📋 | SUCCESS | 复制到剪贴板 |

---

### 5.4 任务详情弹窗（点击 ◎）

弹窗按**状态不同展示不同内容**，所有状态均有"基本信息"卡片。刮削成功后展示刮削+入库卡片。CONFIRMING 状态下维度可编辑。

```
┌─── 任务详情：呼啸山庄 (2024).mkv ────────────────── [✕] ──────┐
│                                                                │
│  ┌ 基本信息 ─────────────────────────────────────────────────┐ │
│  │ 源文件    /downloads/Wuthering.Heights.2024.1080p.mkv    │ │
│  │ 文件大小  4.1 GB    重试次数  0                          │ │
│  │ 状  态    ◉ 确认中                                       │ │
│  │ 创建时间  2026-05-20 14:30:00                            │ │
│  │ 开始时间  2026-05-20 14:30:05                            │ │
│  │ 完成时间  2026-05-20 14:35:00                            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌ 刮削结果 ────────────────────────────────────────────────┐ │
│  │ 中文标题  呼啸山庄                                       │ │
│  │ 英文标题  Wuthering Heights                              │ │
│  │ 年  份    2024                                           │ │
│  │ 类  型    movie        季号 --      集号 --              │ │
│  │ 置信度    0.92                                          │ │
│  │                                                          │ │
│  │ 维度判断（CONFIRMING 时可修改，其他状态只读）:            │ │
│  │   media_type          [movie  ▼]                         │ │
│  │   documentary         [false  ▼]                         │ │
│  │   animation           [false  ▼]                         │ │
│  │   restricted_level    [7-12   ▼] ← 可改为 17+            │ │
│  │                                                          │ │
│  │   [ ✎ 重新分类入库 ]          [ ↩ 回退到源目录 ]        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌ 入库信息 ────────────────────────────────────────────────┐ │
│  │ 分类结果  规则4匹配: movie+norestricted → /电影/2024/    │ │
│  │ 入库目录  /vol1/影视/电影/2024/                          │ │
│  │ 文件位置  temp 目录（等待确认后入库）                    │ │
│  │ 确认状态  等待确认                                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌ 错误信息（如有）─────────────────────────────────────────┐ │
│  │ (无)                                                     │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│        [ ✓ 确认入库 ]        [ 关闭 ]                         │
└────────────────────────────────────────────────────────────────┘
```

#### 不同状态下的弹窗差异

| 状态 | 刮削卡片 | 入库卡片 | 维度可编辑 | 底部按钮 |
|------|---------|---------|-----------|---------|
| PENDING | 不展示 | 不展示 | — | 关闭 |
| PROCESSING | 不展示 | 不展示 | — | 关闭 |
| SUCCESS | 展示(只读) | 展示 | 否 | 复制路径 + 关闭 |
| FAILED | 展示(如有) | 不展示 | — | 重试 + 关闭 |
| SKIPPED | 展示(如有) | 不展示 | — | 关闭 |
| CONFIRMING | 展示 | 展示 | **是** | 确认 + 关闭 |
| NEEDS_REVIEW | 展示(如有) | 不展示 | — | 重试 + 忽略 + 关闭 |
| ROLLBACK | 展示(只读) | 不展示 | 否 | 关闭 |

#### 维度编辑下拉选项

| 维度 | 可选项 |
|------|--------|
| media_type | movie / tv |
| documentary | true / false |
| animation | true / false |
| restricted_level | 0-6 / 7-12 / 13-15 / 17+ |

- 点击"重新分类"→ 调用 `POST /api/tasks/{id}/reclassify` → 仅更新 import_path（文件在 temp 不动）
- 点击"回退"→ 弹二次确认 → 调用 `POST /api/tasks/{id}/rollback` → 删除 temp 文件 → 关闭弹窗

---

### 5.5 字幕详情弹窗（点击列表 "2/3" 链接）

```
┌─── 字幕详情：绝命毒师 S01E01.mkv ──────────── [✕] ──────────┐
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ # │ 源文件名             │语│状态│入库后文件名   │ 操作  ││
│  ├──────────────────────────────────────────────────────────┤│
│  │ 1 │ BB.S01E01.1080p.zh  │zh│成功│绝命毒师…zh  │ [📋]  ││
│  │ 2 │ BB.S01E01.1080p.en  │en│成功│绝命毒师…en  │ [📋]  ││
│  │ 3 │ BB.S01E01.1080p.ja  │ja│失败│(文件不存在) │  --   ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  字幕状态汇总：2/3 成功，1/3 失败                            │
│  失败原因：源字幕文件不存在                                  │
│                                                              │
│                       [ 关闭 ]                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 5.6 回退确认弹窗（点击 ↩ 回退）

```
┌─── 确认回退 ───────────────────────────────── [✕] ──────────┐
│                                                              │
│    确定要回退吗？将删除 temp 目录中的临时文件。               │
│                                                              │
│    视频文件：                                                │
│    /tmp/nas-import/呼啸山庄.mkv                              │
│                                                              │
│    字幕文件（1个）：                                         │
│    /tmp/nas-import/呼啸山庄.zh.srt                           │
│                                                              │
│    注意：源文件未受影响，仍在 source_dir。                    │
│    下一轮扫描会重新发现并创建新任务。                         │
│                                                              │
│                  [ 取消 ]        [ 确定回退 ]                 │
└──────────────────────────────────────────────────────────────┘
```

---

### 5.7 状态筛选 Tab 条

各 Tab 按状态筛选列表，角标数字来自 `GET /api/tasks/stats`：

```json
{
  "total": 1234, "pending": 3, "processing": 1, "success": 980,
  "confirming": 2, "failed": 10, "skipped": 5, "needs_review": 2,
  "rollback": 0
}
```

- 点击 Tab → `switchTaskTab(status)` → 重新请求列表
- Tab 颜色与对应状态角标色一致
- "全部" Tab 显示所有状态

---

### 5.8 分页控件

```
 第 1 / 62 页    ◀ 上一页    下一页 ▶    跳转 [___] [Go]
```

- 当前页 = 1 时，"上一页"置灰不可点击
- 当前页 = 末页时，"下一页"置灰
- 跳转输入框输入数字，回车或点 Go
- 切换 Tab 时重置为第 1 页

---

### 5.9 操作提示（Toast）

操作成功/失败后底部 Toast 提示：

| 操作 | 成功 Toast | 失败 Toast |
|------|-----------|-----------|
| 确认入库 | "已成功入库 ✓" | "确认失败：{原因}" |
| 重新分类 | "已重新分类 → {新路径}" | "重新分类失败：{原因}" |
| 回退 | "已回退，temp 文件已清理" | "回退失败：{原因}" |
| 复制路径 | "路径已复制到剪贴板" | — |

---

### 5.10 CSS 样式要点

| 组件 | 样式说明 |
|------|---------|
| 状态筛选 Tab | `display:flex; gap:6px; flex-wrap:wrap` 彩色圆角按钮，active 时填充对应状态色 |
| 表格行 | 双行布局（`grid` 或 `flex column`），源文件名灰色小字在上，标题加粗在下 |
| 状态角标 | `inline-block; padding:2px 8px; border-radius:10px; font-size:11px` |
| 弹窗 | `position:fixed; z-index:1000; max-width:700px; max-height:85vh` 居中 + 遮罩 |
| 维度下拉 | `select` 带边框，可编辑状态下蓝色边框，只读状态灰色边框+pointer-events:none |
| 操作按钮 | 28x28px 圆角方形，hover 变色 |
| 分页控件 | 底部居中，按钮+页码+跳转输入框 |

---

## 六、API-first 设计：Hermes 调用路径

所有任务管理功能必须通过 REST API 暴露，确保 Hermes（通知机器人）可通过 Skill 调用。

### 6.1 完整 API 列表

| 方法 | 路径 | 用途 | Hermes 场景 |
|------|------|------|------------|
| GET | `/api/tasks` | 分页任务列表 | 查询待处理/失败任务 |
| GET | `/api/tasks/stats` | 各状态计数 | 定时报告任务统计 |
| GET | `/api/tasks/{id}` | 任务全字段 | 查看某个任务详情 |
| GET | `/api/tasks/{id}/subtitles` | 字幕列表 | 查看某任务字幕 |
| POST | `/api/tasks/{id}/confirm` | 确认入库（dedup→rename→import） | Hermes 一键确认 |
| POST | `/api/tasks/{id}/reclassify` | 修改维度重新分类 | Hermes 纠正分类 |
| POST | `/api/tasks/{id}/rollback` | 回退（删除 temp 文件） | Hermes 回退问题文件 |
| POST | `/api/tasks/{id}/retry` | 重试失败任务 | Hermes 批量重试 |
| POST | `/api/tasks/{id}/ignore` | 忽略需介入任务 | Hermes 批量忽略 |
| POST | `/api/tasks/confirm-all` | 批量确认 | Hermes 一键全确认 |

### 6.2 Hermes Skill 调用示例

```
场景：用户对 Hermes 说"确认所有待确认的文件"

Hermes Skill 流程：
  1. GET /api/tasks/stats → 获取 confirming 数量
  2. 如果 > 0：
     POST /api/tasks/confirm-all
  3. 返回结果："已确认 N 个文件"

场景：用户对 Hermes 说"把呼啸山庄改成限制级"

Hermes Skill 流程：
  1. GET /api/tasks?status=confirming → 找到呼啸山庄任务
  2. POST /api/tasks/{id}/reclassify
     Body: { dimensions: { restricted_level: "17+" } }
  3. 返回结果："已重新分类 → /vol1/影视/电影-R/2024/"

场景：用户对 Hermes 说"回退所有刮削失败的任务"

  Hermes Skill 流程：
    1. GET /api/tasks?status=failed → 找到失败任务列表
    2. 对每个 FAILED 任务：
       POST /api/tasks/{id}/rollback
    3. 返回结果："已回退 N 个任务（temp 文件已清理）"
```

### 6.3 API 设计原则

1. **幂等性**：重复调用 confirm/rollback 不产生副作用
2. **原子性**：每个 POST 操作要么全部成功，要么全部回滚（含字幕一起）
3. **一致性**：所有 API 返回相同格式 `{ code, message, data }`
4. **安全性**：文件操作 API 必须在 `allowed_base_dirs` 白名单内
5. **无状态**：不依赖 session，Hermes 可直接调用

---

## 七、Key Design Decisions 汇总

### Q1: 数据库设计 — 两张表

**Decision:** tasks（视频主表）+ task_subtitles（字幕子表）

### Q2: 两层去重分工

**Decision:** 源端去重（source_path 精确匹配，防重复处理+防Token浪费）+ 入库端去重（标题模糊匹配，防同名入库），互补不替代。

### Q3: 卡住文件处理

**Decision:** retry_count >= max_auto_retries（默认3）→ 文件移入隔离区 + NEEDS_REVIEW，源目录不再有该文件。

### Q4: 历史已处理文件重新出现

**Decision:** 不自动处理。将文件从源目录移入隔离区 + NEEDS_REVIEW + 原因说明。用户如需重新导入，把文件放回源目录即可。

### Q5: 人工确认机制（分类错误在线修正）

**Decision:** manual_review.enabled 开关控制。启用后 Pipeline 在 classify 步骤后停止，文件留在 temp 目录，源文件不删除。CONFIRMING 状态下：
- 确认入库：执行 dedup → rename → import（从 temp 到目标目录）→ SUCCESS
- 修改分类：用户在弹窗中改维度值 → 重新 classify → 更新 import_path（文件不动）
- 回退：删除 temp 文件 → ROLLBACK（源文件未受影响）

核心优势：文件在 temp 目录不动，修改分类只需重算路径不需移动文件，回退只需删 temp。

### Q6: 字幕作为子记录

**Decision:** 独立 task_subtitles 表，每条字幕有自己的状态、入库路径。字幕 copy/import 失败不阻塞视频流程。

### Q7: 配置不迁移数据库

**Decision:** 保持 YAML 文件，仅新增 source_dedup 和 manual_review 配置项。

### Q8: 日志不迁移数据库

**Decision:** 保持现有文件存储方式，数据量大且无查询需求。

### Q9: 分页

**Decision:** 服务端分页，默认 20 条/页，按 created_at 倒序。

### Q10: 回退到源目录

**Decision:** CONFIRMING 状态文件可通过 WebUI 或 API 一键回退。系统从 source_filename 恢复原始视频名称，从 task_subtitles 恢复各字幕原始名称，移回 source_dir。旧任务标记 ROLLBACK（终态），文件下一轮扫描自动创建新任务。

### Q11: API-first + Hermes 集成

**Decision:** 所有任务操作功能通过 REST API 暴露（confirm/reclassify/rollback/retry/ignore/confirm-all），Hermes 通过 HTTP 调用完成自动化操作。API 遵循幂等性、原子性、无状态原则。

### Q12: 字幕始终跟随视频

**Decision:** 所有涉及文件移动的操作（移入隔离区、回退源目录、修改分类重新入库）都必须同步处理关联字幕，视频和字幕作为一个原子操作单元。

---

## Assumption Audit

| 假设 | 分类 | 依据 |
|------|------|------|
| SQLite 在 fnOS 上可用 | ✅ Bedrock | Python 自带 sqlite3，fnOS Linux |
| source_path 精确匹配可行 | ✅ Bedrock | 经过场景A/B/C分析，配合入库端模糊匹配，覆盖所有场景 |
| manual_review 在 classify 后停止可避免无效文件移动 | ✅ Bedrock | 文件在 temp 不动，修改分类仅需更新 import_path |
| SQLite 承受 NAS 级任务量 | ✅ Bedrock | 每日几十条，SQLite 轻松百万级 |
| retry_count=3 作为卡住阈值合理 | ⚠️ Unverified | 基于经验，后续可暴露为配置项让用户调 |

## Open Questions（已解决）

1. ~~重复文件提示问题~~ → **不需要 .txt 提示**。用户放回源目录不改名 → 重新被移到隔离区，系统逻辑自洽
2. ~~WebUI 打开文件~~ → **暂不做**。SUCCESS 状态提供"复制路径到剪贴板"按钮
3. ~~旧数据迁移~~ → **不做迁移**。全新 SQLite 启动，旧 tasks.json 保留在原位置不动
4. ~~文件名随分类改变~~ → **已确认**。修改 restricted_level 只改变目录，文件名保持一致
5. ~~隔离区配置~~ → **已加入 WebUI 配置界面**，放在"入库设置"子页签，和 source_dir 同组

## Out of Scope

- 配置系统迁移到数据库
- 日志系统迁移到数据库
- 旧数据迁移（现有 tasks.json → SQLite）
- 并发处理（max_concurrent 实现）
- 任务搜索/排序/优先级
- fnOS 文件管理器集成（文件打开功能）
- 隔离区自动清理策略

## Next Steps

- 用户评审本方案 → 确认后 `/plan` 生成实施计划
- 实施顺序：db.py → task_manager 重写 → pipeline 改造 → API 适配 → WebUI 改造 → 迁移脚本 → 联调测试
