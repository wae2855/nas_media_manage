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

已新增 `media_importer/core/task_lifecycle.py`，用于集中状态转换和文件位置规则。

当前已集中：

- processing 开始；
- temp ready；
- confirming；
- needs review；
- failed；
- skipped；
- imported；
- retry reset。

当前仍保持兼容：pipeline step 继续接收原始 task dict，后续服务化重构再逐步扩大使用范围。
