# Configuration Feature

配置能力负责加载 YAML、执行迁移、校验、脱敏、保存和向 API/frontend 提供稳定配置视图。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/configuration/__init__.py` | Feature public API for config loading, validation, masking, and `ConfigView`. |
| `media_importer/features/configuration/application_service.py` | UI payload shaping, section-save splitting, permission/path payload assembly, and watcher status projection. |
| `media_importer/features/configuration/runtime_service.py` | Runtime refresh service for pipeline config, scraper, copier, Hermes notifier, and file watcher after config reload. |
| `media_importer/features/configuration/storage_readiness.py` | Role-aware path, mount identity, permission and capacity readiness projection. |
| `media_importer/features/configuration/storage_topology.py` | 目录角色真实路径互斥、片库归属与运行时副作用门禁。 |
| `media_importer/features/configuration/directory_changes.py` | 中转目录切换门禁；拒绝运行任务、可恢复任务或非空旧中转目录。 |
| `media_importer/features/configuration/library_paths.py` | `library_root` 迁移、相对规则与运行时 containment。 |
| `media_importer/features/configuration/fnos_directory_access.py` | 通过 fnOS Unix socket 查询应用已授权共享目录；token 不持久化、不出后端。 |
| `media_importer/features/configuration/startup_readiness.py` | 目录、片库边界、TMDB、按需 LLM 和自动运行的最终开场检查。 |
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
- `library_roots[]` 是用户创建的多片库事实源，数量为 0～N；规则和 fallback 保存稳定 root ID + 相对模板。旧 `library_root` 可自动迁移为 `default` 根；只有绝对规则而没有根时必须由用户选根并显式确认，禁止从规则静默推断。
- `duplicate_handling` 运行合同固定为 `enabled=true, strategy=confirm`。旧自动策略只作读取兼容，保存入库选项时统一归一化，不能恢复自动替换。
- “存储检查”是所有目录的唯一编辑入口：来源、中转、回收、日志、海报缓存和任意数量片库均在同一清单完成选择、授权、读写与容量检查。成功选择或重新绑定后保存 `realpath/st_dev/mount_source` 身份快照，运行时发现挂载变化会暂停副作用并要求重新绑定。来源页只保留扫描和处理策略，进阶系统页不再编辑目录。中转切换要求无运行/可恢复任务且旧目录为空；系统不会搬移或删除旧中转文件。非 fnOS 开发环境才可手填。
- 所有目录角色必须真实路径互斥；相同目录、父子嵌套和符号链接别名均显示为阻断项。保存与运行时使用同一拓扑事实，系统不自动迁移或删除冲突目录中的任何文件。
- 授权回调同时支持 opener 消息与同源、短时、一次性的 `localStorage` 结果桥接，覆盖 fnOS 移动端打开新标签的场景；回调 state、应用名与过期时间不匹配时拒绝。
- 配置页只有一条胶卷轨道；`进阶设置` 是与基础步骤同级的 stage，命名、维度和系统设置在该 stage 原位展开，不再进入独立高级首页。服务 API Key 与端口由 fnOS 默认托管，不在普通配置界面暴露；后端/YAML 兼容能力保留。
- `file_watcher.poll_interval` 在自动运行基础页以 30/60/120/300/600 秒预设展示，保存后通过 runtime refresh 重建 watcher；后端接受 10–3600 秒并由 watcher 防御性截断。
- 规则编辑、详细删除规则和 LLM 配置弹窗禁止点击遮罩关闭，避免误丢未保存编辑。
- LLM 连通性测试在配置弹窗内显示测试中、成功或失败与服务端原因；自动运行在用户界面统一称为“后台自动整理”。
- 开场检查 API 保留 `PASS/WARN/BLOCKED/SKIPPED` 合同，前端分别显示“正常/需要留意/需要处理/无需检查”，不得直接暴露英文状态码。
- “模拟识别与分类”属于片库搭建的独立验证工具，不得出现已退役的高级配置首页或返回路径。
- 开场检查传输失败必须在完成页内保留失败原因和重新检查入口；TMDB/LLM 不可用仍由 API 返回逐项检查结果。
- Scraping/provider implementations and storage scanner use `ConfigView` through the configuration feature entry, not direct `core.config_view` imports.
- Low-level `core/config_*` files remain implementation details until they are moved into feature-owned or infrastructure modules.

## Related Areas

- Frontend: `media_importer/webui/js/cinema-config.js`.
- Security: sensitive keys returned to frontend must be masked as `***`.
- Tests: config loader, migration, validator, API, and UI config flows.

## Migration Notes

- New app/API/feature code should import from `media_importer.features.configuration`.
- Keep low-level YAML and file IO helpers in infrastructure if shared.
- Each new config item must document default, migration behavior, validation rule, API exposure, and UI ownership.
- User-selected roots are validation-only and are never auto-created by config save or path checks. Application-owned child directories may be created only below an existing, verified root.
- A disabled root cannot remain the default or be referenced by a rule/fallback. Referenced roots must be migrated before disabling or removal.
