---
title: "Playwright 全流程 E2E 测试清单 v3"
type: plan
date: 2026-06-09
status: pending_review
confidence: high
req: REQ-20260609-E2E001
changelog:
  - v3 (2026-06-09): 对比 docs/_archive/2026-05-31-pre-docs-reorg/docs/测试/文件处理端到端测试用例.md，补充源端去重、字段缺失、API异常、重分类、file_location流转、忽略任务、源目录清理器、回归矩阵、笛卡尔补充共 13 类场景，共 127 条；总数 329。
  - v2 (2026-06-09): 引入 v2 计划，含 C00 Bug 修复验证、75 条配置测试、18 条扫描任务测试等共 202 条（修正 v2 文档中错误的 184 总数）。
  - v1 (2026-06-09): 初版。
---

# Playwright 全流程 E2E 测试清单 v3

> 本文档是可评审的测试清单，评审通过后再编写测试代码执行。

## 1. 测试基础设施

### 1.1 测试环境

| 项目 | 配置 |
|------|------|
| 测试框架 | pytest + playwright sync_api |
| 浏览器 | Chromium headless |
| 视口 | 1280×900（桌面）/ 375×812（移动） |
| 服务启动 | 自启动模式（`start_server` 在 ephemeral port） |
| 配置根目录 | `/tmp/nas_media_e2e_{run_id}/` |
| 数据库 | 每轮测试前清空 SQLite |
| 截图 | 每个测试结束自动截图到 `tests/screenshots/` |

### 1.2 测试文件命名

```
tests/
├── test_e2e_01_config.py          # 配置全流程
├── test_e2e_02_scan.py            # 扫描与任务创建
├── test_e2e_03_task_actions.py    # 任务操作（单/批量）
├── test_e2e_04_recycle.py         # 回收站全流程
├── test_e2e_05_navigation.py      # 导航与页面切换
├── test_e2e_06_batch.py           # 批量操作
├── test_e2e_07_visual.py          # 视觉与响应式
├── test_e2e_08_pipeline.py        # v3新增：流水线细节（源端去重/验证/分类/重分类/file_location/忽略/API异常）
├── test_e2e_09_source_cleaner.py  # v3新增：源目录清理器全功能
├── test_e2e_10_regression.py      # v3新增：回归矩阵 RT-01~05
├── test_e2e_11_cartesian_extra.py # v3新增：笛卡尔补充 TC-14
└── conftest.py                     # 共享 fixture
```

### 1.3 运行方式

```bash
# 运行全部 E2E 测试
python -m pytest tests/test_e2e_*.py --run-live-e2e -v

# 运行单个文件
python -m pytest tests/test_e2e_01_config.py --run-live-e2e -v

# 运行指定测试
python -m pytest tests/test_e2e_01_config.py::TestBasicDirectoryConfig::test_C01 -v
```

---

## 2. 测试数据设计

### 2.1 视频文件命名模式（模拟真实种子下载）

| ID | 文件名 | 类型 | 命名特征 | 预期识别 |
|----|--------|------|----------|----------|
| V01 | `Inception.2010.1080p.BluRay.x264-SPARKS.mkv` | 电影 | 英文标题+年份+分辨率+来源组 | movie, 2010, 1080p |
| V02 | `盗梦空间.Inception.2010.BD.1080P.国英双语.mkv` | 电影 | 中英双语+年份+分辨率 | movie, 2010, 1080p |
| V03 | `Breaking.Bad.S05E16.Felina.1080p.BluRay.x264.mkv` | 电视剧 | 标准SxxExx+集名+分辨率 | tv, S05E16 |
| V04 | `绝命毒师.S05E16.1080p.WEB-DL.mkv` | 电视剧 | 中文标题+SxxExx | tv, S05E16 |
| V05 | `[喵萌奶茶屋] 进击的巨人 最终季 - 01 [1080P][HEVC].mp4` | 动漫 | 发布组+标题+集数+编码 | tv, animation |
| V06 | `Planet.Earth.II.S01E01.Island.2160p.UHD.BluRay.mkv` | 纪录片 | BBC纪录片+4K+集数 | tv, documentary |
| V07 | `地球脉动第二季.S01E01.4K.HDR.mkv` | 纪录片 | 中文标题+4K+HDR | tv, documentary |
| V08 | `The.Shawshank.Redemption.1994.720p.BRRip.XviD.avi` | 电影 | 老片+低分辨率+旧编码 | movie, 1994, 720p |
| V09 | `[DMG] Jujutsu Kaisen - 24 [1080p].mkv` | 动漫 | 发布组+英文标题+集数 | tv, animation |
| V10 | `Chernobyl.S01.COMPLETE.720p.AMZN.WEB-DL.mkv` | 迷你剧 | COMPLETE+来源 | tv |
| V11 | `寄生虫.Parasite.2019.1080p.BluRay.mkv` | 电影 | 中文优先+英文+年份 | movie, 2019 |
| V12 | `三体.Three-Body.S01E01.2023.1080p.WEB-DL.mkv` | 电视剧 | 中英标题+SxxExx+年份 | tv, 2023 |
| V13 | `Oppenheimer.2023.2160p.UHD.BluRay.Remux.mkv` | 电影 | 4K+Remux | movie, 2023, 4K |
| V14 | `Your.Name.2016.1080p.BluRay.x264-[YTS].mkv` | 动漫电影 | 英文标题+年份+发布组 | movie, animation |
| V15 | `舌尖上的中国.S01E03.2012.1080i.ts` | 纪录片 | 中文+集数+旧格式 | tv, documentary |
| V16 | `Sample.mp4` | 无效 | 样本文件（<10MB） | 应被忽略/标记 |
| V17 | `movie_with_subtitle/The.Matrix.1999.1080p.mkv` | 电影+字幕 | 含视频+同名字幕 | 应识别字幕 |
| V18 | `Deadpool.&.Wolverine.2024.1080p.mkv` | 电影 | 特殊字符& | movie, 2024 |
| V19 | `老友记.Friends.S02E03-E04.1080p.mkv` | 电视剧 | 多集合并 | tv, S02E03 |
| V20 | `[SubGroup] 鬼灭之刃 柱稽古篇 - 08 [1080P].mp4` | 动漫 | 中文+篇章名+集数 | tv, animation |

### 2.2 字幕文件

| ID | 文件名 | 关联视频 |
|----|--------|----------|
| S01 | `Inception.2010.1080p.BluRay.x264-SPARKS.zh.srt` | V01 |
| S02 | `Breaking.Bad.S05E16.Felina.1080p.BluRay.x264.en.srt` | V03 |
| S03 | `三体.Three-Body.S01E01.2023.1080p.WEB-DL.chs&eng.ass` | V12 |

### 2.3 垃圾/干扰文件

| ID | 文件名 | 预期行为 |
|----|--------|----------|
| J01 | `Sample/sample.mp4`（<1MB） | 标记为样本/忽略 |
| J02 | `.DS_Store` | 忽略 |
| J03 | `movie.nfo` | 保留（元数据） |
| J04 | `poster.jpg` | 保留（海报） |

---

## 3. 测试场景矩阵

### 3.1 配置全流程（test_e2e_01_config.py）

#### 3.1.0 Bug 修复验证：配置页面加载

> **前置说明**：之前存在 Bug——API 返回 `{"data": {"config": {...}, "prompts": {...}}}` 但前端直接从 `result.data` 读取配置字段，导致所有字段为空。已修复为 `result.data.config || result.data`。以下测试验证此修复。

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C00 | 配置页面加载值 | 导航到配置页 | 源目录、中转目录、回收目录等字段**非空**，显示 config.yaml 中的实际值 |

