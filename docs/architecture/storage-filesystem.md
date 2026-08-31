# Storage and Filesystem Architecture

## Responsibilities

- 基础路径校验、权限检查、安全复制、安全移动/删除和指纹计算。
- 扫描源目录。
- 生成目标文件名。
- 移动文件到入库目录。
- 只读冲突检测、改名建议与用户确认后的安全替换。
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

跨设备文件移动不再使用裸 `copy2 + remove`：当前协议以 `O_NOFOLLOW` 打开目标侧 `.copying`，校验临时文件身份、已有续传前缀、源版本、大小与 SHA-256，`fsync` 后以 no-replace 原子发布，最后才允许处理源文件。复制期间源文件变化、目标并发出现、空间不足或目标掉线都会保留源文件。中转根、回收根和用户选择的片库根必须已存在；运行时只允许在已验证根下创建业务子目录，禁止挂载消失后重建同名根路径。

配置页的存储就绪检查由 `features/configuration/storage_readiness.py` 提供，统一输出目录角色、`realpath/st_dev`、挂载来源、文件系统类型、权限、容量和 `READY/BLOCKED`。目录选择/重新绑定成功后会把身份快照写入 `storage_identities`；自动扫描、源清理、来源整组回收和入库在动作前复核，身份变化必须暂停并要求重新绑定。中转、回收和日志必须为可确认的本地位置；远程或未知来源/目标降级为人工运行，不能自动运行。

目录角色拓扑由 `features/configuration/storage_topology.py` 统一判断。所有操作目录和片库根必须互不包含；启动清理与通用任务文件动作还会再次确认真实路径归属并拒绝符号链接。目标片库既不能被伪装成中转/来源清理，也不能通过任务删除或通用重命名改变。

`FileCopier` 是基础文件系统复制能力，真实实现位于 `media_importer/infrastructure/filesystem/file_copier.py`。路径校验、扩展名校验、安全移动/删除、权限检查和文件指纹真实实现位于 `media_importer/infrastructure/filesystem/safety.py`。Import-flow、API 和 feature service 可以直接依赖这些 infrastructure API；旧 `core/safety.py` 仅保留为兼容 facade。

分类规则和模板渲染是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/classification_rules.py`。

同作品/同名目标检测和重命名建议是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/dedup_rules.py` 与 `services/dedup.py`。检测只扫描本任务实际入库目录并零写入；旧质量比较只保留为兼容代码，不再自动决定片库文件去留。

用户确认替换时，新文件先在目标侧以唯一 `.replacement.tmp` 完整复制和 SHA-256 校验；随后以唯一临时名认领现有文件并再次核对确认时的 SHA-256，校验通过才进入本地回收区，最后以 no-replace 协议发布。回收失败恢复旧文件；并发出现新目标时不覆盖该目标，旧文件保留在回收区；永不调用永久删除作为兜底。

源目录扫描和任务感知过滤真实实现位于 `media_importer/features/import_flow/scan_service.py`。

文件名模板和字幕命名规则真实实现位于 `media_importer/features/import_flow/services/naming.py`。入库移动真实实现位于 `media_importer/features/import_flow/services/file_operations.py`。源文件安全删除、伴生文件识别、非媒体源文件清理和空父目录清理真实实现位于 `media_importer/features/source_files/`。
