# 维度体系扩展 — 全场景全流程测试方案

## 测试目标

验证维度体系扩展后，从维度配置 → 刮削 → 分类 → 入库的完整链路正确性。

## 测试环境

- 部署环境：fnOS NAS 或开发机
- 依赖：ffprobe 可用、TMDB API Key 已配置、LLM API Key 已配置
- 测试视频文件：至少 5 个不同类型的视频文件

## 测试用例

### TC-01: 数据库维度 Seed 数据验证

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 删除旧数据库文件 | - |
| 2 | 启动服务（触发 init_db） | 服务正常启动 |
| 3 | GET /api/dimensions | 返回 8 个维度 |
| 4 | 检查 is_enabled | media_type=1, documentary=1, restricted_level=1, 其余=0 |
| 5 | 检查 value_list JSON 格式 | 每个维度的 value_list 是合法 JSON 数组 |
| 6 | 检查 broad_genre 的 tmdb_genre_ids | 包含正确的 TMDB genre ID |
| 7 | 重启服务 | dimensions 表数据不变（seed 不覆盖） |

### TC-02: 维度启用/禁用

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | POST /api/dimensions/animation/enable | 成功，animation is_enabled=1 |
| 2 | GET /api/dimensions/enabled | 返回 4 个维度（含 animation） |
| 3 | POST /api/dimensions/animation/disable | 成功，animation is_enabled=0 |
| 4 | GET /api/dimensions/enabled | 返回 3 个维度（不含 animation） |
| 5 | 禁用 media_type | 成功（系统维度可禁用但不可删除） |

### TC-03: 维度编辑

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | PUT /api/dimensions/documentary（修改 ai_prompt） | 成功保存 |
| 2 | GET /api/dimensions/documentary | ai_prompt 为修改后的值 |
| 3 | PUT /api/dimensions/region（修改 value_list 映射） | 成功保存 |
| 4 | GET /api/dimensions/region | value_list 为修改后的映射 |

### TC-04: TMDB 维度映射 — region

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 启用 region 维度 | - |
| 2 | 刮削日本动漫文件 | region="asia" |
| 3 | 刮削美国电影文件 | region="western" |
| 4 | 刮削法国电影文件 | region="european" |
| 5 | 刮削印度电影文件 | region="other" |
| 6 | 修改 region 映射（将 IN 加入 asian） | 印度电影 region="asia" |

### TC-05: TMDB 维度映射 — origin_lang

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 启用 origin_lang 维度 | - |
| 2 | 刮削中文电影 | origin_lang="zh" |
| 3 | 刮削英文电影 | origin_lang="en" |
| 4 | 刮削日文动漫 | origin_lang="ja" |
| 5 | 刮韩剧 | origin_lang="ko" |

### TC-06: TMDB 维度映射 — broad_genre

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 启用 broad_genre 维度 | - |
| 2 | 刮削恐怖片（TMDB genres: [Horror, Comedy]） | broad_genre="horror"（优先级最高） |
| 3 | 刮削科幻片（TMDB genres: [Drama, Sci-Fi]） | broad_genre="scifi" |
| 4 | 刮削动作片（TMDB genres: [Action, Thriller]） | broad_genre="action" |
| 5 | 刮削爱情片（TMDB genres: [Romance, Drama]） | broad_genre="drama" |
| 6 | 刮削纪录片（TMDB genres: [Documentary]） | broad_genre="other" |

### TC-07: 文件推导维度 — resolution_tier

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 启用 resolution_tier 维度 | - |
| 2 | 刮削 4K 视频文件（3840x2160） | resolution_tier="4k" |
| 3 | 刮削 1080p 视频文件（1920x1080） | resolution_tier="1080p" |
| 4 | 刮削 720p 视频文件（1280x720） | resolution_tier="720p" |
| 5 | 刮削 SD 视频文件（720x480） | resolution_tier="sd" |
| 6 | ffprobe 不可用时 | resolution_tier 为空，不影响其他维度 |

### TC-08: AI 提示词动态化

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 只启用 3 个默认维度 | AI 提示词只包含 3 个维度 |
| 2 | 启用 animation | AI 提示词包含 4 个维度 |
| 3 | TMDB 命中后 | AI 提示词排除 TMDB 已确定的维度 |
| 4 | 修改 documentary 的 ai_prompt | 刮削时使用新提示词 |

