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
- `media_importer/features/recycle/manager.py`
- `media_importer/features/source_cleaning/cleaner.py`

> 历史 `media_importer/storage/` 兼容层已随清理迁移删除（2026-06），新代码禁止从该路径导入（architecture guard 拦截）。

## Safety

文件删除和覆盖必须遵守 [../standards/safety.md](../standards/safety.md)。

跨设备文件移动不再使用裸 `copy2 + remove`：当前协议写入目标侧 `.copying`，校验已有续传前缀、源版本、大小与 SHA-256，`fsync` 后原子发布，最后才允许处理源文件。复制期间源文件变化、空间不足或目标掉线都会保留源文件。中转根、回收根和用户选择的片库根必须已存在；运行时只允许在已验证根下创建业务子目录，禁止挂载消失后重建同名根路径。

配置页的存储就绪检查由 `features/configuration/storage_readiness.py` 提供，统一输出目录角色、`realpath/st_dev`、挂载来源、文件系统类型、权限、容量和 `READY/BLOCKED`。中转、回收和日志必须为可确认的本地位置；远程或未知来源/目标降级为人工运行，不能自动运行。

`FileCopier` 是基础文件系统复制能力，真实实现位于 `media_importer/infrastructure/filesystem/file_copier.py`。路径校验、扩展名校验、安全移动/删除、权限检查和文件指纹真实实现位于 `media_importer/infrastructure/filesystem/safety.py`。Import-flow、API 和 feature service 可以直接依赖这些 infrastructure API；旧 `core/safety.py` 仅保留为兼容 facade。

分类规则和模板渲染是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/classification_rules.py`。

去重、质量比较和重命名建议是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/dedup_rules.py`。

源目录扫描和任务感知过滤真实实现位于 `media_importer/features/import_flow/scan_service.py`。

文件名模板和字幕命名规则真实实现位于 `media_importer/features/import_flow/services/naming.py`。入库移动真实实现位于 `media_importer/features/import_flow/services/file_operations.py`。源文件安全删除、伴生文件识别、非媒体源文件清理和空父目录清理真实实现位于 `media_importer/features/source_files/`。