#### 3.1.1 基础目录配置

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C01 | 首次打开配置页 | 点击 `[data-nav="config"]` | 配置页可见，步骤条显示，源目录面板展开 |
| C02 | 源目录字段值 | 查看 `#cfg-source-inline` | 输入框有值（来自 config.yaml），非空 |
| C03 | 中转目录字段值 | 切换到 `[data-config-stage="temp"]`，查看 `#cfg-temp-inline` | 输入框有值 |
| C04 | 回收目录字段值 | 切换到 `[data-config-stage="recycle"]`，查看 `#cfg-recycle-inline` | 输入框有值 |
| C05 | 修改源目录 | 清空 `#cfg-source-inline`，输入新路径 | 输入值保留 |
| C06 | 路径权限测试 | 点击 `[data-path-test="source"]` | 显示测试结果（成功/失败） |
| C07 | 保存源目录配置 | 点击 `[data-config-save="source"]` | toast 提示保存成功 |
| C08 | 刷新后配置保留 | 刷新页面，回到配置页 | 源目录值与保存前一致 |
| C09 | 步骤切换 | 点击 `[data-config-stage="scrape"]` | 刮削面板展开，源目录面板折叠 |
| C10 | 空目录保存 | 清空 `#cfg-source-inline`，点击保存 | 提示错误或 toast 失败 |

#### 3.1.2 源策略配置

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C11 | 清理模式选择 | 选择 `read_only` 单选按钮 | radio 选中状态更新 |
| C12 | 清理模式切换 | 选择 `media_and_related` | AI 清理选项区域显示/隐藏 |
| C13 | 递归扫描开关 | 切换 `#cfg-source-recursive-toggle-inline` | 开关状态变化，深度字段显示/隐藏 |
| C14 | 递归深度输入 | 输入 `3` 到 `#cfg-source-depth-inline` | 值更新为 3 |
| C15 | 智能清理开关 | 切换 `#cfg-source-cleaner-enabled-inline` | 清理配置区域展开/折叠 |
| C16 | 保存源策略 | 点击 `[data-config-save="source"]` | toast 成功 |
| C17 | 验证源策略持久化 | 刷新后检查 | 清理模式、递归开关与保存前一致 |

#### 3.1.3 LLM 配置

> **跳过保存测试**：LLM API Key 由人工提前录入，测试中不执行保存操作，避免覆盖真实 Key 导致后续刮削功能失效。

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C18 | LLM 配置页展示 | 切换到 `[data-config-stage="ai"]` | Provider 下拉有值，API Key 输入框可见 |
| C19 | API Key 脱敏验证 | 查看 `#cfg-llm_api_key-inline` | 值显示为 `***`（type=password），非明文 |
| C20 | LLM 模型名可见 | 查看 `#cfg-llm_model-inline` | 显示实际模型名（如 MiniMax-M2.7） |
| C21 | LLM Base URL 可见 | 查看 `#cfg-llm_base_url-inline` | 显示实际 URL |
| ~~C22~~ | ~~保存 LLM 配置~~ | ~~跳过~~ | ~~避免覆盖真实 Key~~ |
| ~~C23~~ | ~~测试 LLM 连接~~ | ~~跳过~~ | ~~避免触发不必要的 API 调用~~ |

#### 3.1.4 TMDB Provider 配置

> **跳过保存测试**：TMDB API Key 由人工提前录入，测试中不执行保存/启用/禁用操作。

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C24 | Provider 列表展示 | 切换到 `[data-config-stage="scrape"]` | TMDB 卡片可见，状态为"已启用" |
| C25 | TMDB API Key 脱敏 | 查看 Provider 卡片中的 API Key | 值显示为 `***`，非明文 |
| ~~C26~~ | ~~保存 Provider~~ | ~~跳过~~ | ~~避免覆盖真实 Key~~ |
| ~~C27~~ | ~~测试 TMDB 连接~~ | ~~跳过~~ | ~~避免影响后续刮削测试~~ |
| ~~C28~~ | ~~禁用 TMDB~~ | ~~跳过~~ | ~~避免影响后续刮削测试~~ |

#### 3.1.5 入库规则配置

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C29 | 规则列表展示 | 切换到 `[data-config-stage="rules"]` | 规则列表可见，每条规则显示条件+模板 |
| C30 | 兜底目录展示 | 查看 `#cfg-fallback-inline` | 输入框有值 |
| C31 | 保存规则 | 点击 `[data-config-save="rules"]` | toast 成功 |
| C32 | 刷新后规则保留 | 刷新页面，回到规则步骤 | 规则数量和内容与保存前一致 |

#### 3.1.6 高级配置-入库名称规范

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C33 | 导航到命名规范 | 配置页→高级配置→入库名称规范 | `data-view="naming-config"` 页面可见 |
| C34 | 电影模板字段 | 查看 `#cfg-filename_templates-movie-inline` | 输入框有值或 placeholder 可见 |
| C35 | 电视剧模板字段 | 查看 `#cfg-filename_templates-tv-inline` | 输入框有值或 placeholder 可见 |
| C36 | 字幕模板字段 | 查看 `#cfg-filename_templates-subtitle-inline` | 输入框有值或 placeholder 可见 |
| C37 | 同名文件策略下拉 | 查看 `#cfg-duplicate_handling-strategy-inline` | 下拉有 skip/replace/rename/quality 选项 |
| C38 | 保存命名规范 | 点击 `[data-config-save="naming"]` | toast 成功 |
| C39 | 返回高级配置 | 点击"返回高级配置" | 回到 `data-view="advanced-config"` |

#### 3.1.7 高级配置-影视分类维度

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C40 | 导航到维度配置 | 高级配置→影视分类维度 | `data-view="dimensions-config"` 页面可见 |
| C41 | 已启用维度列表 | 查看 `#dim-enabled-list` | 至少有 media_type、documentary、restricted_level |
| C42 | 可添加维度列表 | 查看 `#dim-available-list` | 至少有 animation、region 等 |
| C43 | 禁用维度 | 点击已启用维度中的禁用按钮 | 维度从已启用列表移到可添加列表 |
| C44 | 启用维度 | 点击可添加维度中的启用按钮 | 维度从可添加列表移到已启用列表 |
| C45 | 返回高级配置 | 点击"返回高级配置" | 回到高级配置页 |

#### 3.1.8 高级配置-AI刮削提示词

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C46 | 导航到提示词配置 | 高级配置→AI刮削提示词 | `data-view="prompt-config"` 页面可见 |
| C47 | LLM纯AI区域 | 查看 `#prompt-system` textarea | 非空，有默认提示词内容 |
| C48 | 展开 LLM+TMDB 区域 | 点击 `[data-advanced-disclosure="prompt-tmdb"]` | TMDB 提示词面板展开 |
| C49 | TMDB 提示词内容 | 查看 `#prompt-tmdb` textarea | 非空 |
| C50 | 预览系统提示词 | 点击 `[data-prompt-action="preview-system"]` | 弹窗显示完整提示词 |
| C51 | 关闭预览弹窗 | 点击 `.cinema-modal-close` | 弹窗关闭 |
| C52 | 恢复默认系统提示词 | 点击 `[data-prompt-action="reset-system"]` | textarea 内容恢复为默认值 |
| C53 | 保存全部提示词 | 点击 `[data-prompt-action="save-all"]` | toast 成功 |
| C54 | 刷新后提示词保留 | 刷新页面，回到提示词页 | 内容与保存前一致 |

