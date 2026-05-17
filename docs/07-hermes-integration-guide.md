# NAS影视入库系统 - Hermes集成配置指令

> **使用方式**：将本文全部内容发给 Hermes，它会自行完成配置。

---

## 背景

需要你（Hermes）配置一个 Webhook 路由和一个 Skill，用于接收 NAS 影视自动化入库系统的通知，并支持通过对话操控该系统。

---

## 第0步：检查现有配置（重要！先检查是否已有配置

在开始配置前，先检查是否已经存在同名配置，避免冲突。

**请执行以下操作：

1. **检查是否已存在 `media-normalize` Webhook 路由：
   ```bash
   hermes webhook list
   ```
   - 如果 `media-normalize` 已存在，询问用户："检测到已存在名为 media-normalize 路由，是否需要删除后重新创建？"

2. **检查是否已存在 nas-media-importer Skill：
   ```bash
   hermes skills list
   ```
   - 如果 Skill 已存在，询问用户："检测到已存在 nas-media-importer Skill，是否需要覆盖更新？"

3. **如果都不存在，则继续后续步骤。

---

## 第1步：确认飞书 chat_id

在创建 Webhook 路由前，你需要知道飞书投递目标的 chat_id。

**请执行以下操作：**

1. 检查飞书平台是否已配置：查看 `~/.hermes/config.yaml` 中 `platforms.feishu` 是否存在
2. 获取当前飞书 home channel 的 chat_id：查看 `~/.hermes/config.yaml` 中 `platforms.feishu.home_channel` 或 `platforms.feishu.chat_id`
3. 如果找不到 chat_id，请告诉用户："我需要飞书的 chat_id 才能配置通知投递。请在飞书中给机器人发一条消息，我就能获取到 chat_id。"

**将获取到的 chat_id 记为 `FEISHU_CHAT_ID`，后续步骤会用到。

---

## 第2步：创建 Webhook 路由

使用以下命令创建 Webhook 订阅（将 `FEISHU_CHAT_ID` 替换为第1步获取的值）：

```bash
hermes webhook subscribe media-normalize \
  --deliver feishu \
  --deliver-chat-id "FEISHU_CHAT_ID" \
  --deliver-only \
  --prompt $'📺 NAS影视入库通知\n━━━━━━━━━━━━━━━\n{event_type_display}\n📁 文件: {video_file}\n📊 状态: {status}\n{extra_info}\n⏰ {timestamp}' \
  --description "NAS影视入库系统通知"
```

**执行后验证是否创建成功：**
```bash
hermes webhook list
```
确认列表中应包含 `media-normalize`。

**执行后会返回：**
- Webhook URL：`http://你的服务器:8644/webhooks/media-normalize`
- HMAC Secret：自动生成的密钥

**请将返回的 HMAC Secret 告诉用户**，用户需要将它填入 NAS 入库系统的 config.yaml 中。

**日后查询 HMAC Secret 的方法：**
如果用户忘记了 HMAC Secret，可以通过以下命令查看：
```bash
# 查看 ~/.hermes/config.yaml 中 `platforms.webhook.routes.media-normalize.secret`
```

---

## 第3步：安装 Skill

将以下内容写入 `~/.hermes/skills/nas-media-importer/SKILL.md`：

```bash
mkdir -p ~/.hermes/skills/nas-media-importer
cat > ~/.hermes/skills/nas-media-importer/SKILL.md << 'SKILL_EOF'
---
name: nas-media-importer
description: NAS影视自动化入库系统管理技能 - 通过API查询任务状态、重试失败任务、触发批量处理
metadata:
  hermes:
    tags: [nas, media, automation, import, video]
---

# NAS影视自动化入库系统管理技能

## When to Use

当用户提到以下内容时加载此技能：
- NAS影视入库相关操作
- 查询视频处理任务状态
- 重试失败的视频处理任务
- 触发批量扫描和入库
- 查看入库系统健康状态或指标
- 处理同名文件冲突
- 查看处理日志

## Quick Reference

| 操作 | 命令 |
|------|------|
| 触发批量处理 | `curl -X POST http://localhost:9855/api/run` |
| 处理指定文件 | `curl -X POST http://localhost:9855/api/run/file -d '{"path":"/path/to/file.mkv"}'` |
| 查看任务列表 | `curl http://localhost:9855/api/tasks` |
| 查看失败任务 | `curl "http://localhost:9855/api/tasks?status=FAILED"` |
| 查看任务详情 | `curl http://localhost:9855/api/tasks/{task_id}` |
| 重试失败任务 | `curl -X POST http://localhost:9855/api/tasks/{task_id}/retry` |
| 重试所有失败 | `curl -X POST http://localhost:9855/api/queue/retry-all` |
| 暂停队列 | `curl -X POST http://localhost:9855/api/queue/pause` |
| 恢复队列 | `curl -X POST http://localhost:9855/api/queue/resume` |
| 健康检查 | `curl http://localhost:9855/api/health` |
| 查看指标 | `curl http://localhost:9855/api/metrics` |

## Procedure

