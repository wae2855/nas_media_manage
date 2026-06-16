# 开发交接提示词

**任务**：执行 `docs/plans/2026-06-16-scrape-info-responsibility-split-plan.md` 中描述的全部 Phase。  
**预估**：约 24 小时，分 15 个 Phase（A-N + P/Q/R）。  
**仓库**：`/Users/wangwei/Documents/code/nas_media_manage`

---

## 你的角色

你是一名**执行型开发者**。计划文档已经设计好所有架构决策、字段定义、提示词、测试边界。你的职责是：

✅ **按计划逐步实施**，每个 Phase 完成后跑测试验证  
✅ **遇到歧义停止并问**，不要自己拍板  
✅ **每个 Phase 单独提交**，提交信息格式 `Phase X: 简述`  
✅ **修改前先读相关文件**，理解上下文  

❌ **不要做架构决策**（如改字段名、改枚举值、调整 Phase 顺序）  
❌ **不要删除计划外的代码**（除非计划明确要求）  
❌ **不要跳过测试**（每个 Phase 都有验证清单）  
❌ **不要修改 `docs/` 目录的文档**（除了标记完成状态）

---

## 硬性规则

### 1. 测试先行
- 每个 Phase 完成后**必须**运行测试：`python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"`
- 测试通过才能进入下一 Phase
- 新增功能必须同步写单元测试（计划里已给测试用例）

### 2. 文件操作规范
- **修改前必须先读文件**（用 Read 工具）
- **优先用 edit 工具**做精确替换，不要用 write 重写整个文件
- **复杂改动用 morph_edit**（多个分散位置）
- **新建文件用 write**

### 3. Python 缓存陷阱（重要！）
本项目用 `.pyc` 缓存，改了代码但服务器没重启会看到旧行为。**每次改 Python 代码后**：

```bash
# 清缓存 + 重启服务器
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
```

### 4. 提交规范
- 每个 Phase 单独提交
- 提交信息：`Phase X: 简述（如 "Phase A: 新建 match_enums.py 枚举定义"）`
- 不要批量提交多个 Phase

### 5. LSP 错误处理
本项目有**既有的 LSP 类型错误**（如 `scenario: str` 接收 None、mixin 类属性未声明）。这些是**已有的技术债**，不要修。只关注你**新增代码**引入的 LSP 错误。

---

## 实施顺序（严格按此顺序）

### 阶段 1：数据模型基础（Phase A → B → C）

#### Phase A：新建枚举文件
**文件**：`media_importer/features/scraping/match_enums.py`（新建）  
**内容**：完全照抄计划文档 2.1 节的代码。

**验证**：
```bash
python -c "from media_importer.features.scraping.match_enums import TierShortReason, WhySelected, MatchTier; print('OK')"
```

#### Phase B：扩展 MatchResult dataclass
**文件**：`media_importer/features/scraping/match_models.py`  
**改动**：
1. 新建 `SelectedCandidate` dataclass（照抄计划 2.2）
2. `MatchResult` 新增 3 个字段：`tier_short_reason` / `ai_reason` / `selected_candidate`
3. `to_dict()` 输出新字段，**不再输出 `confirm_reason`**
4. **保留** `confirm_reason` 字段定义（避免编译错误），但默认空字符串

**验证**：写 `tests/test_match_result_fields.py`（计划 6.1 节），运行通过。

#### Phase C：Tier 1/2/3 字段生成
**文件**：`media_importer/features/scraping/_match_tiers_impl.py`  
**改动**：按计划 3.1 / 3.2 / 3.3 节，在每个 `MatchResult(...)` 构造点添加新字段。

**关键点**：
- 所有 `confirm_reason="..."` 改为 `confirm_reason=""`（不再赋值）
- `tier_short_reason` 用 `TierShortReason` 枚举
- `selected_candidate` 用 `SelectedCandidate(...)` 构造

**验证**：跑全部测试，已有 tier2 测试可能失败（因为 confirm_reason 不再输出），按需更新测试断言。

### 阶段 2：后端流程改造（Phase D → E → F）

#### Phase D：AI 提示词改造
**文件**：`media_importer/scraper/_llm_match_assist.py`  
**改动**：按计划 3.4 节修改 `_tier2_correct_impl`：
1. `user_parts` 新增 `short_reason` 字段说明
2. 解析时 `result.setdefault("short_reason", "")`
3. 兜底截断到 30 字

