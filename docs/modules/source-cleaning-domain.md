# Module: Source Cleaning Feature

## Code

- `media_importer/features/source_cleaning/cleaner.py`
- `media_importer/features/source_cleaning/records.py`
- `media_importer/features/source_cleaning/__init__.py`
- `media_importer/storage/source_cleaner.py` compatibility alias
- `media_importer/api/source_cleaner_handlers.py`
- `media_importer/core/db/cleaner_repo.py`

## Responsibility

源目录清理业务域，用于识别任务之外的源目录垃圾文件、Sample、广告文件、无关文本、空目录和黑名单目录，并通过回收站安全规则执行清理。

当前实现所在地：

- `SourceCleaner`: `media_importer/features/source_cleaning/cleaner.py`
- 清理记录 repo 入口: `media_importer/features/source_cleaning/records.py`

兼容路径：

- `media_importer/storage/source_cleaner.py`

## Boundary

源目录清理器独立于主任务流。任务完成后的源文件处理仍归 `features/import_flow/services/source_cleanup.py` 管理。

`storage/source_cleaner.py` 是旧 public import 的兼容别名，历史 patch 路径必须继续可用。

## Safety

- 删除文件必须调用回收站安全函数。
- 目录清理必须调用目录回收站函数。
- `source_dir` 和 `recycle_dir` 权限由配置和 API 执行前检查共同保护。

## Tests

- `tests/test_feature_source_cleaning_compatibility.py`
- `tests/test_recycle_safety.py`
- 配置相关测试
