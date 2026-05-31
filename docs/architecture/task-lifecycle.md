# Task Lifecycle

## Current Statuses

当前任务状态仍由 DB 常量、TaskManager、pipeline、API、前端共同使用。

常见状态：

- `PENDING`
- `PROCESSING`
- `CONFIRMING`
- `FAILED`
- `SKIPPED`
- `SUCCESS`
- `NEEDS_REVIEW`

## Current File Locations

`file_location` 用于追踪文件当前位置，典型值：

- `source`
- `temp`
- `import`
- `recycle`

## Direction

后续会新增 `core/task_lifecycle.py`，集中状态转换和文件位置规则。当前文档暂不深写所有转换细节，避免在即将重构前固化散落逻辑。