### 1. 查询任务状态

当用户询问"任务怎么样了"或"处理进度"时：

```bash
curl -s http://localhost:9855/api/tasks | python3 -m json.tool
curl -s "http://localhost:9855/api/tasks?status=FAILED" | python3 -m json.tool
curl -s http://localhost:9855/api/tasks/{task_id} | python3 -m json.tool
```

任务进度字段：`current_step`/`total_steps`（9步流水线）、`percentage`（0-100）、`step_name`、`bytes_copied`/`total_bytes`

### 2. 重试失败任务

当用户说"重试"或"再试一次"时：

```bash
curl -X POST http://localhost:9855/api/tasks/{task_id}/retry
```

重试所有失败任务：

```bash
FAILED_TASKS=$(curl -s "http://localhost:9855/api/tasks?status=FAILED" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for task in data.get('data', {}).get('tasks', []):
    print(task['task_id'])
")
for tid in $FAILED_TASKS; do
    curl -X POST http://localhost:9855/api/tasks/$tid/retry
done
```

### 3. 触发批量处理

当用户说"开始处理"或"跑一批"时：

```bash
curl -X POST http://localhost:9855/api/run
curl -X POST http://localhost:9855/api/run/file -H "Content-Type: application/json" -d '{"path": "/挂载/网盘下载/Inception.2010.mkv"}'
```

### 4. 处理同名文件冲突

当收到"任务跳过"通知且原因为同名文件时：

1. 查询详情：`curl -s http://localhost:9855/api/tasks/{task_id} | python3 -m json.tool`
2. 向用户汇报跳过原因，询问是否需要覆盖或重命名
3. 用户确认后重试任务

### 5. 查看系统状态

```bash
curl -s http://localhost:9855/api/health | python3 -m json.tool
curl -s http://localhost:9855/api/metrics | python3 -m json.tool
```

## Pitfalls

- API地址默认为 `http://localhost:9855`，NAS系统部署在其他机器上需使用正确IP和端口
- 重试前先确认导致失败的问题已解决（磁盘空间、网络等）
- 同名文件跳过是正常行为，不代表出错
- 9步流水线：扫描→复制→刮削→分类→同名检测→命名→入库→通知→记录

## Verification

- 查询任务状态返回正确JSON
- 重试后任务状态从FAILED变为PENDING再变为PROCESSING
- 健康检查返回ok
SKILL_EOF
```

如果 NAS 入库系统不在本机，请将上面命令中所有 `http://localhost:9855` 替换为实际地址（例如 `http://192.168.1.100:9855`）。

---

## 第4步：验证配置

**1. 验证 Webhook 路由：

```bash
hermes webhook test media-normalize --payload '{"event_type":"task_complete","event_type_display":"✅ 任务完成","timestamp":"2026-05-16T10:30:00","video_file":"test.mkv","status":"SUCCESS","extra_info":"测试通知","task":{}}'
```

如果飞书收到通知消息，说明 Webhook 配置成功。

**2. 验证 Skill 是否已加载：

```bash
hermes skills list
```

确认列表中包含 `nas-media-importer`。

**3. 在对话中输入 `/nas-media-importer`，确认技能已加载。

---

## 第5步：将密钥告知用户

将第2步返回的 HMAC Secret 告诉用户，用户需要将它填入 NAS 入库系统的 `config.yaml`：

```yaml
hermes:
  enabled: true
  webhook:
    base_url: "http://你的Hermes服务器IP:8644"
    route_name: "media-normalize"
    secret: "第2步返回的HMAC密钥"
    timeout: 30
    max_retries: 3
    retry_delay: 5
    events:
      - task_complete
      - task_failed
      - task_skipped
      - batch_complete
```

**注意**：请将 `http://你的Hermes服务器IP` 替换为实际 IP，例如 `http://10.200.200.6:8644`。

---

## 第6步：回滚/清理（配置错误时使用）

如果配置出错需要回滚：

**1. 删除 Webhook 路由：
```bash
hermes webhook remove media-normalize
```

**2. 删除 Skill：**
```bash
rm -rf ~/.hermes/skills/nas-media-importer
```

---

## 通知 Payload 格式（供 prompt 模板引用）

| 字段 | 说明 | 示例 |
|------|------|------|
| `event_type` | 事件类型 | `task_complete` / `task_failed` / `task_skipped` / `batch_complete` |
| `event_type_display` | 中文显示 | `✅ 任务完成` / `❌ 任务失败` / `⏭️ 任务跳过` / `📦 批量完成` |
| `timestamp` | 时间 | `2026-05-16T10:30:00` |
| `video_file` | 文件名 | `Inception.2010.mkv` |
| `status` | 状态 | `SUCCESS` / `FAILED` / `SKIPPED` |
| `extra_info` | 补充信息 | 入库路径或错误原因 |
| `task` | 完整任务数据 | 嵌套对象，用 `{task.import_path}` 访问 |

HMAC 签名方式：`X-Webhook-Signature` 请求头 = HMAC-SHA256(密钥, JSON body) 的 hex 摘要。
