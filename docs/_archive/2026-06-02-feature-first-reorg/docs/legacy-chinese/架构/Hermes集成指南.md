# 影音库AI智能整理 - Hermes集成配置指令

> **使用方式**：将本文全部内容发给 Hermes，它会引导你完成配置。
> **原则**：每一步都需要你确认后才执行，不会擅自修改你的配置。

---

## 背景

需要配置 Hermes 与 影音库AI智能整理的集成，包括：
1. 一个 Webhook 路由 — 接收入库系统的飞书通知
2. 一个 Skill — 通过对话操控入库系统

---

## 第1步：检查现有配置

先检查是否已有相关配置，避免冲突：

1. 检查 Webhook 路由：
   ```bash
   hermes webhook list
   ```
   - 如果 `media-normalize` 已存在 → 告知用户并询问："已存在 media-normalize 路由，是否跳过？如需重建请先删除。"

2. 检查 Skill：
   ```bash
   hermes skills list
   ```
   - 如果 `nas-media-importer` 已存在 → 告知用户并询问："已安装 nas-media-importer Skill，是否跳过？如需更新请说'同步最新Skill'。"

**等用户确认后，再继续下一步。**

---

## 第2步：确认飞书 chat_id

1. 读取 `~/.hermes/config.yaml` 中 `platforms.feishu.home_channel` 或 `platforms.feishu.chat_id`
2. 如果找不到 → 请告诉用户："我需要飞书的 chat_id 才能配置通知投递。请在飞书中给机器人发一条消息，我就能获取到。"
3. 找到后告知用户："将使用飞书 chat_id: xxx，确认吗？"

**等用户确认后，再继续。**

---

## 第3步：创建 Webhook 路由

> 如果第1步确认跳过，则跳过此步。

告知用户即将创建的 Webhook 配置概要：

```
即将创建 Webhook 路由：
  名称: media-normalize
  投递: 飞书 (chat_id: xxx)
  模板: 📺 影音库AI智能整理通知 + 事件详情
```

**等用户确认后**，执行创建：

```bash
hermes webhook subscribe media-normalize \
  --deliver feishu \
  --deliver-chat-id "FEISHU_CHAT_ID" \
  --deliver-only \
  --prompt $'📺 影音库AI智能整理通知\n━━━━━━━━━━━━━━━\n{event_type_display}\n📁 文件: {video_file}\n📊 状态: {status}\n{extra_info}\n⏰ {timestamp}' \
  --description "影音库AI智能整理通知"
```

创建成功后，告知用户：
- ✅ Webhook 路由已创建
- 🔑 返回的 HMAC Secret：`xxx`（**用户稍后需要填入 NAS 入库系统配置**）

---

## 第4步：配置 Skill API 地址

向用户询问 NAS 入库系统的 API 地址：

> "请提供 NAS 入库系统的 API 地址（如 http://10.200.200.5:9855），Skill 需要通过这个地址调用入库系统的接口。"

**等用户提供后**，检查 `~/.hermes/config.yaml` 中是否已有 `skills.config.nas_importer`：

- 如果不存在 → 追加配置
- 如果已存在 → 确认是否需要更新

告知用户即将写入的配置：

```yaml
skills:
  config:
    nas_importer:
      api_url: "用户提供的地址"
```

**等用户确认后**，写入配置。

> **说明**：SKILL.md 通过 `metadata.hermes.config` 声明了 `nas_importer.api_url` 变量，Hermes 加载 Skill 时会自动从 config.yaml 读取并替换，无需手动修改 SKILL.md。

---

## 第5步：获取并审核 Skill

> 如果第1步确认跳过 Skill 安装，则跳过此步。

**1. 从 NAS 入库系统 API 获取 SKILL.md：**

```bash
API_URL=$(grep -A1 'nas_importer' ~/.hermes/config.yaml | grep api_url | sed 's/.*: *"\(.*\)"/\1/')
curl -s ${API_URL:-http://localhost:9855}/api/skill
```

**2. 审核内容并告知用户：**

获取到 SKILL.md 后，**不要直接保存**，先向用户展示审核摘要：

```
📋 Skill 审核摘要：
  名称: nas-media-importer
  描述: 影音库AI智能整理管理技能
  API端点数量: 20+
  功能范围: 任务查询/重试/批量处理/轮询控制/配置管理/日志查看
  通知事件: batch_start, batch_complete, program_error
  配置变量: nas_importer.api_url（已在上一步配置）
  安装路径: ~/.hermes/skills/nas-ops/nas-media-importer/SKILL.md
```

如果发现异常（如内容为空、不是合法的 SKILL.md 格式、包含可疑内容等），告知用户并停止安装。

**等用户确认"没问题"后**，再执行安装：

```bash
mkdir -p ~/.hermes/skills/nas-ops/nas-media-importer
echo "$SKILL_CONTENT" > ~/.hermes/skills/nas-ops/nas-media-importer/SKILL.md
```

安装完成后告知用户："✅ Skill 已安装到 ~/.hermes/skills/nas-ops/nas-media-importer/SKILL.md"

---

## 第6步：验证配置

逐项验证并告知用户结果：

**1. 验证 Webhook 路由：**

```bash
hermes webhook test media-normalize --payload '{"event_type":"batch_start","event_type_display":"📥 批量处理开始","timestamp":"2026-05-17T10:30:00","video_file":"","status":"BATCH_START","extra_info":"源目录: /vol1/downloads\n发现文件: 共 5 个（视频 3 个, 字幕 2 个）","task":{}}'
```

→ 告知用户："飞书是否收到了测试通知？"

**2. 验证 Skill 加载：**

```bash
hermes skills list
```

→ 确认列表中包含 `nas-media-importer`

**3. 功能验证：**

```bash
curl -s {nas_importer.api_url}/api/health
```

→ 确认 NAS 入库系统 API 可达

---

## 第7步：告知用户需要配置的 NAS 端内容

所有 Hermes 侧配置完成后，告知用户需要在 NAS 入库系统侧完成的配置：

**用户需要将以下内容填入 NAS 入库系统的 `config.prod.yaml`：**

```yaml
hermes:
  enabled: true
  webhook:
    base_url: "http://Hermes服务器IP:8644"    # ← 替换为 Hermes 实际地址
    route_name: "media-normalize"
    secret: "第3步返回的HMAC密钥"               # ← 替换为第3步获得的密钥
    timeout: 30
    max_retries: 3
    retry_delay: 5
  events:
    - batch_start
    - batch_complete
    - program_error
```

告知用户：
1. 将上面的配置填入 NAS 入库系统的 `config.prod.yaml`
2. 修改后执行 `curl -X POST http://NAS地址:9855/api/config/reload` 热重载配置，或重启服务
3. 配置完成后，入库系统处理文件时就会向飞书发送通知

---

## 回滚/清理

如果配置出错需要回滚：

**1. 删除 Webhook 路由：**
```bash
hermes webhook remove media-normalize
```

**2. 删除 Skill：**
```bash
rm -rf ~/.hermes/skills/nas-ops/nas-media-importer
```

**3. 删除 Skill 配置：**
从 `~/.hermes/config.yaml` 中移除 `skills.config.nas_importer` 节。

---

## 通知 Payload 格式

通知事件的详细字段说明请参考已安装的 SKILL.md：

```bash
cat ~/.hermes/skills/nas-ops/nas-media-importer/SKILL.md | grep -A 30 "Hermes 通知事件"
```

HMAC 签名方式：`X-Webhook-Signature` 请求头 = HMAC-SHA256(密钥, JSON body) 的 hex 摘要。
