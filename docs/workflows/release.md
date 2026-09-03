# Release Workflow

1. 确认工作树干净。
2. 跑必要测试。
3. 确认本地开发环境与 `.python-version` 一致；fnOS package 必须声明并使用官方 `python312` 依赖。
4. 检查配置示例和迁移。
5. 检查文档入口和接口规范。
6. 先运行 `python scripts/release_ledger.py status` 查询当前开发版本、最近候选包和最近 fnOS 验收正常版本。每个新候选必须先提升根 `VERSION`；版本允许跳号但必须严格高于最近候选。禁止用命令参数临时制造另一个版本事实。
7. 运行 `./deploy/build_fpk.sh` 从根源码重建。脚本必须在下载构建依赖前执行台账门禁：同版本仅允许源码指纹一致的确定性重建；同版本不同源码、降版或无效台账直接失败。
8. 确认 `scripts/validate_fpk.py` 通过，manifest 与包内 `server/VERSION` 一致，`build/*.fpk.sha256` 与产物匹配；构建成功后 `deploy/release-ledger.json` 必须登记候选版本、源码指纹和产物哈希。不得把缓存、数据库、日志或本机配置打入包内。
9. 不手动修改 `deploy/nas-media-importer/app/server/media_importer/`。
10. 确认 FPK 内 `requirements-fnos.lock` 与 wheelhouse 完整，安装/升级脚本只使用 `--no-index`；wheel 必须全部为 `py3-none-any` 才能声明 `platform=all`。
11. 分开记录 `LOCAL_BUILD` 与 `FNOS_UAT`：本地构建通过只产生 `candidate`，不等于真实设备安装通过。真机至少验收官方 Python 依赖、首次 Web 目录授权、多片库、外部挂载异常、离线项目依赖、桌面入口和服务启动。升级或保留数据重装还必须确认托管设置已迁移、用户目录未覆盖、桌面 CGI 不返回 502/401。
12. 用户明确确认真机验收后，执行 `python scripts/release_ledger.py mark-verified --version <版本> --note "<验收摘要>"`；未登记时 `status` 必须显示“最近 fnOS 验收正常版本：暂无”，不得把候选包倒推为正常版本。
13. 记录版本变更和已知问题，并把 `VERSION` 与 `deploy/release-ledger.json` 随发布代码提交。
