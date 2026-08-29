# fnOS Deployment

## Current Pattern

项目运行在飞牛 fnOS NAS 环境，使用 Python 服务和原生 Web UI。

当前仓库默认开发版本已升级到 Python 3.12.x，本地开发通过根目录 `.python-version` 和项目 `.venv/` 隔离全局解释器。
fnOS 发布由 `deploy/build_fpk.sh` 生成 FPK。manifest 声明官方 `python312` 依赖，应用优先使用 `/var/apps/python312/target/bin/python3`，并在 `${TRIM_PKGVAR}/venv` 创建可写、可持久化的独立环境。

## Install Configuration Ownership

首次安装向导收集服务端口、来源目录、片库根目录、本地回收目录和初始 API Key。安装回调把它们原子写入 `${TRIM_PKGVAR}/config/config.yaml`；配置已存在时不覆盖。之后 fnOS 配置向导只更新端口，业务目录继续在 Web 配置轨道内维护。

安装脚本只创建 `${TRIM_PKGVAR}` 下的中转、日志和数据目录，不自动创建用户填写的外部目录。来源、片库、回收目录的存在性、授权、读写能力、挂载状态、磁盘容量和回收目录本地性，由首次 Web 开场检查在后台整理启动前验证。

## Important Rule

`deploy/nas-media-importer/` 是 fnOS package workspace，不是应用源码入口。

应用代码的唯一事实来源是根目录：

- `media_importer/`
- `config.yaml.example`
- `requirements.txt`

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

`fnpack` 不存在时脚本会尝试下载工具，因此该命令属于发布流程，不是日常重构验证命令。

构建脚本固定校验 fnpack 1.2.3，构建后运行 `scripts/validate_fpk.py` 检查真实包内容，并在 `build/` 生成 FPK 与 `.sha256`。该结果只能标记为 `LOCAL_BUILD PASS`，不能替代真实 fnOS 的安装、目录授权、依赖下载、CGI 和服务启动验收。
