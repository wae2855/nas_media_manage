# FNOS 应用部署指南

## 概述

本文档介绍如何构建 FNOS 应用包（`.fpk`）并上传到飞牛应用中心进行审核。

## 一、FPK 包构建

### 1.1 构建脚本

项目提供了自动构建脚本 `deploy/build_fpk.sh`：

```bash
# 进入部署目录
cd deploy

# 运行构建脚本（默认版本 1.0.0）
./build_fpk.sh

# 或指定版本号
./build_fpk.sh 1.0.1
```

### 1.2 构建输出

构建成功后会在 `build/` 目录生成：

```
build/
├── fnos-package/          # 打包前的临时目录
│   ├── cmd/               # FNOS 回调脚本
│   │   ├── main              # 启动脚本
│   │   ├── install_callback  # 安装后回调
│   │   ├── upgrade_callback  # 升级后回调
│   │   └── uninstall_callback # 卸载前回调
│   ├── etc/
│   │   └── systemd/
│   │       └── system/
│   │           └── nas-media-importer.service
│   ├── manifest           # 应用清单
│   └── opt/
│       └── nas-media-importer/  # 应用代码
└── nas-media-importer.fpk # 最终 FPK 包
```

### 1.3 手动构建（可选）

如果需要手动构建：

```bash
# 创建目录结构
mkdir -p fnos-package/{cmd,etc/systemd/system,opt/nas-media-importer}

# 复制文件
cp -r media_importer fnos-package/opt/nas-media-importer/
cp requirements.txt fnos-package/opt/nas-media-importer/
cp config.yaml.example fnos-package/opt/nas-media-importer/

# 创建必要目录
mkdir -p fnos-package/opt/nas-media-importer/{config,data,logs}
echo '{}' > fnos-package/opt/nas-media-importer/data/tasks.json

# 复制服务文件
cp deploy/nas-media-importer.service fnos-package/etc/systemd/system/

# 创建 manifest
cat > fnos-package/manifest <<EOF
appname=nas-media-importer
version=1.0.0
desc=NAS影视自动化入库系统
arch=x86_64
display_name=NAS影视入库
maintainer=your-name
source=thirdparty
service_port=9855
EOF

# 打包
tar -czvf nas-media-importer.fpk -C fnos-package .
```

## 二、飞牛应用中心上传流程

### 2.1 登录应用中心

1. 打开浏览器访问：`https://appcenter.feiniu.com`（需内网访问）
2. 使用管理员账号登录

### 2.2 创建应用

1. 点击左侧菜单 **"应用管理"** → **"应用列表"**
2. 点击 **"创建应用"** 按钮
3. 填写应用信息：

| 字段 | 说明 | 示例值 |
|------|------|--------|
| 应用名称 | 英文标识，唯一 | `nas-media-importer` |
| 显示名称 | 中文名称，用户可见 | `NAS影视入库` |
| 应用类型 | 选择服务类型 | `服务应用` |
| 架构 | 支持的 CPU 架构 | `x86_64` |
| 版本号 | 语义化版本 | `1.0.0` |
| 描述 | 应用功能说明 | `NAS影视自动化入库系统 - AI智能刮削、自动分类入库影视文件` |

### 2.3 上传安装包

1. 在应用详情页点击 **"版本管理"**
2. 点击 **"上传新版本"**
3. 选择本地构建的 `.fpk` 文件
4. 填写版本更新说明

### 2.4 提交审核

1. 上传完成后点击 **"提交审核"**
2. 等待审核人员审核（通常 1-3 个工作日）
3. 审核通过后应用会发布到应用市场

## 三、FPK 包结构说明

### 3.1 必需文件

| 文件路径 | 说明 |
|----------|------|
| `manifest` | 应用清单，包含应用基本信息 |
| `cmd/main` | 应用启动脚本 |
| `cmd/install_callback` | 安装后回调脚本 |
| `cmd/upgrade_callback` | 升级后回调脚本 |
| `cmd/uninstall_callback` | 卸载前回调脚本 |

### 3.2 manifest 字段说明

```bash
appname=nas-media-importer    # 应用唯一标识（英文）
version=1.0.0                 # 版本号
desc=应用描述                  # 应用功能说明
arch=x86_64                   # 架构：x86_64 或 arm64
display_name=显示名称          # 用户界面显示的名称
maintainer=维护者              # 联系人信息
source=thirdparty              # 来源类型
service_port=9855             # 服务端口（如有）
```

### 3.3 回调脚本说明

| 脚本 | 触发时机 | 职责 |
|------|----------|------|
| `install_callback` | 安装完成后 | 创建配置、初始化环境、安装依赖、启动服务 |
| `upgrade_callback` | 升级完成后 | 更新依赖、重启服务 |
| `uninstall_callback` | 卸载前 | 停止服务、清理资源 |
| `main` | 服务启动时 | 启动应用主进程 |

## 四、审核注意事项

### 4.1 审核标准

1. **安全性**：
   - 不包含恶意代码
   - 不获取敏感系统信息
   - 权限使用合理

2. **完整性**：
   - 所有必需文件齐全
   - manifest 字段完整正确
   - 回调脚本可执行

3. **兼容性**：
   - 支持目标架构（x86_64/arm64）
   - 不依赖系统特定版本

4. **稳定性**：
   - 安装/卸载/升级流程正常
   - 服务启动正常

### 4.2 常见问题

**Q1: 审核被拒绝，提示 "依赖缺失"**

A: 确保 `install_callback` 脚本中包含依赖安装逻辑：
```bash
python3 -m venv "/opt/nas-media-importer/venv"
"/opt/nas-media-importer/venv/bin/pip" install -r "/opt/nas-media-importer/requirements.txt"
```

**Q2: 服务启动失败**

A: 检查：
- Python 环境是否正确安装
- 端口是否被占用
- 配置文件是否存在

**Q3: 配置文件未生成**

A: 确保 `install_callback` 中包含配置初始化：
```bash
if [[ ! -f "/opt/nas-media-importer/config/config.yaml" ]]; then
    cp "/opt/nas-media-importer/config.yaml.example" "/opt/nas-media-importer/config/config.yaml"
fi
```

## 五、测试建议

在提交审核前，建议进行以下测试：

1. **安装测试**：
   ```bash
   # 在测试环境安装
   fnos-app install nas-media-importer.fpk
   ```

2. **启动测试**：
   ```bash
   systemctl status nas-media-importer
   curl http://localhost:9855/api/health
   ```

3. **升级测试**：
   ```bash
   # 构建新版本
   ./build_fpk.sh 1.0.1
   # 升级
   fnos-app upgrade nas-media-importer.fpk
   ```

4. **卸载测试**：
   ```bash
   fnos-app uninstall nas-media-importer
   ```

## 六、版本更新流程

1. 修改代码
2. 更新版本号：
   ```bash
   ./build_fpk.sh 1.0.1
   ```
3. 在应用中心上传新版本
4. 提交审核
5. 审核通过后发布

---

**文档版本**: 1.0.0  
**更新日期**: 2024年1月
