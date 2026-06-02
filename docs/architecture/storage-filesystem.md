# Storage and Filesystem Architecture

## Responsibilities

- 扫描源目录。
- 复制文件到临时目录。
- 生成目标文件名。
- 移动文件到入库目录。
- 去重和质量策略。
- 源目录清理。

## Entry Points

- `media_importer/infrastructure/filesystem/file_copier.py`
- `media_importer/features/import_flow/services/classification_rules.py`
- `media_importer/storage/file_scanner.py`
- `media_importer/storage/file_copier.py` compatibility alias
- `media_importer/storage/classifier.py` compatibility alias
- `media_importer/storage/file_mover.py`
- `media_importer/storage/dedup_checker.py`
- `media_importer/features/recycle/manager.py`
- `media_importer/features/source_cleaning/cleaner.py`
- `media_importer/storage/source_cleaner.py` compatibility alias

## Safety

文件删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。

`FileCopier` 是基础文件系统复制能力，真实实现位于 `media_importer/infrastructure/filesystem/file_copier.py`。Import-flow 可以直接依赖该 infrastructure API；旧 `storage/file_copier.py` 仅保留为兼容导入。

分类规则和模板渲染是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/classification_rules.py`。旧 `storage/classifier.py` 仅保留为兼容导入。
