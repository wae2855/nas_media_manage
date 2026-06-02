# Architecture Standards

## Layer Rules

- `api` 是入口层，负责 HTTP、鉴权、请求解析和响应，不承载复杂业务策略。
- `features` 是业务事实源；新增或重构业务优先按 feature 边界落地。
- `features/import_flow` 是入库流程编排层，调用 services，不直接承载所有策略。
- `infrastructure` 承载 SQLite、文件系统、外部 client、logger、metrics 等可复用基础设施。
- `core` 是历史基础设施实现目录；新增业务不应直接扩展 `core`，应优先放入 feature 或 infrastructure。
- `storage` 是历史文件处理实现目录；文件系统原子能力可保留为 infrastructure，分类/去重/命名等业务策略应迁入 feature service。
- `scraper` 是历史刮削实现目录；scraping/provider/prompt 新入口和后续迁移目标在 `features/scraping`、`features/providers`、`features/prompts`。
- `monitor` 和 `notify` 是历史周边实现目录；后续应并入 notification/monitoring feature 或 infrastructure adapter。
- `webui` 只通过 HTTP API 与后端交互。

## Dependency Rules

- `api`、CLI、watcher 可以调用 `features`，不应直接承载业务策略。
- `features` 可以调用 infrastructure/shared，也可以在迁移期调用旧实现目录；新增调用应优先走 feature public API。
- 旧实现目录不得新增面向上层的 public 事实入口；需要公开能力时先放入对应 feature。
- feature 不应依赖已归档目录或旧 wrapper。

## Architecture Change Rule

以下变更必须新增或更新 ADR：

- 改变模块依赖方向；
- 引入新框架或外部服务；
- 改变任务状态模型；
- 改变文件删除/回收站策略；
- 改变配置格式或迁移机制；
- 大规模目录重组。
