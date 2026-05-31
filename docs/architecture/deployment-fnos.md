# fnOS Deployment

## Current Pattern

项目运行在飞牛 fnOS NAS 环境，使用 Python 服务和原生 Web UI。

## Important Rule

`deploy/` 目录内有独立副本，当前开发不自动同步 `deploy/`。需要同步部署目录时必须作为明确任务处理。

## Start Command

```bash
python3 -m media_importer.media_importer -c <config> serve -p <port> --host <host>
```
