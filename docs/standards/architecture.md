# Architecture Standards

## Layer Rules

- `api` 是入口层，负责 HTTP、鉴权、请求解析和响应，不承载复杂业务策略。
- `pipeline` 是编排层，长期目标是调用 services，而不是直接处理所有策略。
- `scraper` 负责元数据和 AI/Provider 相关逻辑。
- `storage` 负责文件系统和入库相关能力。
- `core` 负责基础设施和跨域模型，不依赖上层模块。
- `webui` 只通过 HTTP API 与后端交互。

## Architecture Change Rule

以下变更必须新增或更新 ADR：

- 改变模块依赖方向；
- 引入新框架或外部服务；
- 改变任务状态模型；
- 改变文件删除/回收站策略；
- 改变配置格式或迁移机制；
- 大规模目录重组。
