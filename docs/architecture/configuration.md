# Configuration Architecture

## Current Pattern

- 配置格式：YAML。
- 加载入口：`media_importer/core/config_loader.py`。
- 自动迁移：`media_importer/core/config_migrations.py`。
- 校验入口：`media_importer/core/config_validator.py`。
- 前端配置 API：`media_importer/api/config_handlers.py`。
- 业务读取门面：`media_importer/core/config_view.py`。

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

`ConfigView` 是业务层读取配置的稳定入口，保留 `raw` 原始 dict 兼容旧代码，同时提供 typed sections：

- `paths`
- `source_policy`
- `dedup`
- `filename_templates`
- `manual_review`
- `metadata`
- `llm`
- `scanner`
- `source_cleaner`

新增配置项时，loader/migration/validator 仍负责配置文件生命周期；业务代码优先通过 `ConfigView` 读取，避免散落深层 `config.get(...)`。
