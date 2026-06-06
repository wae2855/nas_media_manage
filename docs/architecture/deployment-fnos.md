# fnOS Deployment

## Current Pattern

项目运行在飞牛 fnOS NAS 环境，使用 Python 服务和原生 Web UI。

当前仓库默认开发版本已升级到 Python 3.12.x，本地开发通过根目录 `.python-version` 和项目 `.venv/` 隔离全局解释器。
fnOS 发布仍由 `deploy/build_fpk.sh` 在目标环境中创建独立 `venv`，但目标机器也必须提供 Python 3.12+。

## Important Rule

`deploy/nas-media-importer/` 是 fnOS package workspace，不是应用源码入口。

应用代码的唯一事实来源是根目录：

- `media_importer/`
- `hermes/`
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
