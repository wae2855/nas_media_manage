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

domains compatibility entries -> pipeline + core + storage
domains/recycle -> core/safety compatibility facade
```

Rules:

- `core` 不应依赖 `pipeline`、`api`、`webui`。
- `api` 和 `pipeline` 是编排层，可以依赖多个业务模块。
- `scraper` 和 `storage` 尽量保持互相低耦合。
- `webui` 只通过 HTTP API 与后端交互。
- 未来 `domains/` 目录只能通过兼容 proof slice 渐进引入，不一次性移动现有 public imports。
- `domains/` 当前只作为业务域导航与兼容入口，不能复制业务实现。
- `domains/source_cleaning/` 已持有源目录清理实现，旧 `storage/source_cleaner.py` 是兼容别名。
- `domains/recycle/` 已持有回收站实现，旧 `core/recycle/*` 和 `core/safety.py` 保持兼容。

## Documentation Mapping

模块文档在 [../modules/](../modules/)；代码和文档索引在 [../INDEX.md](../INDEX.md)。