#### 3.1.9 高级配置-置信度计算

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C55 | 导航到置信度配置 | 高级配置→置信度计算 | `data-view="confidence-config"` 页面可见 |
| C56 | 阈值条展示 | 查看 `#confidence-threshold-bar` | 阈值条可见，三个手柄（审核/确认/通过） |
| C57 | 阈值数值展示 | 查看 `[data-confidence-value="pass_threshold"]` | 显示数值（如 0.80） |
| C58 | Provider 最低匹配滑块 | 查看 `[data-confidence-input="threshold"]` | 滑块可见，值显示 |
| C59 | 搜索匹配策略展开 | 点击"搜索匹配策略" section header | 折叠面板展开，显示参数网格 |
| C60 | 保存置信度 | 点击 `[data-config-save="confidence"]` | toast 成功 |
| C61 | 刷新后置信度保留 | 刷新页面，回到置信度页 | 阈值与保存前一致 |

#### 3.1.10 高级配置-安全配置

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C62 | 导航到安全配置 | 高级配置→安全配置 | `data-view="security-config"` 页面可见 |
| C63 | API Key 字段 | 查看 `#cfg-server_api_key-inline` | type=password，值脱敏 |
| C64 | 端口字段 | 查看 `#cfg-server_port-inline` | 显示端口号（如 9855） |
| C65 | 保存安全配置 | 点击 `[data-config-save="security"]` | toast 成功 |

#### 3.1.11 高级配置-Hermes通知

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C66 | 导航到 Hermes 配置 | 高级配置→Hermes通知 | `data-view="hermes-config"` 页面可见 |
| C67 | 启用开关 | 查看 `#cfg-hermes_enabled-inline` | 开关可见 |
| C68 | 切换启用 | 点击启用开关 | Webhook 配置字段展开/折叠 |
| C69 | Webhook 字段 | 查看 `#cfg-hermes_webhook_base_url-inline` 等 | 字段可见 |
| C70 | 签名密钥脱敏 | 查看 `#cfg-hermes_webhook_secret-inline` | type=password |
| C71 | 通知事件复选框 | 查看 `#cfg-hermes_event_batch_start-inline` 等 | 复选框可见 |
| C72 | 保存 Hermes | 点击 `[data-config-save="hermes"]` | toast 成功 |

#### 3.1.12 高级配置-系统设置

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| C73 | 导航到系统设置 | 高级配置→系统设置 | `data-view="system-settings"` 页面可见 |
| C74 | 日志目录 | 查看 `#cfg-log_dir-inline` | 输入框有值 |
| C75 | 资源目录 | 查看 `#cfg-resource_dir-inline` | 输入框有值 |
| C76 | 最大并发 | 查看 `#cfg-task_queue-max_concurrent-inline` | 值为 1-5 |
| C77 | 视频后缀 | 查看 `#cfg-video_extensions-inline` | textarea 有内容（.mkv 等） |
| C78 | 字幕后缀 | 查看 `#cfg-subtitle_extensions-inline` | textarea 有内容（.srt 等） |
| C79 | 保存系统设置 | 点击 `[data-config-save="system"]` | toast 成功 |

### 3.2 扫描与任务创建（test_e2e_02_scan.py）

#### 3.2.1 扫描触发

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| S01 | 首页扫描按钮 | 配置完成，source_dir 有 V01-V20 | 点击 `[data-action="scan"]` | toast 提示扫描已启动 |
| S02 | 首页队列状态 | 扫描进行中 | 查看 `#runtime-status` | 状态元素存在 |
| S03 | 空目录扫描 | source_dir 为空 | 点击扫描 | toast 提示"没有新文件" |
| S04 | 重复扫描 | 已扫描过 | 再次点击扫描 | 提示"没有新文件"或只扫描新增文件 |

#### 3.2.2 任务状态转换

| # | 起始状态 | 触发操作 | 预期终态 | 验证 |
|---|----------|----------|----------|------|
| T01 | PENDING | 自动处理 | PROCESSING | 卡片状态变为"处理中" |
| T02 | PROCESSING | 刮削成功 | SUCCESS | 卡片状态变为"已完成" |
| T03 | PROCESSING | 刮削失败 | FAILED | 卡片状态变为"失败"，显示错误信息 |
| T04 | PROCESSING | 置信度低 | CONFIRMING | 卡片状态变为"待确认" |
| T05 | CONFIRMING | 用户确认 | SUCCESS | 状态变为"已完成" |
| T06 | CONFIRMING | 用户忽略 | SKIPPED | 状态变为"已跳过" |
| T07 | FAILED | 用户重试 | PENDING→PROCESSING | 重新进入处理流程 |
| T08 | FAILED | 超过重试上限 | 自动移入回收 | 任务从列表消失，回收站出现 |
| T09 | SUCCESS | — | 终态 | 无更多操作按钮（仅查看） |

#### 3.2.3 不同视频类型的扫描结果

| # | 视频文件 | 预期 media_type | 预期维度命中 | 预期入库路径模式 |
|---|----------|----------------|-------------|-----------------|
| ST01 | V01 (Inception) | movie | 非动漫, 非纪录片 | `/影视/电影/2010/...` |
| ST02 | V03 (Breaking Bad) | tv | 非动漫 | `/影视/电视剧/.../Season 05/` |
| ST03 | V05 (进击的巨人) | tv | 动漫 | `/影视/动漫/.../Season /` |
| ST04 | V06 (Planet Earth II) | tv | 纪录片 | `/影视/纪录片/...` |
| ST05 | V14 (Your Name) | movie | 动漫 | `/影视/动漫电影/...` |

### 3.3 任务操作（test_e2e_03_task_actions.py）

#### 3.3.1 单任务操作

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| A01 | 查看任务详情 | 至少1个任务 | 点击 `[data-task-action="view-task"]` | `.cinema-modal-overlay` 弹窗显示 |
| A02 | 详情-刮削结果 | 任务已刮削 | 查看弹窗 | 显示匹配标题、年份、类型、置信度 |
| A03 | 详情-失败原因 | 任务状态为 FAILED | 查看弹窗 | 红色高亮显示错误信息 |
| A04 | 详情-重命名预览 | 打开详情 | 修改文件名输入框 | 下方实时显示新文件名预览 |
| A05 | 详情-重命名保存 | 修改文件名 | 点击保存 | toast 成功 |
| A06 | 详情-重命名空值 | 清空文件名 | 查看预览 | 输入框红色边框 |
| A07 | 详情-分类微调 | 打开详情 | 修改维度值，点击应用 | toast 成功 |
| A08 | 详情-分类微调空值 | 不填任何维度 | 点击应用 | toast 提示错误 |
| A09 | 单任务重试 | FAILED 任务 | 点击 `[data-task-action="retry-task"]` | 状态变为 PENDING→PROCESSING |
| A10 | 单任务确认 | CONFIRMING 任务 | 点击 `[data-task-action="confirm"]` | 状态变为 SUCCESS |
| A11 | 单任务忽略 | CONFIRMING 任务 | 点击 `[data-task-action="ignore-task"]` | 状态变为 SKIPPED |
| A12 | 单任务移入回收 | 任意任务 | 点击 `[data-task-action="delete-task"]` | 确认弹窗→确认→任务消失 |
| A13 | 单任务移入回收-取消 | 任意任务 | 点击删除→取消 | 任务仍在列表 |

