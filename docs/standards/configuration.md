# Configuration Standards

## Change Chain

新增或修改配置项必须检查：

```text
config.yaml.example
core/config_loader.py
core/config_migrations.py
core/config_validator.py
core/config_view.py
api/config_handlers.py
webui/js/config.js
webui/index.html
docs
tests
```

## Sensitive Data

返回前端的 `api_key`、`secret` 等敏感字段必须脱敏为 `***`。

## Business Access

业务代码优先通过 `ConfigView` 读取高频配置。

- import-flow services 不直接读取 `source_policy/path_rules/duplicate_handling/filename_templates/manual_review` 等深层 key。
- 新增配置项如果被业务层使用，必须同步 `ConfigView` 和默认值测试。
- loader/migration/validator 负责配置文件生命周期，`ConfigView` 负责运行期业务读取。
- 来源处理只读取 `source_policy.mode`；旧布尔字段不得再次成为业务分支事实源。
- 中心中转目录不是配置项。禁止新增 `temp_dir`、中转授权角色或以缓存名义恢复同类业务目录；影片暂存只允许作为目标侧任务私有实现细节。
- 片库规则必须以 `library_root` 为边界，禁止绝对模板、`..` 和渲染后越界。
- 无法证明安全公共根的旧绝对规则必须阻断保存，不能猜测迁移。
- `file_watcher.poll_interval` 单位为秒，默认 300 秒（5 分钟），保存值必须是 10–3600 的整数；基础界面使用有限预设，运行时 watcher 必须实际消费该值。已有用户显式保存的周期不得在升级时静默覆盖。
- `task_queue.max_concurrent` 必须是整数 `1` 或 `2`，默认及 NAS 推荐值为 `1`。前端控件、保存 API、全量校验和运行时门禁必须四层一致；不能只依赖 HTML `max` 防止超限。
