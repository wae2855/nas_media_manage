# Storage and Filesystem Architecture

## Responsibilities

- 基础路径校验、权限检查、安全复制、安全移动/删除和指纹计算。
- 扫描源目录。
- 生成目标文件名。
- 移动文件到入库目录。
- 去重和质量策略。
- 源文件和伴生文件处理策略。
- 源目录清理。

## Entry Points

- `media_importer/infrastructure/filesystem/file_copier.py`
- `media_importer/infrastructure/filesystem/safety.py`
- `media_importer/features/import_flow/scan_service.py`
- `media_importer/features/import_flow/services/classification_rules.py`
- `media_importer/features/import_flow/services/dedup_rules.py`
- `media_importer/features/import_flow/services/naming.py`
- `media_importer/features/import_flow/services/file_operations.py`
- `media_importer/features/source_files/`
- `media_importer/storage/file_scanner.py`
- `media_importer/storage/file_copier.py` compatibility alias
- `media_importer/storage/classifier.py` compatibility alias
- `media_importer/storage/file_mover.py` compatibility wrapper
- `media_importer/storage/dedup_checker.py` compatibility alias
- `media_importer/features/recycle/manager.py`
- `media_importer/features/source_cleaning/cleaner.py`
- `media_importer/storage/source_cleaner.py` compatibility alias

## Safety

文件删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。

`FileCopier` 是基础文件系统复制能力，真实实现位于 `media_importer/infrastructure/filesystem/file_copier.py`。路径校验、扩展名校验、安全移动/删除、权限检查和文件指纹真实实现位于 `media_importer/infrastructure/filesystem/safety.py`。Import-flow、API 和 feature service 可以直接依赖这些 infrastructure API；旧 `core/safety.py` 仅保留为兼容 facade。

分类规则和模板渲染是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/classification_rules.py`。旧 `storage/classifier.py` 仅保留为兼容导入。

去重、质量比较和重命名建议是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/dedup_rules.py`。旧 `storage/dedup_checker.py` 仅保留为兼容导入。

源目录扫描和任务感知过滤真实实现位于 `media_importer/features/import_flow/scan_service.py`。旧 `storage/file_scanner.py` 仅保留为兼容导入。

文件名模板和字幕命名规则真实实现位于 `media_importer/features/import_flow/services/naming.py`。入库移动真实实现位于 `media_importer/features/import_flow/services/file_operations.py`。源文件安全删除、伴生文件识别、非媒体源文件清理和空父目录清理真实实现位于 `media_importer/features/source_files/`。`storage/file_mover.py` 仅保留兼容 wrapper。