**注意**：Phase P 会进一步大改提示词，但 Phase D 先做基础 short_reason 支持。

#### Phase E：正式流程清理
**文件**：
- `media_importer/features/import_flow/steps/scrape.py`（删 ~L313 confirm_reason 追加）
- `media_importer/features/import_flow/steps/review.py`（删所有 confirm_reason 覆盖）
- `media_importer/features/import_flow/runner.py`（删 ~L169 默认 confirm_reason）

**改动原则**：把这些地方拼 `confirm_reason` 的代码删除，改为往 `concerns[]` 追加 `MatchConcern`。

#### Phase F：scrape_preview_job.py 透传
**文件**：`media_importer/api/scrape_preview_job.py`  
**改动**：所有 7 处构造 `scrape_result` 的位置，加 3 个新字段透传，删除 `confirm_reason` 输出。

**删除函数**：`_confirm_reason_from_match`（~L39-56）。

### 阶段 3：前端基础（Phase G）

#### Phase G：新建装配器
**文件**：`media_importer/webui/js/build-match-path-data.js`（新建）  
**内容**：完全照抄计划 4.1 节代码。

**index.html 引入**：在 `cinema-config-simulator.js` 之前加 `<script src="js/build-match-path-data.js?v=1"></script>`

### 阶段 4：候选数据完整性（Phase M → N，依赖 Phase A-C）

#### Phase M：Tier 1 候选保留
**文件**：`media_importer/features/scraping/_match_tiers_impl.py` + `match_engine.py`  
**改动**：
1. `MatchEngine.__init__` 加 `self._pending_candidates = []`
2. `_tier1_exact_match_impl` 多匹配分支保存候选到 `self._pending_candidates`
3. `_tier2_context_match_impl` 把 `self._pending_candidates` 传给子函数
4. 子函数优先用 Tier 1 候选过滤，空则搜 Provider

#### Phase N：候选补可信度字段
**文件**：`media_importer/features/scraping/_match_tiers_impl.py`  
**改动**：`_search_providers_impl` 候选字典加 `vote_average` / `vote_count` / `popularity`。`year` 兜底从 `raw_data["release_date"]` 提取。同步修改 AUTO_PASS 候选和评分打破候选。

### 阶段 5：AI 提示词大改（Phase P，依赖 Phase M/N）

#### Phase P：完整提示词重设计
**文件**：`media_importer/scraper/_llm_match_assist.py`  
**改动**：按计划 10.1.3 节完整替换 `user_parts`，按 10.1.4 节扩展解析逻辑。

**关键**：
- 渲染 Step 1 候选列表（含评分/热度/id）
- 新增 `is_valid` / `selected_candidate_id` 字段
- 防御性兜底（is_valid=false 清空其他字段）

### 阶段 6：业务语义变更（Phase Q，依赖 Phase P）

#### Phase Q：FAILED 状态
**文件**：
- `_match_tiers_impl.py`：`_tier2_context_match_impl` 新增 is_valid=false 分支返回 `match_level="FAILED"`
- `_tier2_high/medium_certainty_impl`：支持 `selected_candidate_id` 参数
- `runner.py`：处理 `match_level="FAILED"` → 任务状态置 FAILED
- `scrape_preview_job.py`：新增 FAILED 分支提前返回

**验证**：用 `123uyyt.mkv` 测试，应得到 match_level=FAILED。

### 阶段 7：前端视图改造（Phase H → I → J → K → L → O，依赖 Phase G）

#### Phase H：列表行 tier_short_reason
**文件**：`media_importer/webui/js/tasks-list.js`  
**改动**：`buildScrapeCell()` 新增 L2 一句话原因显示。

#### Phase I：任务卡片重写
**文件**：`media_importer/webui/js/cinema-task-list.js`  
**改动**：完全重写 `renderTaskScrapeProcess`，按计划 4.3 节实现 AI 怎么说 / 最终用了 / 维度三块。

#### Phase J：任务详情复用装配器
**文件**：`media_importer/webui/js/cinema-task-detail.js`  
**改动**：`buildScrapeTraceSection` 改用 `buildMatchPathData`；`taskToMatchPathData` 改为调用 `buildMatchPathData`。

