# Recycle Architecture

## Responsibilities

- 将源文件、入库旧文件、任务关联文件安全移入回收站。
- 浏览回收站。
- 恢复文件。
- 永久删除回收站文件。
- 按保留天数清理。

## Entry Points

- `media_importer/features/recycle/manager.py`
- `media_importer/features/recycle/browser.py`
- `media_importer/core/safety.py` compatibility facade
- `media_importer/infrastructure/filesystem/safety.py` path and filesystem safety primitives
- `media_importer/api/recycle_handlers.py`

## Rule

所有删除/覆盖影视文件必须先走回收站。临时文件边界见 [../standards/safety.md](../standards/safety.md)。

旧 `core/recycle/*` 兼容层已删除（2026-06 清理）；`core/safety.py` facade 仍保留。新代码必须从 `features/recycle` 和 `infrastructure/filesystem` 导入。
