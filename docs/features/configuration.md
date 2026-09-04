# Configuration Feature

配置能力负责加载 YAML、执行迁移、校验、脱敏、保存和向 API/frontend 提供稳定配置视图。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/configuration/__init__.py` | Feature public API for config loading, validation, masking, and `ConfigView`. |
| `media_importer/features/configuration/application_service.py` | UI payload shaping, section-save splitting, permission/path payload assembly, and watcher status projection. |
| `media_importer/features/configuration/runtime_service.py` | Runtime refresh service for pipeline config, scraper, notifier, and file watcher after config reload. |
| `media_importer/features/configuration/storage_readiness.py` | Role-aware path, mount identity, permission and capacity readiness projection. |
| `media_importer/features/configuration/storage_topology.py` | 目录角色真实路径互斥、片库归属与运行时副作用门禁。 |
| `media_importer/features/configuration/library_paths.py` | `library_root` 迁移、相对规则与运行时 containment。 |
| `media_importer/features/configuration/fnos_directory_access.py` | 通过 fnOS Unix socket 查询应用已授权共享目录；token 不持久化、不出后端。 |
| `media_importer/features/configuration/startup_readiness.py` | 目录、规则目标片库、TMDB、按需 LLM 和自动运行的最终配置检查。 |
| `media_importer/core/config_loader.py` | Load YAML config and defaults. |
| `media_importer/core/config_validator.py` | Validate config shape and values. |
| `media_importer/core/config_view.py` | Read-only config facade and safe frontend projection. |
| `media_importer/api/config_handlers.py` | Config HTTP handlers. |
| `config/config.yaml` | Runtime config example/default file. |

## Current Consumers

- App/API entrypoints import load, validation, masking, and `ConfigView` through `media_importer.features.configuration`.
- Config API handlers now call feature application helpers for UI config payloads, section updates, permission checks, path tests, and watcher status payloads.
- Config reload now calls configuration runtime helpers for pipeline/notifier/watcher refresh instead of constructing those components in the API handler.
- Config API payload includes a revision, fnOS directory-authorization capability and server-computed storage readiness. On fnOS, user-selected source/library/recycle/temp/log/resource paths reject values outside current authorized roots; unrelated settings can still be repaired independently. Saves reject stale revisions, validate the merged full document, `fsync` a same-directory temporary file, then publish with `os.replace`.
- The first-run UI never infers readiness from non-empty inputs. It displays backend `READY/BLOCKED` and location-level health facts.
- `source_policy.mode` 是来源处理三态事实源；旧布尔字段只作迁移输入。
- `library_roots[]` 是用户创建的多片库事实源，数量为 0～N；存储检查可先独立保存这些目录。每条规则必须显式保存一个存在且启用的 `library_root_id` 和相对模板，非空 fallback 同样必须显式选择 root ID。缺少引用或引用失效可作为配置中的待完成状态保留，但规则保存、配置检查和正式运行全部阻断；未被任何规则使用的片库合法。旧 `library_root` 可迁移为 `default` 根，但默认根只作兼容和界面标识，禁止作为规则缺省归属。旧绝对路径只作人工设置参考；系统不得按片库添加顺序、默认根或路径包含关系静默分配。
- `duplicate_handling` 运行合同固定为 `enabled=true, strategy=confirm`。旧自动策略只作读取兼容，保存入库选项时统一归一化，不能恢复自动替换。
- `task_queue.max_concurrent` 只允许整数 `1` 或 `2`，默认与普通 NAS 推荐值均为 `1`。高级配置保存由后端严格拒绝布尔、字符串、零、负数和超限值；历史 YAML 或手工改写的异常值在运行时仍保守钳制到 `1..2`，不能绕过实际任务门禁。
- “存储检查”是所有目录的唯一编辑入口：来源、回收、日志、海报缓存和任意数量片库均在同一清单完成选择、授权、读写与容量检查。它不展示、编辑或跳转入库规则；规则只在片库整理中配置，并由完成页“配置检查”统一验收。成功选择或重新绑定后保存 `realpath/st_dev/mount_source` 身份快照，运行时发现挂载变化会暂停副作用并要求重新绑定。来源页只保留扫描和处理策略，进阶系统页不再编辑目录。非 fnOS 开发环境才可手填。
- 所有目录角色必须真实路径互斥；相同目录、父子嵌套和符号链接别名均显示为阻断项。保存与运行时使用同一拓扑事实，系统不自动迁移或删除冲突目录中的任何文件。
- 授权回调同时支持 opener 消息与同源、短时、一次性的 `localStorage` 结果桥接，覆盖 fnOS 移动端打开新标签的场景；回调 state、应用名与过期时间不匹配时拒绝。授权事实明确为“当前路径需要授权且尚未授权”时，存储卡必须显示“重新授权”并直接对当前路径发起授权；授权正常后才显示“更改位置”并进入重新选择目录流程。授权成功后前端立即显示持续等待态，以有界递增间隔确认 fnOS 权限可见，再统一重新加载配置与 storage readiness；已有目录重新授权也必须自动刷新，超时或读取失败后恢复按钮并保留手工“重新检查”入口。
- 配置页只有一条胶卷轨道；`进阶设置` 是与基础步骤同级的 stage，命名、维度和系统设置在该 stage 原位展开，不再进入独立高级首页。服务 API Key 与端口由 fnOS 默认托管，不在普通配置界面暴露；后端/YAML 兼容能力保留。
- `file_watcher.poll_interval` 默认 300 秒（5 分钟），在自动运行基础页以 30/60/120/300/600 秒预设展示，保存后通过 runtime refresh 重建 watcher；后端接受 10–3600 秒并由 watcher 防御性截断。升级保留用户已经显式保存的周期。已识别且在线的远程来源允许自动扫描，黄色提示不等于阻断；`automatic_allowed` 由各位置的 `capabilities.automatic` 聚合，未知来源、本地必需目录异常、挂载身份变化和空间门禁仍阻止启动。
- Storage readiness 具有四种明确作用域：完成页“配置检查”检查全部目录与规则；watcher 空闲轮询只读检查来源；发现稳定候选后检查来源、回收、日志和缓存；分类后按 `import_path` 只检查唯一命中的目标片库。作用域缩小只用于延迟不相关磁盘访问，真正文件操作前的实时挂载、授权、容量和写入门禁不缓存、不省略；无法唯一归属片库时失败关闭。
- 规则编辑、详细删除规则和 LLM 配置弹窗禁止点击遮罩关闭，避免误丢未保存编辑。规则编辑弹窗在入库路径模板下提供默认折叠的变量助手，展开后显示后端已支持的核心变量按钮，并按当前启用维度动态提供 `{dimension.<name>}`；点击在当前光标或选区插入。常用变量包含 `{resolution}`，路径渲染时优先使用现有同名字段，否则读取 ffprobe 文件分析产生的 `dimensions.resolution_tier`。路径输入框禁止保留开头 `/`，键入或粘贴时立即移除并提示用户路径已经从所选片库开始；保存层仍拒绝绝对路径和 `..`。
- LLM 连通性测试在配置弹窗内显示测试中、成功或失败与服务端原因；自动运行在用户界面统一称为“后台自动整理”。
- 配置检查 API 保留内部 `/startup-readiness` 路径及 `PASS/WARN/BLOCKED/SKIPPED` 合同，前端分别显示“正常/需要留意/需要处理/无需检查”，不得直接暴露英文状态码。规则项同时验证显式片库绑定以及被引用目标的目录读写能力；规则错误指向片库整理，目录能力错误指向存储检查。自动运行项同时检查配置意图、`automatic_allowed` 与当前服务内 watcher 线程，禁止仅因 YAML 中 `enabled=true` 就报告 PASS。
- 配置检查还验证每个已启用 Provider 维度的映射版本、operator、目标值和未命中策略。旧规则若使用 `restricted_level=17+`，检查页显示“现在只表示限制观看”的 WARN，不自动更换维度、片库或路径。
- 文件来源页内的“忽略明显广告和小视频片段”默认折叠并开启；小视频上限、主视频下限、体积比例和附加名称规则保存到 `media_candidate_filter`。旧 `source_cleaner.junk_video_max_size_mb` 仅作为迁移回退，前端不再展示第二套阈值。
- “模拟识别与分类”属于片库搭建的独立验证工具，不得出现已退役的高级配置首页或返回路径。
- 配置检查传输失败必须在完成页内保留失败原因和重新检查入口；TMDB/LLM 不可用仍由 API 返回逐项检查结果。
- Scraping/provider implementations and storage scanner use `ConfigView` through the configuration feature entry, not direct `core.config_view` imports.
- Low-level `core/config_*` files remain implementation details until they are moved into feature-owned or infrastructure modules.

## Related Areas

- Frontend: `media_importer/webui/js/cinema-config.js`.
- Security: sensitive keys returned to frontend must be masked as `***`；递归覆盖旧配置和扩展块内的 `api_key`、`*_key`、`secret`、`*_secret`、`*_token` 与 password 字段。
- Tests: config loader, migration, validator, API, and UI config flows.

## Migration Notes

- New app/API/feature code should import from `media_importer.features.configuration`.
- Keep low-level YAML and file IO helpers in infrastructure if shared.
- Each new config item must document default, migration behavior, validation rule, API exposure, and UI ownership.
- User-selected roots are validation-only and are never auto-created by config save or path checks. Application-owned child directories may be created only below an existing, verified root.
- A disabled root cannot remain the default or be referenced by a rule/fallback. Referenced roots must be migrated before disabling or removal.
