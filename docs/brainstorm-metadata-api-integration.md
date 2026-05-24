# 影视元数据刮削优化方案：结合 API + AI

## 问题陈述
当前系统**完全依赖 AI (LLM) 进行所有影视元数据刮削**，存在以下问题：
1. **成本高昂**：大量调用 LLM API，对于大批量文件处理非常昂贵
2. **一致性不稳定**：AI 对于同一影视的不同文件名刮削结果可能不一致
3. **依赖训练数据截止时间**：对新上映或小众作品的知识有限
4. **无结构化数据源**：完全依赖 AI 推理，无法直接获取权威元数据（如海报、演员、评分等）

目标：**先通过权威影视元数据 API 刮削，只有 API 找不到结果时才降级使用 AI**

---

## 免费可用元数据网站对比

| API 名称 | 是否免费 | 需要 Key | 请求限制 | 中文支持 | 数据质量 | 推荐指数 |
|---------|---------|---------|---------|---------|---------|---------|
| **TMDb (The Movie Database)** | ✅ 完全免费 | ✅ 需要 | 每分钟 100 次 | ✅ 支持多语言 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| OMDb (Open Movie Database) | ✅ 免费版可用 | ✅ 需要 | 每天 1000 次 | ⚠️ 英文为主 | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| IMDb API (imdb-api.com) | ✅ 免费版 | ✅ 需要 | 免费版限制 | ⚠️ 英文为主 | ⭐⭐⭐⭐ | ⭐⭐ |
| 豆瓣电影 API | ❌ 官方已关闭 | - | - | ✅ 中文最全 | ⭐⭐⭐⭐⭐ | - |
| 第三方豆瓣 API | ⚠️ 不稳定 | - | 可能有风险 | ✅ | ⭐⭐ | ⭐ |

---

## 方案选择

### 推荐方案：TMDb 作为主数据源 + AI 作为兜底
**为什么选择 TMDb？**
1. ✅ **完全免费**：只需注册账号获取 API Key 即可，无付费要求
2. ✅ **中文支持**：提供中文标题、中文简介、中文海报
3. ✅ **数据全面**：包含电影、电视剧、季集、演员、海报、评分、类型等
4. ✅ **API 设计完善**：搜索、详情、剧集查询、多语言支持
5. ✅ **社区活跃**：类似维基百科的编辑模式，数据持续更新
6. ✅ **请求限制宽松**：每分钟 100 次，完全满足家庭用户需求

**备选方案**：OMDb 作为补充（主要用于 IMDb ID 查询和匹配）

---

## 刮削流程设计

### 核心流程：多阶段刮削 + 降级策略

```
文件名预处理
    ↓
从文件名提取基础信息（标题、年份、季集、分辨率）
    ↓
【阶段 1】TMDb API 搜索（主数据源）
    ├─ 找到结果 → 使用 TMDb 数据 → 设置高 confidence (≥0.95)
    └─ 未找到 → 进入【阶段 2】
    ↓
【阶段 2】TMDb API 尝试模糊匹配（放宽搜索条件）
    ├─ 找到结果 → 使用 TMDb 数据 → confidence (0.85-0.95)
    └─ 未找到 → 进入【阶段 3】
    ↓
【阶段 3】降级至 AI 刮削（当前方案）
    └─ 处理完全未知或冷门作品
```

### 数据字段映射

**TMDb → 系统字段对应关系：**
| 系统字段 | TMDb 字段 | 说明 |
|---------|---------|-----|
| `title_cn` | `title` (中文 locale) 或 `original_title` | 中文标题 |
| `title_en` | `original_title` 或 `title` (英文) | 英文标题 |
| `year` | `release_date` 或 `first_air_date` 年份 | 年份 |
| `type` | `media_type` (movie/tv) | 影视类型 |
| `season` | `season_number` | 季数 (仅电视剧) |
| `episode` | `episode_number` | 集数 (仅单集) |
| `confidence` | 1.0 (完全匹配) / 0.9 (模糊匹配) | 置信度 |

---

## 配置变更

### 新增配置项 (`config.yaml`)
```yaml
# 新增：元数据 API 配置
metadata:
  # 主数据源：TMDb
  tmdb:
    enabled: true                  # 是否启用 TMDb 刮削（推荐 true）
    api_key: ""                    # 用户需要去 https://www.themoviedb.org/settings/api 获取
    language: "zh-CN"              # 优先返回的语言（zh-CN / en-US）
    fallback_language: "en-US"     # 中文找不到时的兜底语言
    request_timeout: 10            # API 请求超时（秒）
    max_retries: 3                 # API 失败重试次数
    cache_enabled: true            # 是否缓存 TMDb 搜索结果（避免重复请求）
    cache_ttl: 86400               # 缓存有效期（秒，默认24小时）
  
  # 其他数据源（可选）
  omdb:
    enabled: false
    api_key: ""
```

### 配置校验更新
- 新增 `tmdb.api_key` 校验（如果 `tmdb.enabled=true` 则必需）
- 保留原有 LLM 配置（作为兜底）

---

## 代码架构变更

### 新模块结构
```
media_importer/
├─ metadata_scraper.py           # 新增：统一元数据刮削入口
├─ tmdb_client.py                # 新增：TMDb API 客户端
├─ omdb_client.py                # 新增：OMDb API 客户端（可选）
├─ metadata_cache.py             # 新增：元数据搜索结果缓存
├─ llm_scraper.py                # 保持现有：作为兜底
└─ pipeline.py                   # 修改：接入新的刮削流程
```

