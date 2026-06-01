# Module: Core

## Code

- `media_importer/core/config_loader.py`
- `media_importer/core/config_view.py`
- `media_importer/core/config_migrations.py`
- `media_importer/core/config_validator.py`
- `media_importer/core/task_manager.py`
- `media_importer/core/task_lifecycle.py`
- `media_importer/core/safety.py`
- `media_importer/core/logger.py`
- `media_importer/core/metrics.py`

## Responsibility

核心基础设施：配置、任务管理、路径安全、日志、指标等。

`config_view.py` 负责业务层配置读取门面，减少深层 `config.get(...)` 扇出。

`task_lifecycle.py` 负责集中任务状态和文件位置转换规则。

## Rule

`core` 不应依赖 `api`、`pipeline`、`webui`。

## Related Docs

- [../architecture/configuration.md](../architecture/configuration.md)
- [../architecture/task-lifecycle.md](../architecture/task-lifecycle.md)
- [../standards/safety.md](../standards/safety.md)
