# Configuration Feature

配置能力负责加载 YAML、执行迁移、校验、脱敏、保存和向 API/frontend 提供稳定配置视图。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/configuration/__init__.py` | Feature public API for config loading, validation, masking, and `ConfigView`. |
| `media_importer/core/config_loader.py` | Load YAML config and defaults. |
| `media_importer/core/config_migrations.py` | Apply config migrations. |
| `media_importer/core/config_validator.py` | Validate config shape and values. |
| `media_importer/core/config_view.py` | Read-only config facade and safe frontend projection. |
| `media_importer/api/config_handlers.py` | Config HTTP handlers. |
| `config/config.yaml` | Runtime config example/default file. |

## Current Consumers

- App/API entrypoints import load, validation, masking, and `ConfigView` through `media_importer.features.configuration`.
- Scraping/provider implementations and storage scanner use `ConfigView` through the configuration feature entry, not direct `core.config_view` imports.
- Low-level `core/config_*` files remain implementation details until they are moved into feature-owned or infrastructure modules.

## Related Areas

- Frontend: `media_importer/webui/js/config.js`.
- Security: sensitive keys returned to frontend must be masked as `***`.
- Tests: config loader, migration, validator, API, and UI config flows.

## Migration Notes

- New app/API/feature code should import from `media_importer.features.configuration`.
- Keep low-level YAML and file IO helpers in infrastructure if shared.
- Each new config item must document default, migration behavior, validation rule, API exposure, and UI ownership.
