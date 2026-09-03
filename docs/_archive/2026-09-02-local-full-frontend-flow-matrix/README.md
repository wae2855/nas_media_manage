# 本地真实前端文件全流程矩阵归档

- Requirement: `REQ-20260902-180900`
- Date: 2026-09-02
- Status: 本地实现与工程验收完成，等待用户复核和 fnOS 真机验收
- Basis: F01-F12 共 12/12 真实 Chromium 场景、72 项文件安全专项、1001 项全量测试通过
- Evidence: `output/full-frontend-flow-matrix/20260902T205532/`
- F12: 浏览器触发正式复制，父进程在 64 MiB 文件复制至 1 MiB 时对精确服务 PID 发送 SIGKILL；同配置/数据库重启后清理临时文件，并从前端重试成功

本目录保留已完成的方案与实施记录。持续回归入口为
`tests/test_full_frontend_flow_matrix_browser_ui.py`，文件流的当前事实以
`docs/testing/file-flow-matrix.md`、`docs/features/import-flow.md` 和
`docs/standards/safety.md` 为准。
