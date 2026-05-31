# Configuration Standards

## Change Chain

新增或修改配置项必须检查：

```text
config.yaml.example
core/config_loader.py
core/config_migrations.py
core/config_validator.py
api/config_handlers.py
webui/js/config.js
webui/index.html
docs
tests
```

## Sensitive Data

返回前端的 `api_key`、`secret` 等敏感字段必须脱敏为 `***`。

## Direction

后续会引入 `ConfigView` facade，减少业务代码直接读取深层 dict。