#### 3.3.2 筛选与导航

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| A14 | 全部筛选 | 点击 `[data-task-filter-chip="all"]` | 显示所有状态任务，chip 激活 |
| A15 | 待处理筛选 | 点击 `[data-task-filter-chip="pending"]` | 只显示 PENDING/PROCESSING |
| A16 | 待确认筛选 | 点击 `[data-task-filter-chip="confirm"]` | 只显示 CONFIRMING |
| A17 | 失败筛选 | 点击 `[data-task-filter-chip="failed"]` | 只显示 FAILED |
| A18 | 已完成筛选 | 点击 `[data-task-filter-chip="success"]` | 只显示 SUCCESS/SKIPPED |
| A19 | 空筛选结果 | 某状态无任务 | 显示空状态占位 |
| A20 | 筛选切换清空选中 | 选中任务后切换筛选 | 选中状态清空 |

### 3.4 回收站全流程（test_e2e_04_recycle.py）

#### 3.4.1 回收站基础

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| R01 | 空回收站 | 无回收项 | 导航到回收页 | 显示"回收站还是空的" |
| R02 | 回收站统计 | 有回收项 | 查看统计区 | 可恢复数、待清理数、占用空间正确 |
| R03 | 单项恢复 | 有可恢复项 | 点击 `[data-recycle-action="restore-recycle"]` | toast 成功，项从列表消失 |
| R04 | 单项查看原因 | 有不可恢复项 | 点击 `[data-recycle-action="view-recycle"]` | 弹窗显示原因 |
| R05 | 单项清理 | 有待清理项 | 点击 `[data-recycle-action="delete-recycle"]` | 确认→项消失 |
| R06 | 单项清理-取消 | 有待清理项 | 点击清理→取消 | 项仍在列表 |
| R07 | 清理过期项 | 有过期项 | 点击 Hero 区清理按钮 | 确认→过期项消失 |

#### 3.4.2 回收站恢复冲突

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| R08 | 恢复冲突-跳过 | 源位置已有同名文件 | 恢复→冲突弹窗→跳过 | 文件不覆盖 |
| R09 | 恢复冲突-覆盖 | 源位置已有同名文件 | 恢复→冲突弹窗→覆盖 | 新文件覆盖旧文件 |
| R10 | 恢复冲突-重命名 | 源位置已有同名文件 | 恢复→冲突弹窗→重命名 | 新文件以重命名方式恢复 |

### 3.5 批量操作（test_e2e_06_batch.py）

#### 3.5.1 任务批量操作

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| B01 | 选中单个任务 | 有任务 | 点击 `input[data-task-select]` | 选中计数显示"已选 1 项" |
| B02 | 选中多个任务 | 有多个任务 | 点击多个 checkbox | 计数递增 |
| B03 | 全选 | 有任务 | 点击 `#task-select-all` | 所有当前筛选任务被选中 |
| B04 | 全选-取消 | 已全选 | 再次点击全选 | 所有取消选中 |
| B05 | 清空选择 | 已选中多个 | 点击清空选择 | 选中清空，计数归零 |
| B06 | 批量重试 | 筛选"失败"，选中多个 | 点击 `[data-batch-task-action="batch-retry"]` | 确认→toast 显示结果 |
| B07 | 批量确认 | 筛选"待确认"，选中多个 | 点击 `[data-batch-task-action="batch-confirm"]` | 确认→任务状态更新 |
| B08 | 批量忽略 | 选中多个 | 点击 `[data-batch-task-action="batch-ignore"]` | 确认→任务状态更新 |
| B09 | 批量移入回收 | 选中多个 | 点击 `[data-batch-task-action="batch-delete"]` | 确认→任务消失 |
| B10 | 批量移入回收-取消 | 选中多个 | 点击批量删除→取消 | 任务仍在 |
| B11 | 0 项选中时按钮状态 | 无选中 | 查看批量按钮 | 批量按钮 disabled |
| B12 | 批量重试按钮显隐 | 筛选"全部" | 查看工具栏 | "批量重试"按钮隐藏 |
| B13 | 批量重试按钮显隐 | 筛选"失败" | 查看工具栏 | "批量重试"按钮可见 |
| B14 | 批量确认按钮显隐 | 筛选"待确认" | 查看工具栏 | "批量确认"按钮可见 |
| B15 | >50 项提示 | 选中 >50 项 | 点击批量操作 | toast 提示超限（如不足50项则 skip） |
| B16 | 批量操作后选中清空 | 批量操作完成 | 查看选中状态 | 选中自动清空 |

#### 3.5.2 回收站批量操作

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| B17 | 选中回收项 | 有回收项 | 点击 `input[data-recycle-select]` | 计数更新 |
| B18 | 全选回收项 | 有回收项 | 点击 `#recycle-select-all` | 所有回收项选中 |
| B19 | 批量恢复 | 选中多个可恢复项 | 点击 `[data-batch-recycle-action="batch-restore"]` | 确认→toast 成功 |
| B20 | 批量恢复冲突 | 恢复时有冲突 | 冲突弹窗→选择策略 | 按策略处理 |
| B21 | 批量永久清理 | 选中多个 | 点击 `[data-batch-recycle-action="batch-delete"]` | 确认→项消失 |
| B22 | 批量清理-取消 | 选中多个 | 点击清理→取消 | 项仍在 |
| B23 | 0 项选中时按钮 | 无选中 | 查看按钮 | 批量按钮 disabled |

### 3.6 导航与页面切换（test_e2e_05_navigation.py）

| # | 测试项 | 操作 | 验证 |
|---|--------|------|------|
| N01 | 首页导航 | 点击 `[data-nav="dashboard"]` | `.page-view[data-view="dashboard"]` 可见 |
| N02 | 任务页导航 | 点击 `[data-nav="tasks"]` | `.page-view[data-view="tasks"]` 可见 |
| N03 | 回收页导航 | 点击 `[data-nav="recycle"]` | `.page-view[data-view="recycle"]` 可见 |
| N04 | 配置页导航 | 点击 `[data-nav="config"]` | `.page-view[data-view="config"]` 可见 |
| N05 | 高级配置导航 | 配置页点击"高级配置"按钮 | `.page-view[data-view="advanced-config"]` 可见 |
| N06 | 子页切换 | 依次点击 7 个高级配置卡片 | 对应 `data-view` 子页显示 |
| N07 | 返回基础配置 | 从高级配置点击"返回系统配置" | 回到配置步骤页 |
| N08 | 首页快捷入口 | 点击 `#metric-pending` 等指标卡 | 跳转到任务页对应筛选 |
| N09 | 浏览器后退 | 导航后点浏览器后退 | 回到上一页面 |
| N10 | URL 无 hash | 导航到任务页 | URL 不含 `#`（无 hash 路由） |
| N11 | 刷新后页面 | 在任务页刷新 | 页面状态合理（回到 dashboard 或保持） |

### 3.7 视觉与响应式（test_e2e_07_visual.py）

#### 3.7.1 桌面端（1280×900）

| # | 测试项 | 验证 |
|---|--------|------|
| V01 | Dashboard hero 海报可见 | `.film-frame[data-still]` 的 `::before` 有 backgroundImage |
| V02 | 任务页 hero 海报 | `--hero-poster-image` CSS 变量包含 `task-01` |
| V03 | 回收页 hero 海报 | `--hero-poster-image` CSS 变量包含 `recycle-01` |
| V04 | 配置页 hero 海报 | `--hero-poster-image` CSS 变量包含 `settings-01` |
| V05 | 高级子页差异化海报 | 高级子页使用 `still-02` 而非主页面海报 |

