# Module: Storage

## Code

- `media_importer/storage/file_scanner.py`
- `media_importer/storage/file_copier.py`
- `media_importer/storage/file_mover.py`
- `media_importer/storage/file_analyzer.py`
- `media_importer/storage/dedup_checker.py`
- `media_importer/storage/classifier.py`
- `media_importer/storage/source_cleaner.py`

## Responsibility

文件系统相关业务能力：扫描、复制、移动、分类、去重、分析、源目录清理。

## Safety

删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。
