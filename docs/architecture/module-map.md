# Module Map

## Dependency Direction

```text
api / media_importer.py / monitor
        |
        v
pipeline
        |
        v
scraper + storage + notify
        |
        v
core
```

Rules:

- `core` 不应依赖 `pipeline`、`api`、`webui`。
- `api` 和 `pipeline` 是编排层，可以依赖多个业务模块。
- `scraper` 和 `storage` 尽量保持互相低耦合。
- `webui` 只通过 HTTP API 与后端交互。
- 未来 `domains/` 目录只能通过兼容 proof slice 渐进引入，不一次性移动现有 public imports。

## Documentation Mapping

模块文档在 [../modules/](../modules/)；代码和文档索引在 [../INDEX.md](../INDEX.md)。
