# Module: Storage

## Code

- `media_importer/storage/file_scanner.py`
- `media_importer/storage/file_copier.py`
- `media_importer/storage/file_mover.py`
- `media_importer/storage/file_analyzer.py`
- `media_importer/storage/dedup_checker.py`
- `media_importer/storage/classifier.py`
- `media_importer/storage/source_cleaner.py` compatibility alias
- `media_importer/domains/source_cleaning/cleaner.py`

## Responsibility

文件系统相关业务能力：扫描、复制、移动、分类、去重、分析、源目录清理。

源目录清理实现已迁移到 `media_importer/domains/source_cleaning/`；`storage/source_cleaner.py` 仅保留旧 import 和 patch 路径兼容。

## Safety

删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。
