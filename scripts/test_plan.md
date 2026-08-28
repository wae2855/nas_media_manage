# 影音库AI智能整理 — 全流程测试计划

## 0. 配置问题报告

测试前发现的配置问题：

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | `restricted_level: 13-15` 应为 `13-16` | **中** | config.yaml 第 67 行 path_rule[2] 写 `13-15\|17+`，但维度系统映射值为 `13-16`（dimension_manager.py:12）。`13-15` 永远匹配不到任何影片，该规则的 13-15 分支形同虚设。`17+` 分支正常 |
| 2 | `cleanup_mode` 废弃参数 | 低 | config_validator 给出 warning，建议迁移到 `cleanup_source_after_done` |
| 3 | `delete_source_after_import` 废弃参数 | 低 | 已自动映射到 `cleanup_source_after_done`，不影响运行 |

## 1. 测试环境

| 项目 | 值 |
|------|-----|
| 基础目录 | `/tmp/nas_media_test/` |
| 源目录 | `/tmp/nas_media_test/source` |
| 临时目录 | `/tmp/nas_media_test/temp` |
| 回收站 | `/tmp/nas_media_test/recycle` |
| 影视库 | `/tmp/nas_media_test/影视/` |
| 服务端口 | `9855` |
| 总测试文件 | 84 个文件，42 个目录 |
| 测试场景 | 20 个 |

## 2. 测试场景矩阵

### 2.1 path_rules 覆盖矩阵（场景 1-11）

| 场景 | 文件名 | 媒体类型 | 维度特征 | 命中规则 | 预期路径 | 验证点 |
|------|--------|---------|---------|---------|---------|--------|
| 1 | Inception.2010.1080p.mkv | movie | PG-13→13-16 | 规则9 | `/影视/电影/2010/` | 电影分类+年份子目录+字幕关联 |
| 1 | The.Dark.Knight.2008.mkv | movie | PG-13→13-16 | 规则9 | `/影视/电影/2008/` | 4K REMUX 命名 |
| 1 | Avatar.2009.1080p.mkv | movie | PG-13→13-16 | 规则9 | `/影视/电影/2009/` | 3D 标签不影响刮削 |
| 2 | Deadpool.2016.1080p.mkv | movie | R→17+ | 规则8 | `/影视/电影-R/2016/` | 限制级电影分类 |
| 2 | Joker.2019.2160p.mkv | movie | R→17+ | 规则8 | `/影视/电影-R/2019/` | HDR 标签不影响刮削 |
| 3 | March.of.the.Penguins.2005.mkv | movie | documentary=true | 规则7 | `/影视/纪录片/` | 纪录片维度识别 |
| 4 | Spirited.Away.2001.mkv | movie | animation=true | 规则4 | `/影视/动漫电影/` | 动漫电影识别 |
| 4 | Your.Name.2016.mkv | movie | animation=true | 规则4 | `/影视/动漫电影/` | 动漫电影识别 |
| 5 | Pokemon.S01E01.mkv | tv | animation+TV-Y7→7-12 | 规则1 | `/影视/动漫/家庭向/` | 家庭向动漫分级 |
| 6 | Attack.on.Titan.S01E01.mkv | tv | animation+TV-MA→17+ | 规则2 | `/影视/动漫/青少年向/` | 17+分支匹配 |
| 7 | One.Piece.S01E01.mkv | tv | animation+TV-14→13-16 | 规则3 | `/影视/动漫/` | 通用动漫兜底 |
| 8 | Game.of.Thrones.S01E01.mkv | tv | TV-MA→17+ | 规则4 | `/影视/TV-R/` | 限制级TV |
| 9 | Friends.S01E01.mp4 | tv | TV-PG→7-12 | 规则5 | `/影视/电视剧/` | 通用TV+MP4格式 |
| 10 | 流浪地球.2019.mkv | movie | 一般分级 | 规则9 | `/影视/电影/2019/` | 中文标题刮削 |
| 11 | Some.Random.Indie.Film.2023.mkv | ? | 未知 | 规则10 | `/影视/其他/` | 兜底规则 |

### 2.2 源清理器场景（场景 12, 16-18, 20）

| 场景 | 目录 | 测试内容 | 预期结果 |
|------|------|---------|---------|
| 12 | BT_Downloads/ | BT下载目录完整模拟 | 保留视频+字幕+伴生(.nfo/.jpg/.png)，删除.url/.txt/.sfv/.log/.bak/.m3u/.db/RARBG*/Sample/ |
| 16 | Cleaner_Test/Movie_With_Extras/ | 花絮/预告/Extras/Trailers 黑名单目录 | 子目录内视频被标记为垃圾 |
| 17 | Cleaner_Test/Junk_Videos/ | 小体积视频（<50MB） | 标记为垃圾视频 |
| 18 | Cleaner_Test/Empty_Dirs/ | 空目录+非空目录混合 | 删除空目录，保留非空目录 |
| 20 | BDMV_Test/ | BDMV 蓝光原盘结构 | protect_extensions 保护 .bdmv/.clpi/.mpls |