#### 3.7.2 移动端（375×812）

| # | 测试项 | 验证 |
|---|--------|------|
| V06 | Dashboard hero 海报隐藏 | `::before` 的 backgroundImage 不含 `url(`（渐变替代） |
| V07 | 任务页 h2 字号缩小 | fontSize ≤ 28px |
| V08 | 无水平滚动 | 所有页面 scrollWidth ≤ clientWidth |
| V09 | 任务卡片单列 | 卡片宽度 ≤ 375px |
| V10 | 批量工具栏换行 | scrollWidth ≤ clientWidth |
| V11 | 模态弹窗适配 | 弹窗 left≥0, right≤375 |
| V12 | 导航栏可用 | 4 个导航项均可点击且激活状态正确 |

### 3.8 流水线细节（test_e2e_08_pipeline.py）— v3 新增

> 本节覆盖归档 TC-02 / TC-04 / TC-05 / TC-06 / TC-07 / TC-08 / TC-09 / TC-10-04 / TC-11 / TC-12 / TC-13 共 11 类流水线边界场景。

#### 3.8.1 源端去重 (SD01-SD04)

> 对应归档 TC-02。同文件重复扫描时，根据内容变化采取不同动作。Playwright 操作 + 后端状态校验。

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| SD01 | 同文件同指纹已成功 | 任务 V01 已 SUCCESS | 重新触发扫描 | 新任务自动 SKIPPED，状态标记为 source_dedup |
| SD02 | 文件名变更但内容不变 | V01 已 SUCCESS，源文件 mtime/内容不变仅重命名 | 修改源文件名为 `Inception.2010.RENAMED.mkv`，重新扫描 | 系统识别为 RENAME_DETECTED，更新 task.filename |
| SD03 | 修改时间变更但内容不变 | V01 已 SUCCESS | `touch -m` 修改 mtime，内容不变，重新扫描 | 识别为 UPDATE_MTIME，更新 task.mtime |
| SD04 | 文件内容变更（指纹不同） | V01 已 SUCCESS | 替换源文件为不同内容的同名文件，重新扫描 | 创建新任务重新处理 |

#### 3.8.2 复制阶段 IO 失败 (CP01-CP02)

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| CP01 | 复制成功-正常路径 | source_dir 可写 | 扫描 V01 | temp_dir 出现 .copying 文件，复制完成后变 .mkv |
| CP02 | 复制 IO 失败 | temp_dir 设为只读目录 / 磁盘满模拟 | 扫描 V01 | 任务 FAILED，错误信息含 IO 错误，源文件保留在 source_dir |

#### 3.8.3 验证环节-字段缺失 (VL01-VL07)

> 对应归档 TC-04。验证刮削结果字段完整性如何影响任务状态。

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| VL01 | 正常通过 | 视频可正常刮削 | 扫描正常视频 | 任务 SUCCESS，无 _needs_confirm |
| VL02 | 缺标题（中英文都无） | mock Provider 返回无标题结果 | 扫描 | `_needs_confirm=True`，进入 CONFIRMING |
| VL03 | 缺类型 | mock 返回无 media_type | 扫描 | `_needs_confirm=True` |
| VL04 | 缺年份（有标题） | mock 返回无 year 但有 title | 扫描 | 警告但可继续，confidence=PASS/CONFIRMING |
| VL05 | 缺年份（无标题） | mock 返回无 year 无 title | 扫描 | `_needs_confirm=True` |
| VL06 | 年份异常 (>2030) | mock 返回 year=2099 | 扫描 | 视为缺失，进入 CONFIRMING |
| VL07 | data_gate 阻断 | mock data_gate=block | 扫描 | 强制 NEEDS_REVIEW，无论 confidence |

#### 3.8.4 分类匹配详细组合 (CL01-CL05)

> 对应归档 TC-05。

| # | 测试项 | 视频 | media_type | 维度 | 预期 |
|---|--------|------|-----------|------|------|
| CL01 | 匹配电影规则 | V01 Inception | movie | 普通 | 入库到 `/影视/电影/2010/...` |
| CL02 | 匹配电视剧规则（含季） | V03 Breaking.Bad S05E16 | tv | 非动漫 | 入库到 `/影视/电视剧/.../Season 05/` |
| CL03 | 匹配动漫规则（优先于电影） | V14 Your.Name | movie | animation | 入库到 `/影视/动漫电影/...` |
| CL04 | 兜底目录 | 任一视频 | 任意 | 无规则匹配 | 入库到 fallback_dir |
| CL05 | 无匹配（无规则+无兜底） | 任一视频 | 任意 | 无规则+fallback_dir 空 | PipelineError，任务 FAILED |

#### 3.8.5 去重策略 × 清理配置 (DP01-DP06)

> 对应归档 TC-06。

| # | 去重结果 | dedup_strategy | 验证点 |
|---|---------|----------------|--------|
| DP01 | 非重复 | 任意 | 正常继续入库 |
| DP02 | 重复-skip | skip | PipelineSkipError，任务 SKIPPED |
| DP03 | 重复-rename | rename | final_filename 被修改，继续入库到新名 |
| DP04 | 重复-replace | replace | 已有文件移入回收站，新文件入库 |
| DP05 | 重复-新更优 | quality | 已有文件移入回收站，新文件替换 |
| DP06 | 重复-旧更优 | quality | PipelineSkipError，保留已有文件 |

#### 3.8.6 入库清理 × 回收站 × 任务结果 (IC01-IC08)

> 对应归档 TC-07。8 种组合完整覆盖。

| # | cleanup_source_after_done | has_recycle_dir | 任务结果 | 验证 |
|---|---------------------------|-----------------|----------|------|
| IC01 | true | 有 | SUCCESS | 源文件移入回收站，temp 文件 rm 删除 |
| IC02 | true | 无 | SUCCESS | 源文件直接 rm 删除，temp 文件 rm 删除 |
| IC03 | true | 有 | FAILED | 源文件保留在 source_dir，temp 文件 rm 删除 |
| IC04 | true | 无 | FAILED | 源文件保留在 source_dir，temp 文件 rm 删除 |
| IC05 | false | 有 | SUCCESS | 源文件保留，file_location=import |
| IC06 | false | 无 | SUCCESS | 源文件保留，file_location=import |
| IC07 | false | 有 | FAILED | 源文件保留，file_location=source |
| IC08 | false | 无 | FAILED | 源文件保留，file_location=source |

#### 3.8.7 file_location 全路径流转 (FL01-FL07)

> 对应归档 TC-12。

| # | 起始位置 | 流转路径 | 触发条件 | 验证 |
|---|---------|----------|----------|------|
| FL01 | source | source→temp→import | 正常入库 | file_location 从 source→temp→import |
| FL02 | source | source→temp→(rm) | 失败/跳过 | temp 文件 rm 删除，源文件保留 |
| FL03 | source | source→recycle | 跳过流程+cleanup=true | 源文件直接移入回收站 |
| FL04 | source | source→source | cleanup=false | 源文件保留不变 |
| FL05 | source | source→deleted | cleanup=true 无回收站 | 源文件 rm 删除 |
| FL06 | recycle | recycle→temp→import | 从回收站重试成功 | file_location 从 recycle→temp→import |
| FL07 | recycle | recycle→recycle | 从回收站重试失败 | 不重复移动，文件位置保持 recycle |