#### Phase K：追踪弹窗字段名修复
**文件**：`media_importer/webui/js/match-trace-detail.js`  
**改动**：~L210 把 `step.result || step.message` 改为 `step.reason || step.ai_reason || step.result || step.message`。

#### Phase L：模拟器适配
**文件**：`media_importer/webui/js/cinema-config-simulator.js`  
**改动**：
1. `explainSimulatedQueue` 优先用 `tier_short_reason`
2. 删除 `preview_selected_candidate` 逻辑，改读 `selected_candidate.why_selected`

#### Phase O：候选列表展示可信度
**文件**：`media_importer/webui/js/cinema-config-simulator.js` + `match-trace-detail.js`  
**改动**：候选列表按 popularity 排序，显示 ⭐评分、票数、热度。

### 阶段 8：失败任务 UX（Phase R，依赖 Phase Q）

#### Phase R：前端失败任务交互
**文件**：
- `cinema-task-list.js`：新增 `renderFailedTaskBlock`
- `cinema-task-utils.js`：新增 `rescrapeTask`
- `task_handlers.py`：新增 `POST /api/tasks/{id}/rescrape` 端点

### 阶段 9：清理（最后做）

#### Phase 5.1：confirm_reason 全清理
**命令**：
```bash
grep -rn "confirm_reason" media_importer/ --include="*.py" --include="*.js"
```

把所有引用逐个删除。后端 `MatchResult.confirm_reason` 字段定义保留（避免编译错误），但所有赋值点改为 `""`，`to_dict()` 不输出。

---

## 关键设计决策（不要偏离）

### 1. is_valid 判定边界（Phase P 核心）

| 文件名示例 | is_valid | 理由 |
|-----------|:---:|------|
| `123uyyt.mkv` | false | 随机字符 |
| `消防员.mkv`（候选 5 部同名） | false | 通用词歧义 |
| `消防员.mkv`（候选唯一⭐7+） | true | 候选确定 |
| `泰坦尼克号.mkv` | true | 知名片名 |
| `Movie.2023.mkv` | false | 占位词 |
| `美丽人生.mkv` | true | 同名多版但片名明确 |

**候选数量规则**：≥3 部同名 → 倾向 false；唯一且高分 → 倾向 true。

### 2. 字段语义（不要混淆）

- `match_level`：`AUTO_PASS` / `CONTEXT_PASS` / `NEEDS_CONFIRM` / `FAILED`
- `match_tier`：1（Provider）/ 2（AI）/ 3（AI 不可用降级）
- `certainty`：`high` / `medium`（`low` 不应出现，兜底为 medium）
- `is_valid`：`true` / `false`（false 时其他字段全空）
- `why_selected`：`unique_match` / `top_rated` / `ai_suggestion` / `first_candidate` / `user_pick`

### 3. 前后端字段一致性

`scrape_preview_job.py` 和 `scrape.py` 必须输出**完全相同**的 `scrape_result` 字段结构。前端 `buildMatchPathData` 是唯一装配器，不要在各视图里自己拼。

---

## 测试命令速查

```bash
# 全部非 UI 测试（每个 Phase 完成后跑）
python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"

# 单个测试文件
python -m pytest tests/test_match_result_fields.py -q

# 架构守卫
python -m pytest tests/test_architecture_guards.py -q

# 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
```

---

## 验收场景（最终交付前必须全部通过）

### 后端场景测试

用模拟器 API 测试以下文件名：

```bash
# 启动服务器（每次改完代码后）
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5

# 测试各场景
for f in "Dune.Part.Two.2024.1080p.mkv" "美丽人生.mkv" "速度与激情.mkv" "爱神.mkv" "123uyyt.mkv" "消防员.mkv" "Movie.2023.mkv"; do
  JOB=$(curl -s -X POST http://localhost:9855/api/scrape/preview/start -H 'Content-Type: application/json' -d "{\"filename\":\"$f\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['job_id'])")
  sleep 30
  echo "=== $f ==="
  curl -s "http://localhost:9855/api/scrape/preview/status/$JOB" | python3 -c "
import sys,json
d = json.load(sys.stdin)['data']['result']
sr = d['scrape_result']
mr = d['match_result']
print(f\"  match_level: {sr.get('match_level')}\")
print(f\"  tier_short: {sr.get('tier_short_reason','')}\")
print(f\"  ai_reason: {sr.get('ai_reason','')[:80]}\")
"
done
```

