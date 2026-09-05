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

跨设备文件移动不再使用裸 `copy2 + remove`：当前协议以 `O_NOFOLLOW` 打开目标侧 `.copying`，校验临时文件身份、源版本、大小与 SHA-256，`fsync` 后以 no-replace 原子发布，最后才允许处理源文件。复制期间源文件变化、目标并发出现、空间不足或目标掉线都会保留源文件。回收根和用户选择的片库根必须已存在；运行时只允许在已验证根下创建业务子目录，禁止挂载消失后重建同名根路径。

校验诊断先复核来源在完整哈希后的 size/mtime_ns/device/inode 快照，再比较来源与目标摘要。来源变化提示等待上游稳定，不归因于目标；来源快照稳定而目标摘要不一致时，普通入库仅允许删除本任务拥有的 `.bundle.tmp.copying` 并从零重试一次，持续不一致提示检查目标存储或挂载并停止发布。任务临时文件清理额外验证授权目录、后缀、所有者、单硬链接普通文件和 inode，因此可安全覆盖超过 50 GiB 的影片暂存；统计快照不能证明同大小同时间的内容绝对未变，SHA-256 始终保留为最终门禁。

该协议发出只读进度事件：`resume_check`、`transfer`、`verify_source`、`verify_target`、`publish`。回调只能观察已完成字节，不能跳过检查、提前发布或改变源文件删除条件；同盘 no-replace 移动只显示快速发布，跨盘才显示传输字节。

配置页的存储就绪检查由 `features/configuration/storage_readiness.py` 提供，统一输出目录角色、`realpath/st_dev`、挂载来源、文件系统类型、权限、容量和 `READY/BLOCKED`。它只呈现物理目录事实，不呈现规则关联异常。目录选择/重新绑定成功后会把身份快照写入 `storage_identities`；身份比较以真实路径、挂载来源、挂载点和文件系统类型为稳定事实，`st_dev` 只供诊断，不能因重启后的设备号重排单独阻断。fnOS 本应用私有目录不依赖共享目录 ACL 清单，以当前进程真实读写结果为准；外部目录仍必须同时通过系统授权与文件系统检查。自动扫描、源清理、来源整组回收和入库在动作前复核，真实挂载身份变化必须暂停并要求重新绑定。回收和日志必须为可确认的本地位置；已识别且在线的远程来源允许自动扫描，但每轮必须复核身份、权限和文件稳定性；`unknown` 来源以及远程/未知的本地必需目录继续只允许人工或直接阻断。

readiness 的 `capabilities` 同时区分物理读写与产品操作上限。来源、回收、日志和缓存可在各自安全边界内处理可证明归属的对象；目标片库即使物理可写也固定 `delete=false`，只允许读取和新增入库。POSIX ACL 无法单独表达“可新增但不可删除”，因此该禁令由任务、清理、重命名和冲突处理的业务白名单落实；逐项确认替换仍必须先把旧文件安全移入本地回收。

来源处置默认进入本地回收。用户按 ADR-0019 明确选择 `permanent_delete` 时，来源清理器和来源单元服务也不能直接删除原业务路径：它们必须先复核文件包提交、来源快照与挂载身份，再把精确成员同盘认领到来源根内任务专属 `.nas-media-delete-<unit-id>.deleting` 隔离区并落持久化账本，最后只删除该隔离区。目标片库、未知隐藏目录、符号链接、特殊文件和未被快照认领的内容不得进入这个入口。

来源单元历史重复覆盖由 `source_files/coverage.py` 提供，只在同一物理快照的相同来源路径已有成功提交时读取对应文件包证明。影片与已登记字幕须同时通过 SHA-256 与路径复核，保留意图和活动状态优先阻挡。协调器统一同步整组来源反馈、串行执行清理、拒绝复核期间任务状态变化并隔离单元访问异常；所有实际处置仍走原回收或隔离账本协议。

删除账本记录 `identity_mode` 与来源挂载稳定事实。本地模式使用 inode/device 并通过 dir-fd 删除；远程模式仅在 `inspect_mount()` 明确认定为 remote 时启用，跨 rename 不比较虚拟 inode，而比较挂载身份与文件树快照，并用隔离区限定的逐层路径删除兼容不支持 dir-fd 的 Provider。旧账本缺少模式字段时只允许按当前明确远程挂载推导；删除中断后允许快照子集续做，未知新增成员仍阻断。

写权限检查使用随机文件名和随机内容令牌。关闭描述符的 FUSE 异常不得终止 watcher；清理前必须以 `O_NOFOLLOW` 重新打开，复核单链接普通文件、当前目录项身份和令牌。无法证明归属时保留并报错，禁止通配删除历史 `.write_test_*`。

目录角色拓扑由 `features/configuration/storage_topology.py` 统一判断。所有操作目录和片库根必须互不包含；启动清理与通用任务文件动作还会再次确认真实路径归属并拒绝符号链接。目标片库不能被伪装成来源清理目录，也不能通过任务删除或通用重命名改变。

目标侧校验复制与文件包提交实现位于 `media_importer/features/import_flow/services/file_operations.py`；路径校验、安全移动/删除、权限检查和文件指纹基础能力位于 `media_importer/infrastructure/filesystem/safety.py`。中心 `FileCopier` 已删除，禁止重新引入来源到中心中转步骤。

分类规则和模板渲染是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/classification_rules.py`。

同作品/同名目标检测和重命名建议是入库业务策略，真实实现位于 `media_importer/features/import_flow/services/dedup_rules.py` 与 `services/dedup.py`。检测只扫描本任务实际入库目录并零写入；旧质量比较只保留为兼容代码，不再自动决定片库文件去留。

用户确认替换时，新文件先在目标侧以唯一 `.replacement.tmp` 完整复制和 SHA-256 校验；随后以唯一临时名认领现有文件并再次核对确认时的 SHA-256，校验通过才进入本地回收区，最后以 no-replace 协议发布。回收失败恢复旧文件；并发出现新目标时不覆盖该目标，旧文件保留在回收区；永不调用永久删除作为兜底。

新作品的视频和字幕按同一文件包提交：所有成员具有任务稳定成员信息和 SHA-256，目标暂存名绑定 `task_id`，字幕先发布，视频最后发布。视频发布前失败只回退本任务且指纹吻合的成员；视频发布后恢复逻辑只能核验并修复数据库，不得删除片库结果。当前带字幕作品不支持覆盖既有作品；在整包替换事务完成前，冲突处理必须拒绝 `replace_existing`。

关联重新整理任务复用同一文件包协议，来源是父任务记录的现存片库影片和字幕，允许在当前启用片库根之间移动。规则型目标来自分类规则；人工型目标来自 root ID + 安全相对子目录并保持当前文件名。它不经过中转目录、来源清理或覆盖入口；提交前中断退回原片库位置，提交后中断只补齐父子任务、当前路径和字幕状态。任何目标同名都以 no-replace 失败关闭并保留双方。

源目录扫描和任务感知过滤真实实现位于 `media_importer/features/import_flow/scan_service.py`。

文件名模板和字幕命名规则真实实现位于 `media_importer/features/import_flow/services/naming.py`。入库移动真实实现位于 `media_importer/features/import_flow/services/file_operations.py`。源文件安全删除、伴生文件识别、非媒体源文件清理和空父目录清理真实实现位于 `media_importer/features/source_files/`。