#### 3.8.8 忽略任务 × file_location (IG01-IG06)

> 对应归档 TC-13。

| # | file_location | has_recycle_dir | cleanup_source_after_done | 验证 |
|---|---------------|-----------------|---------------------------|------|
| IG01 | temp | 有 | — | temp 文件 rm 删除，状态 SKIPPED |
| IG02 | temp | 无 | — | temp 文件 rm 删除，状态 SKIPPED |
| IG03 | source | 有 | true | 源文件移入回收站，状态 SKIPPED |
| IG04 | source | 无 | true | 源文件 rm 删除，状态 SKIPPED |
| IG05 | source | 有 | false | 仅更新状态 SKIPPED，源文件保留 |
| IG06 | recycle | 有 | — | 仅更新状态 SKIPPED |

#### 3.8.9 失败→回收→重试 (RL01-RL05)

> 对应归档 TC-08。

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| RL01 | 处理失败-源目录文件 | 视频无法刮削 | 自动处理 | file_location=source，源文件保留 |
| RL02 | 处理失败-回收站文件 | 任务已在回收站 | 自动处理 | file_location=recycle，不重复移动 |
| RL03 | 从回收站重试 | 回收站有失败任务 | 点击 retry_task | 重新处理，状态变为 PROCESSING |
| RL04 | 重试次数超限 | task.retry_count > max_auto_retries | 自动处理 | 不再自动重试，源文件仍在源目录 |
| RL05 | 复制阶段 IO 失败 | 模拟磁盘满 | 扫描 | 任务 FAILED，temp 文件清理 |

#### 3.8.10 API 异常恢复 (ER01-ER04)

> 对应归档 TC-09。LLM/TMDB 保存仍跳过（避免覆盖真实 Key），但**触发的异常处理路径**必须测试。

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| ER01 | TMDB API 超时降级 | TMDB 模拟超时 | 扫描 | 系统降级为纯 AI 模式继续处理 |
| ER02 | LLM API 异常 | LLM 模拟 500 | 扫描 | 任务 FAILED，错误信息含详情，可手动重试 |
| ER03 | TMDB + LLM 都异常 | 两边都 5xx | 扫描 | 任务 FAILED，错误信息含两方异常 |
| ER04 | API 恢复后重试 | 任务 ER03 FAILED | API 恢复后点击 retry_task | 重试成功，状态变为 SUCCESS |

#### 3.8.11 确认流程详细 (CF01-CF04)

> 对应归档 TC-10。补充 manual_review 关闭分支。

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| CF01 | 低置信度进入确认 | manual_review=true，刮削低置信 | 扫描 | 状态 CONFIRMING，file_location=temp |
| CF02 | 确认入库成功 | CONFIRMING 任务 | 点击 confirm_task | 状态 SUCCESS，文件入库 |
| CF03 | 确认入库失败（去重） | CONFIRMING 任务且去重 skip | 点击 confirm_task | 触发去重，状态 SKIPPED |
| CF04 | manual_review 关闭 | manual_review=false | 扫描低置信度视频 | 不进入 CONFIRMING，直接按置信度处理（PASS 入库 / FAILED 入回收） |

#### 3.8.12 重分类流程 (RC01-RL04)

> 对应归档 TC-11。

| # | 测试项 | 前置条件 | 操作 | 验证 |
|---|--------|----------|------|------|
| RC01 | 修改 media_type | SUCCESS 任务，movie→tv | 详情页改维度，点击 reclassify_task | 重新匹配路径规则，入库到新目录 |
| RC02 | 修改维度后去重跳过 | 新路径已有文件 | reclassify_task | 触发去重 skip，新路径未生成新文件 |
| RC03 | 修改维度后无匹配规则 | 修改维度到无规则 | reclassify_task | PipelineError，任务 FAILED |
| RC04 | 修改多个维度 | 同时改 type+region | reclassify_task | 维度合并正确，分类结果按新维度计算 |

### 3.9 源目录清理器（test_e2e_09_source_cleaner.py）— v3 新增

> 对应归档 TC-15 ~ TC-19。源目录清理器独立于任务流水线。

#### 3.9.1 清理模式 (SC01-SC04)

| # | 测试项 | mode | AI辅助 | 验证 |
|---|--------|------|--------|------|
| SC01 | 仅保留影视+字幕 | keep_media_only | false | .url/.txt 等移入回收站，视频/字幕保留 |
| SC02 | 保留影视+相关文件 | keep_media_related | false | .nfo/.jpg 等影视相关文件保留，.url 等移入回收站 |
| SC03 | AI 辅助判断 | keep_media_related | true | 规则无法判定的文件由 AI 决定 |
| SC04 | 规则优先级高于 AI | keep_media_related | true | 规则明确判定的文件按规则处理，不走 AI |

#### 3.9.2 垃圾视频阈值 (SC05-SC07)

| # | 测试项 | 阈值 | 文件 | 验证 |
|---|--------|------|------|------|
| SC05 | Sample 文件识别 | 50MB | `Sample/sample.mp4` (1MB) | 移入回收站 |
| SC06 | 正常视频保留 | 50MB | `Movie.2020.mkv` (2GB) | 保留 |
| SC07 | 阈值为 0 | 0 | 任意小视频 | 不检测视频大小，仅按后缀名规则判断 |

#### 3.9.3 黑名单与保护 (SC08-SC11)

| # | 测试项 | 配置 | 验证 |
|---|--------|------|------|
| SC08 | 黑名单匹配 | blacklist_patterns 含 `RARBG*` | RARBG 开头的文件移入回收站 |
| SC09 | 删除后缀名 | delete_extensions 含 `.url` | .url 文件移入回收站 |
| SC10 | 保护后缀名 | protect_extensions 含 `.nfo` | .nfo 文件在 keep_media_related 模式下保留 |
| SC11 | 已关联任务保护 | 任务表中有对应记录 | 已关联任务的视频/字幕文件不被清理 |

#### 3.9.4 确认模式与空目录 (SC12-SC15)

| # | 测试项 | 配置 | 验证 |
|---|--------|------|------|
| SC12 | 需确认模式 | confirm_before_cleanup=true | 生成清理列表等待用户确认，不自动执行 |
| SC13 | 自动执行 | confirm_before_cleanup=false | 直接执行清理，移入回收站 |
| SC14 | 空目录清理 | cleanup_empty_dirs=true | 文件清理后空目录被删除 |
| SC15 | 空目录保留 | cleanup_empty_dirs=false | 文件清理后空目录保留 |

#### 3.9.5 与任务流的隔离 (SC16-SC18)

| # | 测试项 | 验证 |
|---|--------|------|
| SC16 | 清理器不影响任务流 | 清理器执行时，正在处理的任务不受影响 |
| SC17 | 任务流不影响清理器 | 任务完成后 cleanup_source_after_done 的清理与清理器独立 |
| SC18 | 清理器禁用 | source_cleaner.enabled=false，清理器不执行，任务流正常 |

### 3.10 回归矩阵（test_e2e_10_regression.py）— v3 新增

> 对应归档 RT-01 ~ RT-05。每次发版必跑。Playwright 跑完整链路，断言状态机、文件位置、目录结构。

#### 3.10.1 主流程回归 (RT-01)

| # | 场景 | 优先级 |
|---|------|--------|
| RT-01-01 | 电影正常入库 (scan→copy→scrape→validate→classify→dedup→rename→import→notify→record) | P0 |
| RT-01-02 | 电视剧正常入库，同上 media_type=tv | P0 |
| RT-01-03 | 带字幕入库 | P0 |
| RT-01-04 | 保留源文件入库 (cleanup=false) | P1 |

