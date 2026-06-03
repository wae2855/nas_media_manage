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
- `media_importer/features/import_flow/scan_service.py`
- `media_importer/features/import_flow/services/classification_rules.py`
- `media_importer/features/import_flow/services/dedup_rules.py`
- `media_importer/features/import_flow/services/naming.py`
- `media_importer/storage/file_scanner.py`
- `media_importer/storage/file_copier.py` compatibility alias
- `media_importer/storage/classifier.py` compatibility alias
- `media_importer/storage/file_mover.py`
- `media_importer/storage/dedup_checker.py` compatibility alias
- `media_importer/features/recycle/manager.py`
- `media_importer/features/source_cleaning/cleaner.py`
- `media_importer/storage/source_cleaner.py` compatibility alias

## Safety

文件删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。

`FileCopier` 是基础文件系统复制能力，真实实现位于 `media_importer/infrastructure/filesystem/file_copier.py`。Import-flow 可以直接依赖该 infrastructure API；旧 `storage/file_copier.py` 仅保留为兼容导入。

分类规则和模板渲染是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/classification_rules.py`。旧 `storage/classifier.py` 仅保留为兼容导入。

去重、质量比较和重命名建议是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/dedup_rules.py`。旧 `storage/dedup_checker.py` 仅保留为兼容导入。

源目录扫描和任务感知过滤真实实现位于 `media_importer/features/import_flow/scan_service.py`。旧 `storage/file_scanner.py` 仅保留为兼容导入。

文件名模板和字幕命名规则真实实现位于 `media_importer/features/import_flow/services/naming.py`。入库移动、源文件安全删除、附属文件识别和空父目录清理真实实现位于 `media_importer/features/import_flow/services/file_operations.py`。`storage/file_mover.py` 仅保留兼容 wrapper。