### 期望结果

| 文件名 | match_level | tier_short_reason 含 |
|--------|-------------|----------------------|
| `Dune.Part.Two.2024.1080p.mkv` | AUTO_PASS 或 CONTEXT_PASS | "唯一精确匹配" 或 "Dune 2" |
| `美丽人生.mkv` | NEEDS_CONFIRM | "同名多版" |
| `速度与激情.mkv` | CONTEXT_PASS | "AI 高确定性" |
| `爱神.mkv` | NEEDS_CONFIRM | "AI 建议候选" |
| `123uyyt.mkv` | **FAILED** | "无可识别影视信息" |
| `消防员.mkv` | **FAILED** 或 NEEDS_CONFIRM | 取决于 Provider 返回候选数 |
| `Movie.2023.mkv` | **FAILED** | "占位词" |

### 前端验证（Playwright 或手动）

1. **任务列表行**：NEEDS_CONFIRM 任务显示一句话原因
2. **任务卡片**：显示"🤖 AI 怎么说"+"✅ 最终用了"+"🏷️ 维度"三块
3. **任务详情**：6 步时间轴完整渲染，每步都有内容（不是"-"）
4. **失败任务卡片**：显示 ❌ + ai_reason + 🔄 重新刮削按钮
5. **点击重新刮削**：任务状态变为 PENDING

---

## 遇到问题时

### 1. 改了代码但行为没变
**原因**：Python `.pyc` 缓存未清  
**解决**：执行"Python 缓存陷阱"中的清缓存+重启命令

### 2. 测试失败
**第一步**：读测试断言，判断是测试过时还是代码 bug  
**第二步**：如果是测试过时（如断言 `confirm_reason` 字段），更新测试  
**第三步**：如果是代码 bug，修复后重跑

### 3. 计划有歧义
**不要自己拍板**。停下来问用户，引用计划文档的具体章节请求澄清。

### 4. LSP 错误
本项目有既有 LSP 错误（如 `scenario: str` 接收 None）。这些是已有的，不要修。只关注**你新增代码**的 LSP 错误。

---

## 完成交付物清单

完成后，仓库应包含：

### 新建文件
- [ ] `media_importer/features/scraping/match_enums.py`
- [ ] `media_importer/webui/js/build-match-path-data.js`
- [ ] `tests/test_match_result_fields.py`
- [ ] `tests/test_phase_pqr.py`

### 修改文件（按 Phase 顺序）
- [ ] `media_importer/features/scraping/match_models.py`（Phase B）
- [ ] `media_importer/features/scraping/_match_tiers_impl.py`（Phase C/M/N/P/Q）
- [ ] `media_importer/features/scraping/match_engine.py`（Phase M）
- [ ] `media_importer/scraper/_llm_match_assist.py`（Phase D/P）
- [ ] `media_importer/features/import_flow/steps/scrape.py`（Phase E）
- [ ] `media_importer/features/import_flow/steps/review.py`（Phase E）
- [ ] `media_importer/features/import_flow/runner.py`（Phase E/Q）
- [ ] `media_importer/api/scrape_preview_job.py`（Phase F/Q）
- [ ] `media_importer/api/task_handlers.py`（Phase R）
- [ ] `media_importer/webui/index.html`（Phase G）
- [ ] `media_importer/webui/js/tasks-list.js`（Phase H）
- [ ] `media_importer/webui/js/cinema-task-list.js`（Phase I/R）
- [ ] `media_importer/webui/js/cinema-task-detail.js`（Phase J）
- [ ] `media_importer/webui/js/match-trace-detail.js`（Phase K/O）
- [ ] `media_importer/webui/js/cinema-config-simulator.js`（Phase L/O）
- [ ] `media_importer/webui/js/cinema-task-utils.js`（Phase R）

### Git 提交
- [ ] 每个 Phase 一个提交，提交信息 `Phase X: 简述`

---

## 最终交付确认

全部 Phase 完成后：

1. 跑完整测试套件：`python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"`
2. 跑架构守卫：`python -m pytest tests/test_architecture_guards.py -q`
3. 跑编译检查：`PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests`
4. 执行"验收场景"中的 7 个文件名测试
5. 向用户报告完成状态

**不要自行决定"完成"。必须所有验收场景通过后才能宣告完成。**

---

**交付提示词完毕。开始执行。**
