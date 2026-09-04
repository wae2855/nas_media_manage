# Import Pipeline

## Current Entry Points

- `media_importer/features/import_flow/runner.py`
- `media_importer/features/import_flow/`
- `media_importer/features/import_flow/steps/`
- `media_importer/features/import_flow/steps/file.py`
- `media_importer/features/import_flow/steps/scrape.py`
- `media_importer/features/import_flow/confirm.py`
- `media_importer/features/import_flow/services/`

## Current Flow

```text
scan
  -> read-only source identity / release-name parse
  -> atomic create-or-reuse source task
  -> scrape (or manual candidate apply)
  -> validate -> classify -> rename preview -> dedup preflight
  -> [await manual review/conflict decision when needed]
  -> source-to-target task staging verified copy
  -> subtitle-first, video-last bundle publish
  -> notify -> source_cleanup -> record

completed fallback result
  -> create linked REORGANIZE task (original stays SUCCESS/DONE)
  -> manual scrape or dimension edit -> formal rule required
  -> library-to-library bundle stage/verify/publish (no source cleanup)
  -> mark linked task SUCCESS and original organization result ORGANIZED
```

大文件复制必须在作品身份、规则片库、相对目录、最终文件名和冲突决策明确后开始。冲突选择“保留片库文件”时直接跳过且保留来源，不制造中转副本。发布新作品时，字幕先发布、视频最后以 no-replace 发布；视频是文件包提交标记。

## Direction

Import flow 已引入：

- `Import Flow Feature`: `media_importer/features/import_flow/`
- `TaskContext`: `media_importer/features/import_flow/context.py`
- `TaskLifecycle`: `media_importer/core/task_lifecycle.py`
- `ClassificationService`: `media_importer/features/import_flow/services/classification.py`
- `DedupService`: `media_importer/features/import_flow/services/dedup.py`
- `ImportService`: `media_importer/features/import_flow/services/import_service.py`
- `SourceCleanupService`: `media_importer/features/source_files/cleanup_service.py`
- `ReviewDecisionService`: `media_importer/features/import_flow/services/review.py`
- `ReorganizationService`: `media_importer/features/import_flow/services/reorganization.py`

当前 `TaskContext` 和 `TaskLifecycle` 已接入 runner、confirm 和 retry 逻辑。分类、去重、导入和审核决策已从 step 内抽成 import-flow service；源文件清理策略已独立到 `features/source_files`；step 主要保留进度、日志和 DB 状态写入。

扫描、watcher 和手动单文件入口共享 `TaskManager.create_or_reuse_source_task()`。真实路径归一化、最新任务判定与创建在同一进程锁内完成，任务处理在锁外执行；因此 fnOS 单实例中的重复点击、重复扫描和入口竞争只会产生一个任务。数据库仍允许来源文件大小明确变化后建立新的审计任务，不使用唯一键抹平历史。不同路径不能仅凭当前弱来源指纹自动合并失败任务。

长文件阶段通过 `TaskProgressReporter` 节流落库：阶段切换和完成立即保存，其余更新满足至少 1 秒、1% 或 64 MB 任一条件才写 SQLite。来源→目标任务暂存和来源→本地回收统一显示传输、源校验、目标校验和发布阶段。SHA-256、no-replace 与删除顺序不因进度展示而改变。

新作品文件包发布使用持久化 `bundle_state/bundle_manifest/bundle_committed` 日志。目标侧全部成员先使用本任务唯一暂存名；字幕依次发布，视频最后发布。服务在视频发布前中断时，普通入库删除“本任务创建且指纹匹配”的目标临时成员并保留来源，重新整理任务才退回原片库位置；视频已发布且全部成员指纹吻合时只补齐数据库成功状态、保留来源且不重写片库；成员残缺或变化时冻结现场并要求人工检查。

新任务的执行顺序固定为“刮削与人工选片 → 维度和规则 → 目标命名 → 目标片库重名检查 → 人工冲突决定 → 大文件传输”。中心中转目录和旧任务断点已取消；重试从来源完整重来。后台空闲扫描不得读取任意目标片库，只在具体任务已选定目标后检查该一个目标根。

分类使用兜底目录时不再静默自动完成：任务先停在 `AWAIT_REVIEW`，只有用户明确接受待整理区才继续。入库成功仍是不可变的 `SUCCESS/DONE`；后续修改维度或重新刮削通过独立 `REORGANIZE` 任务完成。重新整理以待整理区现存影片和字幕为来源，必须匹配正式规则，复用文件包提交与重启恢复，但不执行来源复制、来源清理或目标覆盖。

现有影片替换仍是更窄的单视频事务：用户逐项确认后，旧视频先进入本地回收，再发布新视频。带字幕作品的完整替换事务尚未开放，因此这类冲突不展示“替换”动作，只能保留现有或另存一份。

片库文件发布后先写 `import_success=1`，再尝试来源单元处理，最后才进入 `SUCCESS/DONE`。来源处理失败会保留来源并记录 `source_cleanup_status`，不能把已安全入库的影片按整体入库失败重复执行。

`media_importer/features/import_flow/` 是入库流程业务域入口。旧 `media_importer/pipeline/` 包装层已归档，不再作为当前可导入入口。新代码、测试和文档必须直接使用 `media_importer.features.import_flow`。

## Change Guide

- 改分类路径规则：先看 `features/import_flow/services/classification.py`。
- 改同名策略：先看 `features/import_flow/services/dedup.py`，涉及回收站时再看 `SourceCleanupService`。
- 改入库移动、字幕落库、确认入库：先看 `features/import_flow/services/import_service.py`。
- 改已完成兜底作品的后续整理：先看 `features/tasks/organization_service.py` 与 `features/import_flow/services/reorganization.py`。
- 改成功入库、跳过或临时文件后的源文件处理：先看 `features/source_files/cleanup_service.py`。
- 改匹配级别、人工确认、匹配疑虑：先看 `features/import_flow/services/review.py`。
- 改流程 step 顺序、进度、日志或 DB 状态写入：先看 `features/import_flow/steps/`。
- 改状态字段：先看 `TaskLifecycle`。
