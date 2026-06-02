# Configuration Feature

配置能力负责加载 YAML、执行迁移、校验、脱敏、保存和向 API/frontend 提供稳定配置视图。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/core/config_loader.py` | Load YAML config and defaults. |
| `media_importer/core/config_migrations.py` | Apply config migrations. |
| `media_importer/core/config_validator.py` | Validate config shape and values. |
| `media_importer/core/config_view.py` | Read-only config facade and safe frontend projection. |
| `media_importer/api/config_handlers.py` | Config HTTP handlers. |
| `config/config.yaml` | Runtime config example/default file. |

## Related Areas

- Frontend: `media_importer/webui/js/config.js`.
- Security: sensitive keys returned to frontend must be masked as `***`.
- Tests: config loader, migration, validator, API, and UI config flows.

## Target Shape

- Move feature-owned config behavior into `features/configuration/`.
- Keep low-level YAML and file IO helpers in infrastructure if shared.
- Each new config item must document default, migration behavior, validation rule, API exposure, and UI ownership.