#### 3.10.2 异常恢复回归 (RT-02)

| # | 场景 | 优先级 |
|---|------|--------|
| RT-02-01 | 失败→源文件保留 | P0 |
| RT-02-02 | 回收站重试 (retry_task) | P0 |
| RT-02-03 | 确认入库 (CONFIRMING→confirm_task→SUCCESS) | P1 |
| RT-02-04 | 重分类入库 (reclassify_task→新路径) | P1 |

#### 3.10.3 去重策略回归 (RT-03)

| # | 场景 | 策略 | 优先级 |
|---|------|------|--------|
| RT-03-01 | 重复-skip | skip | P0 |
| RT-03-02 | 重复-rename | rename | P1 |
| RT-03-03 | 重复-replace | replace | P1 |
| RT-03-04 | 重复-quality(新更优) | quality | P1 |
| RT-03-05 | 重复-quality(旧更优) | quality | P1 |

#### 3.10.4 源端去重回归 (RT-04)

| # | 场景 | 动作 | 优先级 |
|---|------|------|--------|
| RT-04-01 | 同文件重复扫描 | SKIP | P0 |
| RT-04-02 | 文件重命名 | RENAME_DETECTED | P1 |
| RT-04-03 | 文件修改时间变化 | UPDATE_MTIME | P1 |
| RT-04-04 | 文件内容变化 | REPROCESS | P0 |

#### 3.10.5 配置兼容性回归 (RT-05)

| # | 场景 | 优先级 |
|---|------|--------|
| RT-05-01 | cleanup_mode 自动迁移（迁移到 cleanup_source_after_done） | P0 |
| RT-05-02 | delete_source_after_import 自动迁移 | P0 |
| RT-05-03 | smart_cleanup 自动迁移到顶层 source_cleaner | P1 |
| RT-05-04 | API 返回新配置结构（含 cleanup_source_after_done） | P1 |
| RT-05-05 | 前端无旧文案（不显示 cleanup_mode/delete_source_after_import） | P1 |

### 3.11 笛卡尔补充（test_e2e_11_cartesian_extra.py）— v3 新增

> 对应归档 TC-14。25 个笛卡尔补充场景。每个测试单独跑一组配置 + 视频组合，验证状态/文件位置/目录结构。

#### 3.11.1 刮削×置信度×分类 (CX28-CX35)

| # | scrape | confidence | classify | 验证 |
|---|--------|------------|----------|------|
| CX28 | Provider+AI | CONFIRMING | 兜底目录 | 确认后入库到兜底路径 |
| CX29 | Provider+AI | CONFIRMING | 失败 | 确认时仍失败 |
| CX30 | Provider+AI | NEEDS_REVIEW | 兜底目录 | 审核通过后入库 |
| CX31 | Provider+AI | NEEDS_REVIEW | 失败 | 无法入库 |
| CX32 | 纯AI | PASS | 兜底目录 | 纯AI高置信+兜底 |
| CX33 | 纯AI | PASS | 失败 | 纯AI高置信+无规则 |
| CX34 | 纯AI | CONFIRMING | 兜底目录 | 纯AI低置信+兜底 |
| CX35 | 纯AI | CONFIRMING | 失败 | 纯AI低置信+无匹配 |

#### 3.11.2 去重×清理配置×回收站 (CX36-CX45)

| # | dedup | cleanup | recycle | 验证 |
|---|-------|---------|---------|------|
| CX36 | skip | true | 无 | 去重跳过+无回收站，源文件 rm 删除 |
| CX37 | skip | false | — | 去重跳过+保留源文件 |
| CX38 | rename | true | 无 | 去重重命名+无回收站 |
| CX39 | rename | false | — | 去重重命名+保留源文件 |
| CX40 | replace | true | 无 | 去重替换+无回收站，已有文件 rm 删除 |
| CX41 | replace | false | — | 去重替换+保留源文件 |
| CX42 | quality保留 | true | 无 | 质量保留+无回收站 |
| CX43 | quality保留 | false | — | 质量保留+保留源文件 |
| CX44 | quality替换 | true | 无 | 质量替换+无回收站 |
| CX45 | quality替换 | false | — | 质量替换+保留源文件 |

#### 3.11.3 任务结果×文件位置×回收站 (CX46-CX52)

| # | 任务结果 | file_location | recycle | 验证 |
|---|---------|---------------|---------|------|
| CX46 | FAILED | temp | 有 | 处理中失败，temp 文件 rm 删除，源文件保留 |
| CX47 | FAILED | temp | 无 | 处理中失败，temp 文件 rm 删除，源文件保留 |
| CX48 | SKIPPED | source | 无 | 跳过+无回收，cleanup=true 时源文件 rm 删除 |
| CX49 | SKIPPED | temp | 有 | 跳过+temp 文件 rm 删除 |
| CX50 | SKIPPED | temp | 无 | 跳过+temp 文件 rm 删除 |
| CX51 | SKIPPED | recycle | — | 跳过+回收站文件，不重复移动 |
| CX52 | CONFIRMING | source | 有 | 确认状态+源目录文件 |

---

## 4. 笛卡尔组合测试

### 4.1 清理模式 × 视频类型 × 任务结果

| 清理模式 | 视频类型 | 任务结果 | 测试 ID | 验证点 |
|----------|----------|----------|---------|--------|
| read_only | movie | SUCCESS | CX01 | 源文件不删除 |
| read_only | movie | FAILED | CX02 | 源文件保留 |
| read_only | tv | SUCCESS | CX03 | 源文件不删除 |
| read_only | tv | FAILED | CX04 | 源文件保留 |
| smart_cleanup | movie | SUCCESS | CX05 | 清理关联文件（字幕等） |
| smart_cleanup | movie | FAILED | CX06 | 源文件保留 |
| smart_cleanup | tv | SUCCESS | CX07 | 清理关联文件 |
| smart_cleanup | tv | FAILED | CX08 | 源文件保留 |
| full_cleanup | movie | SUCCESS | CX09 | 源文件移入回收站 |
| full_cleanup | movie | FAILED | CX10 | 源文件保留（未超限） |
| full_cleanup | tv | SUCCESS | CX11 | 源文件移入回收站 |
| full_cleanup | tv | FAILED | CX12 | 源文件保留（未超限） |

### 4.2 人工确认 × 置信度区间 × 用户操作

| manual_review | 置信度区间 | 用户操作 | 测试 ID |
|---------------|-----------|----------|---------|
| enabled | ≥ pass_threshold | 自动入库 | CX13 |
| enabled | confirm ~ pass | CONFIRMING → 确认 | CX14 |
| enabled | confirm ~ pass | CONFIRMING → 忽略 | CX15 |
| enabled | < review_threshold | CONFIRMING → 重命名后确认 | CX16 |
| disabled | ≥ pass_threshold | 自动入库 | CX17 |
| disabled | < pass_threshold | FAILED | CX18 |

### 4.3 重复文件策略 × 文件质量差异

| dedup_strategy | 已存在文件 | 新文件 | 预期结果 | 测试 ID |
|----------------|-----------|--------|----------|---------|
| skip | 1080p | 720p | 跳过新文件 | CX19 |
| replace | 720p | 1080p | 新文件替换旧文件 | CX20 |
| rename | 1080p | 1080p | 两者都保留 | CX21 |
| quality | 720p | 1080p | 保留 1080p | CX22 |
| quality | 1080p 2GB | 1080p 1GB | 保留 1GB | CX23 |