### 关键接口设计

#### `MetadataScraper` 统一接口
```python
class MetadataScraper:
    def __init__(self, config: dict):
        """
        初始化元数据刮削器
        优先使用 TMDb，失败时降级至 LLM
        """
    
    def scrape(self, video_filename: str, subtitle_filenames: List[str] = None) -> Dict[str, Any]:
        """
        统一刮削入口，返回与 LLMScraper 相同的格式（无缝兼容）
        """
```

#### `TMDbClient` 设计
```python
class TMDbClient:
    def search_movie(self, title: str, year: Optional[int] = None) -> Optional[dict]:
        """搜索电影"""
    
    def search_tv(self, title: str, year: Optional[int] = None) -> Optional[dict]:
        """搜索电视剧"""
    
    def get_tv_season(self, tv_id: int, season_num: int) -> Optional[dict]:
        """获取电视剧季详情"""
    
    def get_movie_details(self, movie_id: int) -> dict:
        """获取电影完整信息"""
```

### Pipeline 集成

**修改 `_step_scrape` 流程：**
1. 替换原有的 `LLMScraper.scrape()` 为 `MetadataScraper.scrape()`
2. `MetadataScraper` 内部负责：API → 失败 → LLM 的降级逻辑
3. 输出格式完全与现有 LLM 结果兼容 → 后续流程无需任何修改

---

## 关键问题解决

### 1. 从文件名提取搜索关键词
**策略：**
- 移除常见标记：`.1080p`, `.BluRay`, `.x264`, `.HDR`, `.DDP5.1`, `[CHD]`, `[Team]` 等
- 移除季集标记（先保留用于后续匹配）：`S01E05`, `Season.1`, `Episode.5`
- 移除年份（先提取用于精确搜索）：`(2024)`, `.2024.`
- 替换 `.` 和 `_` 为空格：`Breaking.Bad` → `Breaking Bad`
- 优先搜索：`{标题} {年份}`，如果失败再搜索：`{标题}`

### 2. 缓存策略
**目标**：避免对同一影视重复请求 API
- 缓存 Key：`tmdb:{title}:{year}:{type}`
- 缓存内容：完整搜索结果
- 缓存存储：SQLite (复用现有数据库) 或 JSON 文件
- TTL：24 小时（TMDb 数据变化不频繁）

### 3. 季集匹配
**电视剧处理策略：**
1. 先用 `tv/{tv_id}` 获取基本信息
2. 如果文件名包含季/集信息，用 `tv/{tv_id}/season/{season}` 获取季详情
3. 进一步（可选）用 `tv/{tv_id}/season/{season}/episode/{episode}` 获取单集信息

### 4. 向后兼容
- 如果用户不配置 TMDb API Key → 自动回退到纯 LLM 模式
- 现有刮削结果格式保持不变 → 所有后续流程（验证、分类等）无需修改

---

## 实施方案优先级

### Phase 1：核心 TMDb 集成（MVP）
1. ✅ 创建 `tmdb_client.py` - 基础搜索
2. ✅ 创建 `metadata_scraper.py` - 统一接口 + 降级到 LLM
3. ✅ 修改 `pipeline.py` - 接入新刮削器
4. ✅ 更新配置模板
5. ✅ 前端配置界面增加 TMDb 配置项
6. ✅ 单元测试 + 端到端测试

### Phase 2：优化和增强
1. 搜索结果智能选择（优先匹配年份、语言）
2. 本地缓存机制
3. 季集详细信息刮削
4. OMDb 可选集成（用于 IMDb 匹配）

### Phase 3：高级功能（可选）
1. 元数据手动编辑界面
2. 刮削历史记录
3. 批量重新刮削
4. 海报/封面图下载（可选，因为系统当前不需要）

---

## 风险和注意事项

### 潜在风险
1. **TMDb API 变更**：依赖第三方服务，可能有 API 变更风险 → 需要做好异常处理
2. **网络问题**：NAS 可能无法访问 TMDb → 做好超时和重试，网络不通时自动回退到 LLM
3. **冷门作品**：TMDb 可能没有小众作品 → LLM 兜底正常工作

### 如何获取 TMDb API Key
文档参考：
1. 访问 https://www.themoviedb.org/signup 注册账号
2. 登录后访问 https://www.themoviedb.org/settings/api
3. 点击 "Create" 或 "Request an API Key"
4. 选择 "Developer"
5. 填写基本信息（应用名称、用途等）
6. 获取 API Key（v3 auth 或 v4 auth 都可以，推荐 v3）

---

## 成本效益分析

| 维度 | 当前方案（纯 LLM） | 新方案（TMDb + LLM） |
|-----|------------------|---------------------|
| API 调用成本 | 每次刮削都需要 | 90-99% 刮削免费 |
| 刮削速度 | 慢（LLM 推理） | 快（API 响应） |
| 结果一致性 | 可能波动 | 高度一致 |
| 数据准确性 | 依赖 AI 知识 | 权威数据源 |
| 实现复杂度 | 已实现 | 中等 |

---

## 下一步行动
请您评审此方案后，我将：
1. 根据您的反馈调整方案
2. 进入规划阶段（`/plan`）
3. 开始编码实现

