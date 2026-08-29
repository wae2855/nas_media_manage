# Release Workflow

1. 确认工作树干净。
2. 跑必要测试。
3. 确认本地开发环境与 `.python-version` 一致；fnOS package 必须声明并使用官方 `python312` 依赖。
4. 检查配置示例和迁移。
5. 检查文档入口和接口规范。
6. 如果发布 fnOS package，运行 `./deploy/build_fpk.sh <version>` 从根源码重建 `deploy/nas-media-importer/`。
7. 确认 `scripts/validate_fpk.py` 通过，`build/*.fpk.sha256` 与产物匹配；不得把缓存、数据库、日志或本机配置打入包内。
8. 不手动修改 `deploy/nas-media-importer/app/server/media_importer/`。
9. 分开记录 `LOCAL_BUILD` 与 `FNOS_UAT`：本地构建通过不等于真实设备安装通过。真机至少验收 Python 依赖、首次目录写入/升级保留、授权目录、外部挂载异常、依赖下载、桌面入口和服务启动。
10. 记录版本变更和已知问题。
