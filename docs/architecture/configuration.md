# Configuration Architecture

## Current Pattern

- 配置格式：YAML。
- 加载入口：`media_importer/core/config_loader.py`。
- 自动迁移：`media_importer/core/config_migrations.py`。
- 校验入口：`media_importer/core/config_validator.py`。
- 前端配置 API：`media_importer/api/config_handlers.py`。

## Change Rule

新增配置项必须同步：

```text
config.yaml.example
-> config_loader
-> config_migrations
-> config_validator
-> config_handlers
-> webui
-> docs
-> tests
```

## Direction

后续会新增 `ConfigView` facade，减少业务层直接读取深层 `config.get(...)`。
