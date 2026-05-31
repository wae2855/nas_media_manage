# Notification and Monitoring Architecture

## Monitoring

- `media_importer/monitor/file_watcher.py`
- `media_importer/monitor/permission_checker.py`

## Notification

- `media_importer/notify/hermes_hook.py`
- `media_importer/notify/hooks.py`

## Boundaries

监控负责触发和检查；通知负责发送外部消息。业务决策仍应留在 pipeline 或应用服务中。
