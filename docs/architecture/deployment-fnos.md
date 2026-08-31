# fnOS Deployment

## Current Pattern

项目运行在飞牛 fnOS NAS 环境，使用 Python 服务和原生 Web UI。

当前仓库默认开发版本已升级到 Python 3.12.x，本地开发通过根目录 `.python-version` 和项目 `.venv/` 隔离全局解释器。
fnOS 发布由 `deploy/build_fpk.sh` 生成 FPK。manifest 声明官方 `python312` 依赖，应用优先使用 `/var/apps/python312/target/bin/python3`，并在 `${TRIM_PKGVAR}/venv` 创建可写、可持久化的独立环境。项目依赖在构建时锁定并下载为 `py3-none-any` wheel，安装/升级只从包内 wheelhouse 使用 `--no-index`，不会在设备上访问 pip 源。

## Install Configuration Ownership

首次安装向导只说明首次启动流程，不收集目录、服务 API Key 或端口。安装回调以固定端口 `14591`、空服务认证原子创建 `${TRIM_PKGVAR}/config/config.yaml`。安装、保留数据重装和升级遇到已有配置时，只幂等迁移 fnOS 托管字段 `server.port=14591`、`server.api_key=""`；来源、片库、回收、业务凭据和业务开关不得覆盖。来源、多个片库根和本地回收目录在首次 Web 启动通过 fnOS 共享目录授权能力选择，普通浏览器或平台能力不可用时可手填。后端仍保留 `server.api_key`、`server.port` 与 CLI/YAML 覆盖能力，但不在普通配置界面暴露。`14591` 位于 IANA 当前未分配的用户端口区间，避免与常见 NAS 服务端口及动态端口段混用。

安装脚本只创建 `${TRIM_PKGVAR}` 下的中转、日志和数据目录，不自动创建外部目录。外部目录未配置时服务只用于完成配置；watcher、入库、清理和恢复受 readiness 阻塞。来源、各片库、回收目录的存在性、授权、读写能力、挂载状态、磁盘容量和回收目录本地性，由首次 Web 开场检查验证。

manifest 设置 `micro_app=true`、最低系统 `1.2.0401`，`config/resource` 只声明 `trim.file.sharedAccess`。服务端每次调用从进程环境读取 `TRIM_API_TOKEN`，通过 `/var/run/trim_open_gateway_apiscope.socket` 查询授权目录，任何响应和日志都不得包含 token。

fnOS 桌面入口使用同源 CGI iframe。CGI 固定反向代理 `127.0.0.1:14591`，后端启动也只监听该回环地址；空服务认证不会暴露为 NAS 局域网直连端口。CGI 不得依赖 fnOS 环境未承诺提供的 `TRIM_PKGVAR` 或从旧配置猜测端口，应用启动与 CGI 上游共享同一托管端口契约。

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
./deploy/build_fpk.sh <version>
```

`fnpack` 或 wheel 不存在时脚本会下载构建依赖，因此该命令属于发布流程，不是日常重构验证命令。设备安装阶段不需要外网 pip。

构建脚本固定校验 fnpack 1.2.3，构建后运行 `scripts/validate_fpk.py` 检查真实包内容，并在 `build/` 生成 FPK 与 `.sha256`。该结果只能标记为 `LOCAL_BUILD PASS`，不能替代真实 fnOS 的安装、目录授权、依赖下载、CGI 和服务启动验收。
