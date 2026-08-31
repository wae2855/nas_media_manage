# fnOS 首次启动目录授权与多片库架构

Requirement: REQ-20260830-180954

## 配置合同

```yaml
library_roots:
  - id: default
    name: 主片库
    path: /vol1/media
    enabled: true
default_library_root_id: default
path_rules:
  - conditions: {category: movie}
    library_root_id: default
    template: "电影/{year}/{title}"
fallback_library_root_id: default
fallback_dir: "其他"
```

旧 `library_root` 只作为迁移输入和兼容读取，不再是新保存事实源。根 ID 满足小写字母数字、`_`、`-`，唯一且稳定；路径规范化后也必须唯一。

## 运行数据流

```text
规则匹配
  → 取得 library_root_id
  → 查找启用根
  → 渲染相对模板
  → realpath/commonpath 双重校验
  → 存储健康与容量门禁
  → 暂存/校验/发布
```

规则无匹配时使用 `fallback_library_root_id + fallback_dir`。根缺失、停用、掉线或越界均失败关闭。

## fnOS 目录授权边界

- 浏览器适配层只负责发起系统选择和接收被授权路径，不持久化平台 token。
- fnOS 页面通过官方 `/app-auth/pick-shared-file` 或 `/app-auth/authorize-shared-file` 路由进入原生选择器；独立同源回调页解析结果，原页面校验一次性 `state` 后只刷新授权事实，不覆盖尚未保存的路径选择。
- 服务端仅从当前进程环境读取 `TRIM_API_TOKEN`，通过 Unix socket 查询已授权共享目录；响应不包含 token。
- 配置路径和系统 ACL 是两份事实：来源、每个启用片库根与回收目录必须位于某个当前授权根之内，才能保存和通过 readiness。
- 回收角色过滤远程目录；服务端 validator 仍是最终安全边界。
- 只有非 fnOS 开发/普通浏览器环境暴露手工输入；真实 fnOS 的授权 API 不可用时失败关闭并提示管理员刷新，不能手填绕过。

## 打包边界

- manifest 保留 `python312` 依赖。
- x86/arm 分别构建 FPK 与 wheelhouse；安装只允许与目标架构匹配的离线 wheel。
- 安装向导不再收集目录；首次启动未完成时服务可用于配置，但 watcher、入库、清理和恢复保持 BLOCKED。

## 失败模式

| 失败 | 行为 |
|---|---|
| 片库挂载消失 | 标记 OFFLINE，暂停相关任务，不创建目录 |
| 规则引用未知根 | 配置 BLOCKED，不回退到任意根 |
| fnOS 选择器不可用 | 保留旧值、阻止保存并提示管理员刷新授权；非 fnOS 开发环境才允许手填 |
| 开放 API 查询失败 | 不声称已授权，保留重试 |
| wheel 缺失/架构不符 | 安装失败，日志说明缺失平台 |