### TC-09: 前端维度配置页签

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 打开配置 → 维度配置页签 | 显示 3 个已启用 + 5 个可添加 |
| 2 | 点击 animation 的"添加" | animation 移到已启用列表 |
| 3 | 点击 documentary 的"编辑" | 展开编辑面板，显示 AI 提示词 |
| 4 | 修改 AI 提示词并保存 | 保存成功提示 |
| 5 | 点击 region 的"添加" | 显示 PRO 标签（当前放行） |
| 6 | 点击 documentary 的"禁用" | documentary 移回可添加列表 |
| 7 | 展开 region 映射配置 | 显示国家代码映射表 |

### TC-10: 入库规则页签维度联动

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 只启用 3 个默认维度 | 入库规则条件选择器只有 3 个维度 |
| 2 | 启用 region | 入库规则条件选择器新增 region |
| 3 | 添加条件选择 region | 下拉框显示 asia/western/european/other |
| 4 | 禁用 region | 已有规则中 region 条件高亮警告 |

### TC-11: 任务列表维度标签

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 刮削一个文件（3 个默认维度） | 任务卡片显示 3 个维度标签 |
| 2 | 启用 animation + region | 重新刮削，任务卡片显示 5 个维度标签 |
| 3 | 检查维度颜色 | 颜色与 dimensions 表 color 字段一致 |
| 4 | 禁用 region | 任务卡片不再显示 region 标签 |

### TC-12: 端到端全流程

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 启用所有 8 个维度 | - |
| 2 | 配置 path_rules 使用新维度 | - |
| 3 | 放入测试视频文件到源目录 | - |
| 4 | 触发批量扫描 | 文件进入流水线 |
| 5 | 验证 file_analyzer 填充 resolution_tier | 正确 |
| 6 | 验证 TMDB 填充 region/origin_lang/broad_genre | 正确 |
| 7 | 验证 AI 填充 documentary/animation/restricted_level | 正确 |
| 8 | 验证 classifier 匹配 path_rules | 正确 |
| 9 | 验证文件入库到正确目录 | 正确 |
| 10 | 验证任务详情中维度值完整 | 8 个维度都有值 |

### TC-13: 降级场景

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | TMDB 未启用 | 所有维度走 AI 判断 |
| 2 | TMDB 启用但未命中 | TMDB 类型维度走 AI 兜底 |
| 3 | ffprobe 不可用 | resolution_tier 为空，其他维度正常 |
| 4 | AI 刮削失败 | 任务标记 FAILED，维度值不完整 |

### TC-14: 浏览器全场景测试

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 浏览器打开 Web UI | 页面正常加载 |
| 2 | 切换到维度配置页签 | 页签内容正确渲染 |
| 3 | 启用/禁用维度 | UI 实时更新 |
| 4 | 编辑 AI 提示词 | 保存成功 |
| 5 | 编辑映射规则 | 保存成功 |
| 6 | 切换到入库规则页签 | 维度条件选择器反映最新启用状态 |
| 7 | 添加/编辑入库规则 | 维度下拉框正确 |
| 8 | 触发刮削任务 | 任务列表显示 |
| 9 | 查看任务详情 | 维度标签正确渲染（颜色+标签） |
| 10 | 重新分类 | 维度输入框正确 |

## 测试执行顺序

1. **Phase 1 测试**：TC-01 ~ TC-03（数据库 + API）✅ 单元测试已覆盖
2. **Phase 2 测试**：TC-04 ~ TC-08（后端刮削链路）— 需部署后测试
3. **Phase 3-4 测试**：TC-09 ~ TC-11（前端 UI）— 需浏览器测试
4. **Phase 5 测试**：TC-12 ~ TC-13（端到端 + 降级）— 需部署后测试
5. **最终测试**：TC-14（浏览器全场景）— 需浏览器测试

## 缺陷报告模板

```
缺陷 ID: BUG-DIM-XXX
测试用例: TC-XX
严重程度: P0(阻塞) / P1(严重) / P2(一般) / P3(轻微)
重现步骤:
  1. ...
  2. ...
预期结果: ...
实际结果: ...
环境信息: (fnOS版本/浏览器/ffprobe版本)
```

## 测试通过标准

- P0 缺陷：0 个
- P1 缺陷：0 个
- P2 缺陷：≤ 3 个（需记录但可后续修复）
- P3 缺陷：不限（记录即可）
- 所有 TC-01 ~ TC-14 测试用例执行完毕
- 端到端全流程（TC-12）至少通过 2 个不同类型的视频文件
