# fnOS 应用部署指南

## 一、概述

本文档基于 [飞牛应用开放平台](https://developer.fnnas.com/) 官方文档编写，描述如何将 `nas-media-importer` 打包为飞牛 fnOS 可安装的 `.fpk` 应用。

---

## 二、fnOS 应用架构

### 2.1 应用安装后的目录结构

安装到 fnOS 后，系统创建如下目录（`[appname]` = `nas-media-importer`）：

```
/var/apps/[appname]
├── target → /vol${x}/@appcenter/[appname]  ← 应用代码（只读）
├── var    → /vol${x}/@appdata/[appname]    ← 运行时数据（可写）
├── etc    → /vol${x}/@appconf/[appname]    ← 静态配置
├── home   → /vol${x}/@apphome/[appname]    ← 用户数据
├── tmp    → /vol${x}/@apptemp/[appname]    ← 临时文件
├── shares → ...                            ← 共享目录（根据 resource 配置）
├── manifest, ICON.PNG, ICON_256.PNG
├── cmd/     ← 生命周期脚本
├── config/  ← privilege, resource
└── wizard/  ← 安装/卸载/配置向导
```

### 2.2 关键环境变量

| 变量 | 含义 | 本应用用途 |
|------|------|-----------|
| `TRIM_APPDEST` | 代码目录（target） | Python 代码、venv、config.yaml.example |
| `TRIM_PKGVAR` | 数据目录（var） | config/config.yaml、data/tasks.json、logs/、PID 文件 |
| `TRIM_PKGETC` | 配置目录（etc） | 未使用 |
| `TRIM_TEMP_LOGFILE` | 错误日志路径 | 写入错误信息给用户看 |
| `wizard_port` | 安装向导端口 | 用户自定义服务端口，默认 9855 |

### 2.3 应用生命周期

```
安装: install_init → [解压 app.tgz 到 TRIM_APPDEST] → install_callback → [cmd/main start]
升级: [cmd/main stop] → upgrade_init → [覆盖 TRIM_APPDEST] → upgrade_callback → [cmd/main start]
卸载: [cmd/main stop] → uninstall_init → uninstall_callback → [删除 TRIM_APPDEST]
配置: config_init → [更新环境变量] → config_callback → [自动重启应用]
```

---

## 三、FPK 打包流程

### 3.1 使用项目构建脚本（推荐）

```bash
./deploy/build_fpk.sh          # 默认版本 1.0.0
./deploy/build_fpk.sh 1.1.0    # 指定版本号
```

输出文件：`build/nas-media-importer.fpk`

### 3.2 手动打包流程

```bash
cd deploy
fnpack create nas-media-importer

# 复制代码到 app/server/
cp -r ../media_importer nas-media-importer/app/server/
cp -r ../hermes         nas-media-importer/app/server/
cp ../config.yaml.example nas-media-importer/app/server/
cp ../requirements.txt    nas-media-importer/app/server/

# 编辑 manifest、cmd/*、config/*、wizard/*、app/ui/*

# 打包
cd nas-media-importer
fnpack build
```

---

## 四、打包目录结构

```
nas-media-importer/
├── manifest                        # 应用信息清单
├── ICON.PNG                        # 64x64 图标（应用中心显示）
├── ICON_256.PNG                    # 256x256 图标（应用详情显示）
├── app/
│   ├── server/                     # 原生应用代码目录
│   │   ├── media_importer/         # Python 应用
│   │   │   ├── api_server.py       # HTTP API 服务
│   │   │   ├── classifier.py       # 文件分类
│   │   │   ├── config_loader.py    # 配置加载
│   │   │   ├── config_validator.py # 配置验证
│   │   │   ├── dedup_checker.py    # 去重检查
│   │   │   ├── file_copier.py      # 文件复制
│   │   │   ├── file_mover.py       # 文件移动
│   │   │   ├── file_scanner.py     # 文件扫描
│   │   │   ├── file_watcher.py     # 文件监控
│   │   │   ├── hermes_hook.py      # Hermes Webhook
│   │   │   ├── hooks.py            # 钩子管理
│   │   │   ├── llm_scraper.py      # LLM 刮削
│   │   │   ├── logger.py           # 日志模块
│   │   │   ├── media_importer.py   # 主入口
│   │   │   ├── metrics.py          # 指标统计
│   │   │   ├── pipeline.py         # 处理流水线
│   │   │   ├── safety.py           # 安全模块
│   │   │   └── task_manager.py     # 任务管理
│   │   ├── hermes/                 # Hermes 集成（SKILL.md）
│   │   │   ├── skills/nas-ops/nas-media-importer/SKILL.md
│   │   │   └── webhook-route-config.yaml
│   │   ├── config.yaml.example     # 配置模板
│   │   └── requirements.txt        # Python 依赖
│   └── ui/                         # 桌面图标入口
│       ├── config                  # 入口配置（定义桌面图标）
│       └── images/                 # 图标资源
│           ├── icon-64.png         # 64x64 桌面图标
│           └── icon-256.png        # 256x256 桌面图标
├── cmd/                            # 应用生命周期脚本
│   ├── main                        # 启动/停止/状态检查
│   ├── install_callback            # 安装后初始化
│   ├── install_init                # 安装前（空）
│   ├── upgrade_callback            # 升级后更新依赖
│   ├── upgrade_init                # 升级前（空）
│   ├── uninstall_callback          # 卸载前清理 venv
│   ├── uninstall_init              # 卸载前（空）
│   ├── config_callback             # 配置变更后（空）
│   └── config_init                 # 配置变更前（空）
├── config/
│   ├── privilege                   # 权限配置
│   └── resource                    # 资源配置
└── wizard/
    ├── install                     # 安装向导（端口配置）
    ├── uninstall                   # 卸载向导
    └── config                      # 配置向导（端口配置）
```

---

## 五、关键配置说明

### 5.1 manifest — 应用信息

```
appname               = nas-media-importer
version               = 1.0.0
display_name          = NAS影视整理入库
desc                  = NAS影视自动化入库系统，支持AI智能刮削、自动分类入库影视文件
platform              = all
source                = thirdparty
maintainer            = wae2855
distributor           = wae2855
desktop_uidir         = ui                          ← 桌面入口 UI 目录
desktop_applaunchname = nas-media-importer.main      ← 桌面入口 ID
service_port          = 9855                         ← 默认端口（仅用于参考）
checkport             = false                        ← 端口动态配置，不做预检
ctl_stop              = true
changelog             = 1.0.0 初始版本发布
```

关键字段说明：
- `desktop_uidir = ui`：指定 `app/ui/` 为桌面入口目录
- `desktop_applaunchname = nas-media-importer.main`：对应 `app/ui/config` 中的入口 ID
- `checkport = false`：因为端口由向导动态配置，不做固定端口预检

### 5.2 app/ui/config — 桌面图标入口

```json
{
    ".url": {
        "nas-media-importer.main": {
            "title": "NAS影视整理入库",
            "icon": "images/icon-{0}.png",
            "type": "url",
            "protocol": "http",
            "port": "${wizard_port}",
            "url": "/",
            "allUsers": true
        }
    }
}
```

字段说明：
- `title`：桌面图标显示名称
- `icon`：图标路径，`{0}` 会被替换为 64 或 256
- `type: "url"`：在浏览器新标签页中打开
- `port: "${wizard_port}"`：使用向导中用户配置的端口号（V1.1.8+ 支持）
- `allUsers: true`：所有用户可见

### 5.3 cmd/main — 启动/停止/状态

基于官方模板，支持：
- `start` — 后台启动 Python 进程，写 PID 文件
- `stop` — TERM → 等待10秒 → KILL 优雅停止
- `status` — 通过 PID 文件检查进程存活（exit 0 运行 / exit 3 未运行）

启动命令：
```bash
${VENV_DIR}/bin/python3 ${APP_DIR}/media_importer/media_importer.py \
    -c ${CONFIG_FILE} serve --host 0.0.0.0 --port ${wizard_port:-9855}
```

端口优先级：`--port` 命令行参数 > `config.yaml` 中的 `server.port` > 默认值 9855

用到的目录：
- `TRIM_APPDEST/venv/` — Python 虚拟环境（首次启动自动创建）
- `TRIM_APPDEST/media_importer/` — 应用代码
- `TRIM_PKGVAR/config/config.yaml` — 运行时配置
- `TRIM_PKGVAR/app.pid` — PID 文件
- `TRIM_PKGVAR/info.log` — 运行日志

### 5.4 cmd/install_callback — 安装后初始化

1. 在 `TRIM_PKGVAR/` 下创建 `config/`、`data/`、`logs/` 目录
2. 复制 `config.yaml.example` → `config/config.yaml`（如不存在）
3. 创建空 `tasks.json`

> 注意：venv 创建不在 install_callback 中进行，而是在首次 `cmd/main start` 时自动完成。
> 这样避免 install_callback 因 venv 创建失败而报 INSTALL_CALLBACK_EXCEPTION。

### 5.5 cmd/upgrade_callback — 升级后

- 重新 `pip install -r requirements.txt`（如 venv 存在）

### 5.6 cmd/uninstall_callback — 卸载前

- 删除 `TRIM_APPDEST/venv/`

---

## 六、配置向导

### 6.1 安装向导（wizard/install）

安装时用户可自定义端口，初始值 `9855`。

### 6.2 配置向导（wizard/config）

安装后可在 **系统设置 → 应用设置** 中修改端口。修改后系统自动重启应用，新端口立即生效。

### 6.3 端口配置流转

```
用户在向导中输入端口 → wizard_port 环境变量 → cmd/main 读取 → --port 参数传递给应用
                                              → app/ui/config 读取 → 桌面图标打开正确端口
```

---

## 七、fnOS 安装后手动配置

应用安装完成后，用户需编辑配置文件：

```bash
# 配置文件路径（根据实际存储卷不同）
vi /vol1/@appdata/nas-media-importer/config/config.yaml
```

必须修改的项：
- `source_dir` — 影视文件来源目录
- `temp_dir` — 中转目录
- `log_dir` — 日志目录
- `llm.api_key` — LLM API 密钥

---

## 八、常见问题

### Q: 安装报 INSTALL_CALLBACK_EXCEPTION

**根因**：`install_callback` 脚本中某条命令返回非零退出码，且脚本使用了 `set -e`。

**当前版本已修复**：
- `install_callback` 不使用 `set -e`
- 所有命令添加 `|| true` 防止非零退出码
- venv 创建从 install_callback 移到 cmd/main start

如果仍然报错，请 SSH 登录 fnOS 查看 syslog：
```bash
grep nas-media-importer /var/log/syslog | tail -20
```

### Q: 安装成功但没有桌面图标

**原因**：打包时使用了 `--without-ui true`，导致没有生成桌面入口配置。

**当前版本已修复**：
- 使用 `fnpack create` 不带 `--without-ui` 参数
- 添加了 `app/ui/config` 入口配置
- manifest 中配置了 `desktop_uidir` 和 `desktop_applaunchname`

### Q: 启动失败，弹窗提示"Python虚拟环境创建失败"

fnOS 默认已包含 `python3-venv`。如果确实缺少，执行：
```bash
sudo apt-get install python3-venv
```
然后重启应用。

### Q: 启动失败，弹窗提示"pip依赖安装失败"

检查 fnOS 网络是否能访问 pypi.org，或查看 `info.log` 日志。

### Q: 服务启动后立即停止

查看日志：`cat /vol1/@appdata/nas-media-importer/info.log`

### Q: config.yaml 修改后不生效

在应用中心重启应用即可。

### Q: 修改端口后桌面图标打开的还是旧端口

在 **系统设置 → 应用设置** 中修改端口（不是直接改 config.yaml），这样桌面图标也会使用新端口。

---

## 九、自定义图标

图标文件存放在 `deploy/icons/` 目录：

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `ICON.PNG` | 64x64 | FPK 包根目录，应用中心列表显示 |
| `ICON_256.PNG` | 256x256 | FPK 包根目录，应用详情页显示 |
| `icon-64.png` | 64x64 | app/ui/images/，桌面小图标 |
| `icon-256.png` | 256x256 | app/ui/images/，桌面大图标 |

替换图标后重新执行 `./deploy/build_fpk.sh` 即可。

---

## 十、参考链接

- [飞牛应用开放平台](https://developer.fnnas.com/)
- [创建应用教程](https://developer.fnnas.com/docs/quick-started/create-application)
- [manifest 文档](https://developer.fnnas.com/docs/core-concepts/manifest)
- [应用入口文档](https://developer.fnnas.com/docs/core-concepts/app-entry)
- [用户向导文档](https://developer.fnnas.com/docs/core-concepts/wizard)
- [架构概述](https://developer.fnnas.com/docs/core-concepts/framework)
- [fnpack CLI 文档](https://developer.fnnas.com/docs/cli/fnpack)