### 2.3 边缘情况场景（场景 13-15, 19）

| 场景 | 测试内容 | 验证点 |
|------|---------|--------|
| 13 | 多季剧集 S01E01-S01E03 + S02E01 | 季集号正确解析 |
| 13 | 4种字幕格式 ass/ssa/vtt/sub | 全部格式被识别 |
| 14 | 6种视频格式 avi/ts/mov/wmv/m2ts/flv | 全部格式被扫描 |
| 15 | 中文电视剧（庆余年/三体） | 中文标题刮削+季集识别 |
| 19 | 同名不同分辨率重复文件 | 去重策略 quality 处理 |

## 3. 测试步骤

### 第一步：准备环境
```bash
# 1. 生成测试数据
python3 scripts/generate_test_data.py

# 2. 确认服务运行
curl http://127.0.0.1:9855/api/health

# 3. 验证配置
curl http://127.0.0.1:9855/api/config/validate
```

### 第二步：触发扫描
```bash
# 触发批量扫描（POST /api/run）
curl -X POST http://127.0.0.1:9855/api/run \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 第三步：监控任务进度
```bash
# 查看任务列表
curl http://127.0.0.1:9855/api/tasks

# 查看任务统计
curl http://127.0.0.1:9855/api/tasks/stats

# 查看队列状态
curl http://127.0.0.1:9855/api/queue/status
```

### 第四步：验证分类结果
```bash
# 对每个任务调用 classify-preview 验证分类路径
curl -X POST http://127.0.0.1:9855/api/tasks/{task_id}/classify-preview \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 第五步：验证入库结果
```bash
# 检查影视库目录结构
find /tmp/nas_media_test/影视/ -type f | sort

# 检查回收站
curl http://127.0.0.1:9855/api/recycle/list
```

### 第六步：测试源清理器
```bash
# 预览清理结果
curl http://127.0.0.1:9855/api/source-cleaner/preview

# AI 预览
curl http://127.0.0.1:9855/api/source-cleaner/ai-preview

# 执行清理（需确认）
curl -X POST http://127.0.0.1:9855/api/source-cleaner/execute \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

### 第七步：测试回收站
```bash
# 查看回收站列表
curl http://127.0.0.1:9855/api/recycle/list

# 恢复文件
curl -X POST http://127.0.0.1:9855/api/recycle/restore \
  -H "Content-Type: application/json" \
  -d '{"path": "..."}'

# 永久删除
curl -X POST http://127.0.0.1:9855/api/recycle/delete \
  -H "Content-Type: application/json" \
  -d '{"path": "..."}'
```

## 4. 验收标准

| 功能节点 | 验收标准 | 检查方法 |
|---------|---------|---------|
| 扫描 | 所有 84 个文件被扫描，视频+字幕正确分组 | `/api/tasks` 返回列表 |
| 刮削 | TMDB 匹配成功返回元数据，失败进入 AWAIT_REVIEW 或 FAILED | `/api/tasks/{id}` 查看 scrape_result |
| 分类 | 每部影片分类路径符合 path_rules 预期 | `/api/tasks/{id}/classify-preview` |
| 入库 | 文件出现在正确的影视库目录下 | `find /tmp/nas_media_test/影视/` |
| 回收入库 | 源文件移入回收站（cleanup_source_after_done=true） | `/api/recycle/list` |
| 清理器 | 垃圾文件被标记删除，伴生文件保留 | `/api/source-cleaner/preview` |
| 回收站 | 恢复/永久删除功能正常 | 对应 API 调用 |
| 任务状态 | 状态机转换正确（PENDING→SUCCESS/FAILED/SKIPPED） | `/api/tasks/stats` |

## 5. 注意事项

1. **TMDB API 限流**：少量文件逐一刮削，注意 API 调用频率。建议排队等待自然完成
2. **manual_review: false**：当前配置关闭人工审核，文件自动入库
3. **cleanup_source_after_done: true**：入库后源文件自动移入回收站
4. **task_queue.max_concurrent: 1**：单线程处理，约 30-40 个任务需排队
5. **源清理器 confirm_before_cleanup: true**：需手动确认或 API 传 `confirm: true`
6. **规则2 配置 bug**：`13-15` 应改为 `13-16`，否则 TV-14 级动漫会回退到规则3
