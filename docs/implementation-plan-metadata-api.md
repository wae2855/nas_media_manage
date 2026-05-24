# 影视元数据 API 集成实施计划

## 概述
实现 TMDb API 作为主元数据来源，降级至 LLM 作为兜底，并完善前端配置界面。

---

## 任务清单

### Phase 1：核心功能实现（优先级：高）

#### 1.1 创建 TMDb API 客户端
- **文件**：`media_importer/tmdb_client.py`
- **功能**：
  - 搜索电影 (`search/movie`)
  - 搜索电视剧 (`search/tv`)
  - 获取电影详情 (`movie/{id}`)
  - 获取电视剧详情 (`tv/{id}`)
  - 获取季详情 (`tv/{id}/season/{season}`)
  - 多语言支持 (`language` 参数)
  - 超时、重试、异常处理
- **参考 API**：https://developer.themoviedb.org/docs/getting-started

#### 1.2 创建统一元数据刮削器
- **文件**：`media_importer/metadata_scraper.py`
- **功能**：
  - 文件名预处理（提取标题、年份、季集信息）
  - 优先调用 TMDb
  - 失败时降级至 LLM
  - 格式统一：返回与 `LLMScraper` 相同的数据结构
  - 置信度标记：TMDb 结果为 0.95-1.0，LLM 结果为原置信度

#### 1.3 集成到 Pipeline
- **修改文件**：`media_importer/pipeline.py`
- **变更**：
  - 将 `LLMScraper` 替换为 `MetadataScraper`
  - 保持所有下游流程不变
  - 在 `_step_scrape` 中接入新刮削器

#### 1.4 更新配置系统
- **修改文件**：
  - `config.yaml.example`
  - `media_importer/config_loader.py`
  - `media_importer/config_validator.py`
- **新增配置**：
  ```yaml
  metadata:
    tmdb:
      enabled: true
      api_key: ""
      language: "zh-CN"
      fallback_language: "en-US"
      request_timeout: 10
      max_retries: 3
  ```
- **校验逻辑**：
  - 如果 `metadata.tmdb.enabled=true` 但 `api_key` 为空 → 提示配置但不阻止启动
  - 不配置 TMDb → 自动使用纯 LLM 模式

### Phase 2：前端配置界面（优先级：高）

#### 2.1 更新配置模板 UI
- **修改文件**：
  - `media_importer/webui/index.html`
  - `media_importer/webui/js/config.js`
- **新增项**：
  - TMDb 启用开关
  - TMDb API Key 输入框
  - TMDb 语言选择
  - TMDb 测试连接按钮
- **功能**：
  - API Key 掩码显示
  - 测试连接按钮（调用 `test-tmdb` 接口）
  - 获取 Key 帮助链接

#### 2.2 更新后端 API
- **修改文件**：`media_importer/api_server.py`
- **新增接口**：
  - `POST /api/config/test-tmdb` - 测试 TMDb API Key 是否有效

### Phase 3：测试（优先级：中）

#### 3.1 单元测试
- **文件**：`deploy/nas-media-importer/app/server/tests/test_full_flow.py`
- **新增测试**：
  - TMDb API 搜索（Mock）
  - 文件名预处理
  - 降级逻辑
  - 向后兼容性（无 TMDb Key 时）

#### 3.2 端到端测试
- 使用真实文件测试各种场景
- 验证季集匹配
- 验证配置变更

### Phase 4：部署（优先级：中）

#### 4.1 同步文件
- 同步所有新文件到 `deploy/` 目录
- 更新部署文档

---

## 数据流设计

### MetadataScraper 内部流程
```
输入：视频文件名，字幕文件名
    ↓
【步骤 1】文件名解析
    ├─ 提取纯净标题
    ├─ 提取年份
    └─ 提取季集信息
    ↓
【步骤 2】TMDb 搜索
    ├─ 优先：标题 + 年份
    ├─ 失败：仅标题
    └─ 未找到 → 进入【步骤 4】
    ↓
【步骤 3】结果转换
    ├─ 匹配最佳结果
    ├─ 转换为统一格式
    └─ 置信度 0.95-1.0
    ↓
【步骤 4】降级至 LLM（仅 TMDb 失败）
    └─ 调用现有 LLMScraper
    ↓
输出：统一格式刮削结果
```

### 字段映射

| 系统字段 | TMDb 字段 | 说明 |
|---------|---------|-----|
| `title_cn` | `title` (zh-CN) | 中文标题 |
| `title_en` | `original_title` | 英文标题 |
| `year` | `release_date[:4]` / `first_air_date[:4]` | 年份 |
| `type` | `media_type` (movie/tv) | 影视类型 |
| `season` | `season_number` | 季数（电视剧） |
| `episode` | - | 从文件名提取 |
| `confidence` | 1.0 (完全匹配) / 0.9 (模糊匹配) | 置信度 |
| `dimensions.media_type` | `media_type` | 媒体类型 |
| `raw_info` | TMDb 原始 JSON | 原始数据（便于调试） |

---

## 技术细节

### TMDb API 端点
- 基础 URL：`https://api.themoviedb.org/3`
- 搜索电影：`/search/movie?api_key={}&query={}&language={}`
- 搜索电视剧：`/search/tv?api_key={}&query={}&language={}`
- 电影详情：`/movie/{id}?api_key={}&language={}`
- 电视剧详情：`/tv/{id}?api_key={}&language={}`

### 文件名预处理规则
1. 移除常见标记：`r'\.(1080p|720p|2160p|BluRay|WEB-DL|HDTV|x264|x265|HDR|DDP5\.1|Atmos)[^.]*'`
2. 移除季集标记（先提取再移除）：`r'(S\d+E\d+|Season\.\d+|Episode\.\d+)'`
3. 移除年份标记（先提取再移除）：`r'\((19\d\d|20\d\d)\)|\.(19\d\d|20\d\d)\.'`
4. 替换分隔符：`r'[._]'` → `' '`
5. 首尾去空格

---

## 依赖检查
当前项目已使用 `urllib.request`（无需额外依赖），TMDb 客户端使用标准库即可实现。

---

## 验收标准
1. ✅ 配置 TMDb API Key 后，能成功刮削常见电影/电视剧
2. ✅ TMDb 失败时，能自动降级到 LLM
3. ✅ 不配置 TMDb 时，完全使用 LLM 模式
4. ✅ 前端界面完整，配置项齐全
5. ✅ 所有现有测试通过
6. ✅ 新增测试覆盖关键路径

---

## 向后兼容保证
- 所有现有接口不变
- 配置可选，不强制用户迁移
- 数据格式与现有系统完全兼容

