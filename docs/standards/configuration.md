# Configuration Standards

## Change Chain

新增或修改配置项必须检查：

```text
config.yaml.example
core/config_loader.py
core/config_migrations.py
core/config_validator.py
core/config_view.py
api/config_handlers.py
webui/js/config.js
webui/index.html
docs
tests
```

## Sensitive Data

返回前端的 `api_key`、`secret` 等敏感字段必须脱敏为 `***`。

## Business Access

业务代码优先通过 `ConfigView` 读取高频配置。

- pipeline services 不直接读取 `source_policy/path_rules/duplicate_handling/filename_templates/manual_review` 等深层 key。
- 新增配置项如果被业务层使用，必须同步 `ConfigView` 和默认值测试。
- loader/migration/validator 负责配置文件生命周期，`ConfigView` 负责运行期业务读取。
