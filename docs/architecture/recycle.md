# Recycle Architecture

## Responsibilities

- 将源文件、入库旧文件、任务关联文件安全移入回收站。
- 浏览回收站。
- 恢复文件。
- 永久删除回收站文件。
- 按保留天数清理。

## Entry Points

- `media_importer/core/recycle/manager.py`
- `media_importer/core/recycle/browser.py`
- `media_importer/api/recycle_handlers.py`

## Rule

所有删除/覆盖影视文件必须先走回收站。临时文件边界见 [../standards/safety.md](../standards/safety.md)。
