# fnOS Deployment

## Current Pattern

项目运行在飞牛 fnOS NAS 环境，使用 Python 服务和原生 Web UI。

当前仓库默认开发版本已升级到 Python 3.12.x，本地开发通过根目录 `.python-version` 和项目 `.venv/` 隔离全局解释器。
fnOS 发布由 `deploy/build_fpk.sh` 生成 FPK。manifest 声明官方 `python312` 依赖，应用优先使用 `/var/apps/python312/target/bin/python3`，并在 `${TRIM_PKGVAR}/venv` 创建可写、可持久化的独立环境。项目依赖在构建时锁定并下载为 `py3-none-any` wheel，安装/升级只从包内 wheelhouse 使用 `--no-index`，不会在设备上访问 pip 源。

根目录 `VERSION` 是当前开发/构建版本唯一事实源并必须纳入版本控制。`deploy/release-ledger.json` 保存历次候选包和 fnOS 验收事实：候选记录包含源码输入指纹与产物 SHA-256，真机验收必须显式标记。构建脚本从 `VERSION` 写入 manifest 和包内 `app/server/VERSION`，并在下载依赖前拒绝降版或同版本不同源码；同版本只允许相同指纹重建。产物校验器再次核对 manifest 与运行时版本。运行服务通过 `GET /api/health` 返回当前版本，页面在服务状态胶囊下显示真实值；`scripts/release_ledger.py status` 查询最近候选和最近正常版本。

## Install Configuration Ownership

首次安装向导只说明首次启动流程，不收集目录、服务 API Key 或端口。安装回调以固定端口 `14591`、空服务认证原子创建 `${TRIM_PKGVAR}/config/config.yaml`。安装、保留数据重装和升级遇到已有配置时，幂等迁移 fnOS 托管字段 `server.port=14591`、`server.api_key=""`，并让日志和资源缓存跟随当前 `${TRIM_PKGVAR}`；用户主动选择的外部目录保持原值并重新校验授权。来源、片库、回收、业务凭据和业务开关不得覆盖。来源、多个片库根和本地回收目录在首次 Web 启动通过 fnOS 共享目录授权能力选择，普通浏览器或平台能力不可用时可手填。后端仍保留 `server.api_key`、`server.port` 与 CLI/YAML 覆盖能力，但不在普通配置界面暴露。`14591` 位于 IANA 当前未分配的用户端口区间，避免与常见 NAS 服务端口及动态端口段混用。

安装脚本只创建 `${TRIM_PKGVAR}` 下的日志、资源缓存、数据和运行时临时目录，不自动创建外部业务目录。运行时临时目录不承载影片中转，也不对用户开放配置。应用私有目录由 fnOS 负责包级权限，界面标记“系统托管”并直接验证服务进程读写，不要求用户在共享目录选择器中寻找不可见的 `@appdata`。外部目录未配置时服务只用于完成配置；watcher、入库、清理和恢复受 readiness 阻塞。来源、各片库、回收及任何用户改到外部的日志/资源目录，其存在性、授权、读写能力、挂载状态、磁盘容量和本地性由 Web 配置检查验证。

manifest 设置 `micro_app=true`、最低系统 `1.2.0401`，`config/resource` 只声明 `trim.file.sharedAccess`。服务端每次调用从进程环境读取 `TRIM_API_TOKEN`，通过 `/var/run/trim_open_gateway_apiscope.socket` 查询授权目录，任何响应和日志都不得包含 token。

fnOS 桌面入口使用同源 CGI iframe。CGI 固定反向代理 `127.0.0.1:14591`，后端启动也只监听该回环地址；空服务认证不会暴露为 NAS 局域网直连端口。CGI 不得依赖 fnOS 环境未承诺提供的 `TRIM_PKGVAR` 或从旧配置猜测端口，应用启动与 CGI 上游共享同一托管端口契约。

因为应用固定监听 `14591`，manifest 必须声明 `checkport=true`，由 fnOS 在启动前识别端口冲突。维护者和发布者显示名统一为 `oneway`，联系地址统一指向公开 GitHub 仓库；对外邮箱写在 README，不增加未在官方 manifest 契约中的自定义字段。更新说明必须面向用户描述当前版本，禁止长期沿用“初始版本发布”。

桌面入口与后台服务生命周期相互独立：`cmd/main start` 将 Python 服务作为带 PID 文件的包服务启动，CGI 只转发 HTTP 请求。关闭 fnOS 桌面窗口或移动端页面不会调用 `cmd/main stop`，因此已启用的后台自动整理继续运行；只有用户停止/卸载应用或系统停止包服务时才终止进程。

## Important Rule

`deploy/nas-media-importer/` 是 fnOS package workspace，不是应用源码入口。

应用代码的唯一事实来源是根目录：

- `media_importer/`
- `config.yaml.example`
- `requirements.txt`
- `deploy/requirements-fnos.lock`

`deploy/build_fpk.sh` 会重建 `deploy/nas-media-importer/`，再把根源码复制到 `app/server/`。当前开发不手动同步 deploy 副本；发布时通过 build script 生成 package workspace 和 `.fpk`。

已跟踪的 `deploy/nas-media-importer/app/server/media_importer/` 可能滞后于根源码，不能作为架构事实或修改入口。

## Start Command

```bash
python3 -m media_importer.media_importer -c <config> serve -p <port> --host <host>
```

## Build Command

```bash
./deploy/build_fpk.sh
# 可选一致性断言；必须与根 VERSION 完全相同
./deploy/build_fpk.sh "$(tr -d '[:space:]' < VERSION)"
```

`fnpack` 或 wheel 不存在时脚本会下载构建依赖，因此该命令属于发布流程，不是日常重构验证命令。设备安装阶段不需要外网 pip。

构建脚本固定校验 fnpack 1.2.3，构建后运行 `scripts/validate_fpk.py` 检查真实包内容，并在 `build/` 生成 FPK 与 `.sha256`。该结果只能标记为 `LOCAL_BUILD PASS`，不能替代真实 fnOS 的安装、目录授权、依赖下载、CGI 和服务启动验收。

候选包成功生成后由构建脚本写入发布台账；只有用户明确完成真机验收后，才可用 `scripts/release_ledger.py mark-verified` 把该候选标记为正常版本。版本可跳号，但不能复用到不同源码。
