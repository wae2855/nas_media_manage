# Configuration Architecture

## Current Pattern

- 配置格式：YAML。
- 业务入口：`media_importer/features/configuration/`。
- 应用层辅助：`media_importer/features/configuration/application_service.py`。
- 运行时刷新：`media_importer/features/configuration/runtime_service.py`。
- 加载实现：`media_importer/core/config_loader.py`。
- 自动迁移：`media_importer/core/config_migrations.py`。
- 校验入口：`media_importer/core/config_validator.py`。
- 前端配置 API：`media_importer/api/config_handlers.py`。
- 业务读取门面：`media_importer.features.configuration.ConfigView`，实现位于 `media_importer/core/config_view.py`。

## Change Rule

新增配置项必须同步：

```text
config.yaml.example
-> config_loader
-> config_migrations
-> config_validator
-> config_view
-> config_handlers
-> webui
-> docs
-> tests
```

## ConfigView

`ConfigView` 是业务层读取配置的稳定入口。业务代码从 `media_importer.features.configuration` 导入它；底层实现文件保留在 `core/config_view.py`。它保留 `raw` 原始 dict 兼容旧代码，同时提供 typed sections：

- `paths`
- `source_policy`
- `dedup`
- `filename_templates`
- `manual_review`
- `metadata`
- `matching`
- `llm`
- `scanner`
- `source_cleaner`

新增配置项时，loader/migration/validator 仍负责配置文件生命周期；业务代码优先通过 `ConfigView` 读取，避免散落深层 `config.get(...)`。

规范字段：

- `source_policy.mode`: `preserve_all | preserve_media | recycle_source_unit`；旧 `cleanup_source_after_done` 只作迁移输入和兼容投影。
- `source_policy.disposal_mode`: `local_recycle | permanent_delete`；只在 `preserve_media/recycle_source_unit` 下生效，缺失或旧配置默认 `local_recycle`。切换到 `permanent_delete` 的保存请求必须携带本次不可恢复确认，但确认标记不写入持久配置。
- `library_roots[]`: 多个已授权片库根，字段为稳定 `id/name/path/enabled`；ID 与规范路径都必须唯一。
- `default_library_root_id`: 普通规则和旧配置迁移使用的默认根；`library_root` 只保留为旧读取兼容投影。
- `path_rules[].library_root_id + template`: 每条规则明确绑定一个启用根和其下相对模板。
- `fallback_library_root_id + fallback_dir`: 兜底目标同样显式绑定根。保存与运行时均做 containment 校验。

旧单根 `library_root` 可迁移为 `default` 根，但不能把默认根当作规则归属。没有根、只有绝对规则的旧配置先允许独立保存用户选择的 `library_roots`；随后用户必须在片库整理中为每条规则和非空兜底目录显式选择一个真实、启用的 root ID。旧绝对路径只作参考，用户主动选根后才能转换为该根下的相对模板。服务端不得按添加顺序、默认片库、规则序号或路径包含关系替用户分配；规则未选根、引用未知/停用根或模板越界时，规则保存、配置检查与运行路径均失败关闭并返回规则序号及名称。反向不要求每个片库都被规则引用，备用或暂未使用的片库合法。

`storage_topology.py` 是目录角色互斥的单一事实源。来源、回收、日志、资源缓存和所有启用片库根先规范化为真实路径；任意两者相同或互为父子都产生 `dir_conflict`，配置保存、storage/startup readiness 和文件副作用入口共同阻断，YAML 也不能绕过。

## fnOS 目录授权事实

配置中的路径不代表 fnOS ACL。托管运行时由 `fnos_directory_access.py` 通过开放 API 查询当前应用授权根；用户选择的来源、启用片库根、回收、日志和资源目录保存时执行规范化 `commonpath` containment，并把当时的 `realpath/st_dev/mount_source` 写入 `storage_identities`。`${TRIM_PKGVAR}` / 本应用 `@appdata` 下的日志和资源等私有目录由 fnOS 随包创建和授权，不进入共享目录选择器，readiness 直接实测当前应用进程的存在性与读写能力；只有外部共享目录才要求开放 API 授权根。`st_dev` 只作诊断展示，因为同一磁盘在重启或重装后可能被内核重新编号；绑定判断使用 `realpath + mount_source + mount_point + filesystem_type`。真正的挂载来源变化仍保持 BLOCKED 并要求重新绑定。卸载重装后保留的外部路径若 ACL 已清空，逐项显示“需要重新授权”；私有默认路径则自动跟随当前 `${TRIM_PKGVAR}` 并校验。非 fnOS 本地开发不强制 ACL 层，但仍执行文件系统校验。

全新 fnOS 初始化将来源、回收和 `library_roots` 置空，同时清除模板规则的根 ID 绑定并关闭后台自动整理；日志和资源缓存使用应用私有默认目录。Web 配置按“来源 1 + 目标 0～N + 回收 1 + 系统目录”返回独立 location 记录，“存储检查”是唯一目录编辑面且只显示目录事实，不展示规则列表或迁移跳转。配置检查聚合 storage readiness 与规则片库绑定，readiness 不从规则猜出目标目录，只有显式开启后台自动整理时才要求整套存储全部为绿色。

重复处理配置固定归一化为 `duplicate_handling.enabled=true / strategy=confirm`。旧 `skip/rename/replace/quality` 值可以读入，但运行时不会产生自动片库写操作；配置界面只展示“冲突时等待确认”的安全说明。

任务并发配置 `task_queue.max_concurrent` 的产品边界固定为 `1..2`，缺失默认 `1`。分区保存和全量配置校验都拒绝非整数及超限值；import-flow 运行时再次钳制历史或手工异常值，保证配置文件绕过界面时也不会产生超过 2 个并发文件任务。

当前 `config_handlers.py` 中的 UI 配置投影、分区保存拆分、权限检查请求组装、路径测试结果组装和 watcher 状态投影已下沉到 configuration feature application service；配置重载后的 pipeline/notifier/watcher 刷新已下沉到 runtime service。API handler 仍保留全局对象引用赋值，后续如新增 application state 容器再继续收口。
