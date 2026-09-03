# Notification and Monitoring Architecture

## Monitoring

- `media_importer/monitor/file_watcher.py`
- `media_importer/monitor/permission_checker.py`

FileWatcher 由 Python 服务进程创建和持有，不由浏览器页面持有。fnOS 桌面窗口、手机页面和 CGI 只负责访问服务；关闭界面不会停止监控。只有关闭后台自动整理开关、停止/卸载 fnOS 包或服务进程退出，才会停止 watcher。

自动运行页的开关和轮询周期更改后立即保存并调用运行时重载，再通过 `GET /api/watcher/status` 回读真实状态。响应区分 `configured_enabled`（用户设置）、`enabled`（线程实际运行）、`automatic_allowed`（当前目录能力）与 `status=disabled|blocked|not_started|running`，并返回具体 `reason`；前端不得把“设置为开启”冒充“后台正在运行”。`file_watcher` 更新不改变正在执行任务的 pipeline 快照，因此即使已有任务运行也不进入延迟配置队列。

已识别为 `fuse.rclone` 等远程文件系统的来源目录，在授权、挂载身份、读写能力和其他本地必需目录均通过时允许 watcher 启动。远程来源保留黄色运行提示，但不因提示本身阻断自动扫描。启动时检查来源与处理支持目录；空闲轮询只复核来源目录的读取、授权和挂载身份，不访问回收、日志、缓存或目标片库。发现稳定候选后才复核处理支持目录，分类确定 `import_path` 后只检查该任务命中的目标片库，随后才允许查重和发布。挂载消失、身份变化或不可读时暂停相应阶段并保留候选，恢复后自动重试，禁止把离线误判为空目录。`unknown` 来源以及远程回收、日志和缓存继续失败关闭。

回收保留期维护与来源轮询解耦，最多每 24 小时执行一次，服务启动后的首轮空闲扫描不遍历回收目录；维护时使用配置保存阶段已经规范化的片库根做边界比较，不重新解析或读取目标片库。正常运行中的 watcher 状态响应直接投影线程缓存的最近运行事实，不为页面刷新重新执行存储探针。

来源单元处置维护与来源轮询同线程串行：服务启动后及每次成功读取来源目录后执行轻量回调，先从 SQLite 查询 `WAITING/BLOCKED/RECYCLING/DELETING`，只有存在记录才复核对应来源、所需本地回收和删除账本；不得因此扫描任一目标片库。异常只记录中文原因并等待下一轮，不得终止 watcher。

## Notification

- `media_importer/notify/hermes_hook.py`
- `media_importer/notify/hooks.py`

## Boundaries

监控负责触发和检查；通知负责发送外部消息。业务决策仍应留在 import-flow 或对应 feature 应用服务中。

配置重载时的 Hermes notifier 与 FileWatcher 刷新由 `media_importer/features/configuration/runtime_service.py` 编排；API handler 只更新全局引用。
