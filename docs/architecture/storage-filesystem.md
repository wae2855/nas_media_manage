# Storage and Filesystem Architecture

## Responsibilities

- 扫描源目录。
- 复制文件到临时目录。
- 生成目标文件名。
- 移动文件到入库目录。
- 去重和质量策略。
- 源目录清理。

## Entry Points

- `media_importer/storage/file_scanner.py`
- `media_importer/storage/file_copier.py`
- `media_importer/storage/file_mover.py`
- `media_importer/storage/dedup_checker.py`
- `media_importer/storage/classifier.py`
- `media_importer/storage/source_cleaner.py`

## Safety

文件删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。
