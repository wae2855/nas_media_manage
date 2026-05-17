# _deprecated

本目录存放已弃用的文件，仅作参考保留，待审阅后删除。

## 内容说明

| 文件/目录 | 说明 | 弃用原因 |
|---|---|---|
| `tests/` | 旧测试目录（含 unit、integration、fixtures） | 未使用，当前项目使用 `restart_for_test.sh` 进行测试 |
| `init_test_env.sh` | 旧测试环境初始化脚本 | 已被 `restart_for_test.sh` 替代 |
| `dot_trae/` | 原 `.trae/` 目录，含早期规格文档 | 规格文档严重过时，与当前实现不符 |
| `04-tasks.md` | 旧任务跟踪文档 | 所有任务标记为未完成，但实际已完成，文档已过时 |