### 4.4 回收恢复冲突模式

| conflict_mode | 源位置状态 | 预期结果 | 测试 ID |
|---------------|-----------|----------|---------|
| skip | 同名文件存在 | 跳过，不覆盖 | CX24 |
| overwrite | 同名文件存在 | 新文件覆盖旧文件 | CX25 |
| rename | 同名文件存在 | 新文件添加编号后缀 | CX26 |
| skip | 源位置为空 | 正常恢复 | CX27 |

---

## 5. 全流程端到端测试（完整链路）

### E2E-01：电影入库完整流程

```
配置源目录 → 扫描 → 任务创建 → 刮削(PENDING→PROCESSING) → 分类 → 入库(SUCCESS)
→ 验证源文件处理（按清理模式）→ 验证入库目录结构 → 验证文件名格式
```

### E2E-02：电视剧入库完整流程

```
配置源目录 → 扫描 → 多集任务创建 → 逐集刮削 → 分类 → 入库
→ 验证 Season 文件夹结构 → 验证集号格式
```

### E2E-03：低置信度人工确认流程

```
启用 manual_review → 扫描 → 刮削置信度低 → CONFIRMING
→ 用户查看详情 → 修改维度 → 应用分类微调 → 确认入库
```

### E2E-04：失败重试→回收→恢复流程

```
扫描 → 刮削失败 → FAILED → 重试仍失败 → 超限移入回收
→ 回收站查看 → 恢复文件 → 重新扫描 → 成功入库
```

### E2E-05：批量操作完整流程

```
扫描多个文件 → 多个 FAILED → 批量重试 → 部分成功
→ 选中剩余 FAILED → 批量移入回收 → 回收站批量清理
```

### E2E-06：配置变更影响流程

```
初始配置 → 扫描入库 → 修改路径规则 → 重新扫描
→ 验证新规则生效 → 修改维度启停 → 验证分类变化
```

---

## 6. 测试统计

### 6.1 v2 已含

| 类别 | 测试数 |
|------|--------|
| Bug 修复验证 (C00) | 1 |
| 基础目录配置 (C01-C10) | 10 |
| 源策略配置 (C11-C17) | 7 |
| LLM 配置 (C18-C21, 跳过 C22-C23) | 4 |
| TMDB Provider (C24-C25, 跳过 C26-C28) | 2 |
| 入库规则 (C29-C32) | 4 |
| 入库名称规范 (C33-C39) | 7 |
| 影视分类维度 (C40-C45) | 6 |
| AI刮削提示词 (C46-C54) | 9 |
| 置信度计算 (C55-C61) | 7 |
| 安全配置 (C62-C65) | 4 |
| Hermes 通知 (C66-C72) | 7 |
| 系统设置 (C73-C79) | 7 |
| 扫描触发 (S01-S04) | 4 |
| 任务状态转换 (T01-T09) | 9 |
| 视频类型识别 (ST01-ST05) | 5 |
| 单任务操作 (A01-A13) | 13 |
| 筛选导航 (A14-A20) | 7 |
| 回收站基础 (R01-R07) | 7 |
| 回收站冲突 (R08-R10) | 3 |
| 任务批量 (B01-B16) | 16 |
| 回收站批量 (B17-B23) | 7 |
| 页面导航 (N01-N11) | 11 |
| 视觉响应式 (V01-V12) | 12 |
| 笛卡尔组合 (CX01-CX27) | 27 |
| 端到端链路 (E2E-01~06) | 6 |
| **v2 小计** | **202** |

### 6.2 v3 新增

| 类别 | 测试数 |
|------|--------|
| 源端去重 (SD01-SD04) | 4 |
| 复制 IO 失败 (CP01-CP02) | 2 |
| 验证字段缺失 (VL01-VL07) | 7 |
| 分类匹配详细 (CL01-CL05) | 5 |
| 去重策略 × 清理配置 (DP01-DP06) | 6 |
| 入库清理 × 回收站 × 结果 (IC01-IC08) | 8 |
| file_location 流转 (FL01-FL07) | 7 |
| 忽略任务 × file_location (IG01-IG06) | 6 |
| 失败→回收→重试 (RL01-RL05) | 5 |
| API 异常恢复 (ER01-ER04) | 4 |
| 确认流程详细 (CF01-CF04) | 4 |
| 重分类流程 (RC01-RC04) | 4 |
| 源目录清理器-清理模式 (SC01-SC04) | 4 |
| 源目录清理器-垃圾视频阈值 (SC05-SC07) | 3 |
| 源目录清理器-黑名单保护 (SC08-SC11) | 4 |
| 源目录清理器-确认与空目录 (SC12-SC15) | 4 |
| 源目录清理器-任务流隔离 (SC16-SC18) | 3 |
| 回归矩阵-主流程 (RT-01-01~04) | 4 |
| 回归矩阵-异常恢复 (RT-02-01~04) | 4 |
| 回归矩阵-去重策略 (RT-03-01~05) | 5 |
| 回归矩阵-源端去重 (RT-04-01~04) | 4 |
| 回归矩阵-配置兼容 (RT-05-01~05) | 5 |
| 笛卡尔补充-刮削×置信×分类 (CX28-CX35) | 8 |
| 笛卡尔补充-去重×清理×回收 (CX36-CX45) | 10 |
| 笛卡尔补充-结果×位置×回收 (CX46-CX52) | 7 |
| **v3 新增小计** | **127** |

### 6.3 总计

> 注：v2 计划文档原本声明小计 184，实际按行累加为 202；本表按真实条数修正。

| 大类 | 测试数 |
|------|--------|
| 配置 (C00-C79) | 75 |
| 扫描/任务 (S/T/ST) | 18 |
| 任务操作/筛选 (A01-A20) | 20 |
| 回收站 (R01-R10) | 10 |
| 批量 (B01-B23) | 23 |
| 导航 (N01-N11) | 11 |
| 视觉响应式 (V01-V12) | 12 |
| 笛卡尔组合 (CX01-CX27) | 27 |
| 端到端链路 (E2E-01~06) | 6 |
| 流水线细节 (SD/CP/VL/CL/DP/IC/FL/IG/RL/ER/CF/RC) | 62 |
| 源目录清理器 (SC01-SC18) | 18 |
| 回归矩阵 (RT-01~05) | 22 |
| 笛卡尔补充 (CX28-CX52) | 25 |
| **总计** | **329** |

---

## 7. 实施约束

1. **所有测试通过 Playwright 执行**：全部通过真实 UI 交互触发，不使用 mock
2. **测试数据隔离**：每轮测试使用独立的 `/tmp/nas_media_e2e_{run_id}/` 目录
3. **服务自启动**：复用 `start_server` 模式，不依赖外部服务
4. **LLM / TMDB 使用真实 API**：API Key 由人工提前录入，测试中不执行保存/修改/禁用操作
5. **LLM / TMDB 配置测试跳过保存**：C22-C23、C26-C28 标记为跳过
6. **截图归档**：每个测试结束自动截图到 `tests/screenshots/`
7. **测试顺序**：按文件编号顺序执行，配置测试先行
8. **超时设置**：刮削测试使用 180 秒超时，适应真实 API 调用延迟
9. **条件跳过**：依赖特定状态（FAILED/CONFIRMING）的测试在条件不满足时 `pytest.skip`
