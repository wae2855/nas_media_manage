# Product Workflows

## Import Workflow

```text
扫描源目录 -> 创建任务 -> 复制到临时目录 -> 刮削元数据 -> 三级匹配判断 -> 分类路径 -> 去重 -> 重命名 -> 入库 -> 通知/记录
```

Feature ownership:

- task creation and status: `features/tasks`
- process orchestration: `features/import_flow`
- scraping and matching: `features/scraping`
- provider metadata: `features/providers`
- source cleanup after success: `features/source_files` + `features/recycle`

## Manual Review Workflow

```text
匹配疑虑/需确认 -> 停在临时目录 -> 用户确认/重分类/重命名/忽略 -> 继续入库或完成跳过
```

## Source Cleanup Workflow

源目录清理器独立于主任务流，负责识别源目录中的垃圾文件、Sample、广告文件、无关标记文件，并按安全规则移入回收站或清理。

Feature ownership: `features/source_cleaning` decides what to clean; `features/recycle` performs safe removal.

## Recycle Workflow

所有需要移除的源文件或入库文件先进入回收站；用户可浏览、恢复、永久删除，系统可按保留天数清理。

Feature ownership: `features/recycle` owns move/list/restore/delete/cleanup semantics.
