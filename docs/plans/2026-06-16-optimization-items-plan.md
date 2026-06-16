# 优化项实施计划

**日期**：2026-06-16  
**类型**：清理 + 加固（非功能性）  
**前置条件**：上一个计划"刮削信息职责拆分"及其修复补丁已完成

---

## 一、总体概览

| 优化项 | 风险 | 工作量 | 收益 | 建议优先级 |
|--------|:---:|:---:|:---:|:---:|
| 1. 遗留详情模态框清理 | 低（7 个文件全孤立） | 0.5h | 减 1600+ 行死代码 | **P0** |
| 2. confirm_reason DB 列删除 | 低（无读写） | 1.5h | 清洁 schema | **P1** |
| 3. E2E 测试加强 | 中（需 Playwright） | 4h | 防回归 | **P2** |

**总工作量**：约 6 小时

---

## 二、优化项 1：遗留详情模态框清理

### 2.1 现状（已调研）

**关键发现**：Cinema 版是生产中实际使用的唯一详情模态框。7 个遗留 JS 文件**完全孤立**：
- `index.html` 只加载 Cinema 链路
- 遗留 `showTaskDetail` 函数从未被任何已加载文件调用
- 遗留文件之间互相引用，但整个孤岛与主代码无连接
- 无任何测试引用遗留文件

**遗留版独有但已对用户不可见的特性**（因模态框从不打开）：
- 文件大小、文件位置标签
- 中转路径、入库目录、最终文件名
- 分辨率、画质
- 入库去重检测（dedup_result）
- 时间戳（创建/开始/完成）

### 2.2 实施方案

#### 阶段 A：删除孤立文件（零风险，立即做）

**删除以下 7 个文件**：

```
media_importer/webui/js/tasks.js                       (1 行 stub)
media_importer/webui/js/tasks-list.js                  (489 行)
media_importer/webui/js/tasks-detail.js                (414 行)
media_importer/webui/js/tasks-ops.js                   (218 行)
media_importer/webui/js/tasks-ops-extended.js          (380 行)
media_importer/webui/js/tasks-actions.js               (153 行)
media_importer/webui/js/match-trace-detail.js          (394 行)
```

**合计减重**：约 2050 行死代码

**操作**：
```bash
# 1. 删除前最后确认无引用
for f in tasks.js tasks-list.js tasks-detail.js tasks-ops.js tasks-ops-extended.js tasks-actions.js match-trace-detail.js; do
  echo "=== $f 引用检查 ==="
  grep -rn "$f" media_importer/webui/ --include="*.html" 2>/dev/null
  grep -rn "$(echo $f | sed 's/.js$//' | sed 's/-/_/g')" media_importer/webui/js/ --include="*.js" 2>/dev/null | grep -v "^$f:" | head -5
done

# 2. 删除
rm media_importer/webui/js/tasks.js
rm media_importer/webui/js/tasks-list.js
rm media_importer/webui/js/tasks-detail.js
rm media_importer/webui/js/tasks-ops.js
rm media_importer/webui/js/tasks-ops-extended.js
rm media_importer/webui/js/tasks-actions.js
rm media_importer/webui/js/match-trace-detail.js
```

**不需要改 index.html**（这些文件本来就没被引入）

#### 阶段 B：清理已加载文件中的死代码（低风险）

**位置 1**：`media_importer/webui/js/cinema-app-events.js` 第 60-67 行

删除 `data-task-row-open` 分支（无人 emit 该属性，是死代码）：

```javascript
// 删除这段（约 L60-67）
document.querySelectorAll("[data-task-row-open]").forEach(btn => {
  btn.addEventListener("click", () => {
    const tid = btn.getAttribute("data-task-row-open");
    if (tid) openTaskDetail(tid);
  });
});
```

**位置 2**：`media_importer/webui/js/cinema-task-list.js` 第 414-416 行

检查 `rescrapeTask` 函数后的孤立 `}` 和 `handleTaskActions(...)` 调用。如果是合并残留，清理；如果是有效代码，保留。

**验证**：

```bash
# 启动服务，清缓存
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5

# 浏览器访问 http://localhost:9855/
# 1. 点开任意任务卡片，确认 Cinema 详情模态框正常打开
# 2. 浏览器 console 应无报错
# 3. 各种状态任务（AWAIT_REVIEW/FAILED/SUCCESS/SKIPPED）都能打开详情
```

#### 阶段 C：迁移遗留版独有特性到 Cinema（可选，作为产品增强）

**重要**：这些特性当前对用户已经不可见（遗留模态框从不打开）。迁移是产品增强，不是删除阻塞项。

按用户价值排序（每项约 30 分钟）：

1. **路径与位置信息块** — 文件大小 + 文件位置标签 + video_path/import_path/final_filename
2. **刮削增强** — 在 `buildScrapeResultSection` 加 resolution/quality/season/episode
3. **去重块** — `buildDedupSection(task)` 读 `task.dedup_result`
4. **时间戳** — `buildTimelineSection(task)` 显示创建/开始/完成时间
5. **SKIPPED 支持** — 泛化 `buildFailureSection` 也响应 SKIPPED 状态

每项独立提交，各自验证。

### 2.3 验收清单

- [ ] 7 个遗留文件已删除
- [ ] `index.html` 无需改动（已确认这些文件未被引入）
- [ ] 浏览器 console 无 Symbol not found 错误
- [ ] Cinema 详情模态框对每种任务状态都能正常打开
- [ ] 全部测试通过：`python -m pytest tests/ -q --ignore=tests/test_*_ui.py -k "not test_ai_config_ui"`

---

## 三、优化项 2：confirm_reason DB 列删除

### 3.1 现状（已调研）

**关键发现**：
- DB 表 `tasks` 有 `confirm_reason TEXT DEFAULT ''` 列（`constants.py:50`）
- **零生产代码读取**该列的值（`SELECT *` 取出但无人 `task.get('confirm_reason')`）
- **零生产代码写入**该列（无 `update_task(confirm_reason=...)` 调用，`mark_confirming` 写的是 `error_message`）
- 前端零引用
- 与内存中的 `MatchResult.confirm_reason` 字段是**两个不同的概念**（内存字段已废弃，是另一个清理项）

### 3.2 实施方案

#### 阶段 A：代码层移除（立即做）

**文件 1**：`media_importer/core/db/constants.py:50`

删除 `CREATE_TASKS_TABLE` 中的 `confirm_reason TEXT DEFAULT '',` 行（新 DB 不再创建此列）。

**文件 2**：`media_importer/core/db/task_repo.py`

- **L137**：从 `list_tasks` 的 SELECT 语句删除 `t.confirm_reason,`
- **L183**：从 `update_task` 的 `valid_columns` 集合删除 `"confirm_reason",`

**文件 3**：删除测试文件 `tests/test_task_confirm_reason.py`（整个文件，104 行）

#### 阶段 B：DB 迁移（兼容已有 DB）

**文件**：`media_importer/core/db/connection.py` 的 `_migrate_schema` 函数

现有 `_migrate_schema` 是个 stub（只创建 `schema_version` 表）。新增 guarded DROP COLUMN：

```python
import sqlite3
import logging

logger = logging.getLogger(__name__)

def _drop_deprecated_columns(conn):
    """删除已废弃的列（需要 SQLite 3.35+）"""
    cur = conn.execute("PRAGMA table_info(tasks)")
    cols = {row[1] for row in cur.fetchall()}
    
    if "confirm_reason" not in cols:
        return  # 新库本来就没有
    
    if sqlite3.sqlite_version_info >= (3, 35, 0):
        conn.execute("ALTER TABLE tasks DROP COLUMN confirm_reason")
        logger.info("已删除 tasks.confirm_reason 列")
    else:
        logger.warning(
            "SQLite %s < 3.35，无法 DROP confirm_reason，"
            "该列已废弃无影响",
            sqlite3.sqlite_version,
        )

# 在 _migrate_schema 末尾调用：
# _drop_deprecated_columns(conn)
```

**为什么用版本守卫**：fnOS 的 SQLite 版本未在仓库中 pin。DROP COLUMN 是 SQLite 3.35.0（2021-03）引入的。Python 3.12 通常捆绑更新版本，但 fnOS 实际版本需确认。守卫失败时降级为警告（列留着无害，因为无人读写）。

#### 阶段 C：文档更新

**文件 1**：`docs/architecture/api.md:270` — 删除字段表中 `confirm_reason` 行

**文件 2**：`docs/INDEX.md:50` — 更新 "confirm_reason 持久化" 引用

**文件 3**：`docs/testing/feature-coverage.md:82` — 删除 `test_task_confirm_reason.py` 引用

### 3.3 验收清单

- [ ] `constants.py` 的 CREATE_TASKS_TABLE 不含 confirm_reason
- [ ] `task_repo.py` 的 SELECT 和 valid_columns 不含 confirm_reason
- [ ] `tests/test_task_confirm_reason.py` 已删除
- [ ] 已有 DB 启动后日志显示 "已删除 tasks.confirm_reason 列" 或 "无法 DROP（版本低）"
- [ ] 新 DB（删除后重建）不含 confirm_reason 列
- [ ] 全部测试通过：`python -m pytest tests/ -q --ignore=tests/test_*_ui.py -k "not test_ai_config_ui"`
- [ ] 编译通过：`python -m compileall -q media_importer tests`

### 3.4 风险评估

| 风险 | 等级 | 说明 |
|------|:---:|------|
| 生产代码读取断裂 | **无** | 无人读取此列 |
| 生产代码写入断裂 | **无** | 无人调用 `update_task(confirm_reason=...)` |
| 已有 DB 升级失败 | **低** | 守卫+降级警告 |
| 测试失败 | **低** | 仅 1 个文件需删 |
| 概念混淆 | **中（流程）** | 不要顺手清理内存 `MatchResult.confirm_reason`，那是另一个独立项 |

---

## 四、优化项 3：E2E 测试加强

### 4.1 现状

**已有基础设施**：
- Playwright 已装（`tests/test_ai_config_ui.py` 等使用）
- UI 测试有跳过机制（`@unittest.skipIf(not HAS_PLAYWRIGHT)`）
- 测试用例模式：headless Chromium + requestApi / 直接 API 调用

**当前缺口**：
- 模拟器与正式任务字段一致性**无自动化测试**（依赖手动 Playwright 验证）
- 没有真正的"投递文件 → 入库 → 验证 DB"端到端测试
- 6 层信息职责的 UI 渲染无回归测试

### 4.2 实施方案

#### 测试套件 1：字段传递回归测试

**目标**：防止 scrape.py 再次出现"字段未透传"bug

**新建文件**：`tests/test_scrape_result_fields_e2e.py`

```python
"""端到端验证：模拟器与正式任务的 scrape_result 字段结构一致"""
import unittest
import requests


@unittest.skipUnless(
    __import__("os").environ.get("RUN_E2E_TESTS"),
    "需要启动服务：RUN_E2E_TESTS=1 python -m pytest tests/test_scrape_result_fields_e2e.py"
)
class TestScrapeResultFieldsConsistency(unittest.TestCase):
    
    BASE_URL = "http://localhost:9855"
    TEST_FILENAME = "Dune.Part.Two.2024.1080p.mkv"
    
    EXPECTED_FIELDS = {
        "match_level", "match_tier", 
        "tier_short_reason", "ai_reason", 
        "selected_candidate",
    }
    
    @classmethod
    def setUpClass(cls):
        # 健康检查
        resp = requests.get(f"{cls.BASE_URL}/api/dimensions/enabled", timeout=5)
        if resp.status_code != 200:
            raise unittest.SkipTest("服务未启动")
    
    def test_preview_scrape_result_has_all_fields(self):
        """模拟器的 scrape_result 包含全部 L1-L4 字段"""
        resp = requests.post(
            f"{self.BASE_URL}/api/scrape/preview/start",
            json={"filename": self.TEST_FILENAME},
            timeout=10,
        )
        job_id = resp.json()["data"]["job_id"]
        
        # 轮询直到完成
        import time
        for _ in range(60):
            status = requests.get(
                f"{self.BASE_URL}/api/scrape/preview/status/{job_id}",
                timeout=5,
            ).json()
            if status["data"]["status"] == "done":
                break
            time.sleep(1)
        
        scrape_result = status["data"]["result"]["scrape_result"]
        missing = self.EXPECTED_FIELDS - set(scrape_result.keys())
        self.assertEqual(missing, set(), f"模拟器 scrape_result 缺字段: {missing}")
    
    def test_selected_candidate_structure(self):
        """selected_candidate 字段结构正确"""
        # ... 类似上面，额外验证 selected_candidate 的子字段
        pass


if __name__ == "__main__":
    unittest.main()
```

**特点**：
- 用环境变量 `RUN_E2E_TESTS=1` 控制，避免 CI 中意外触发
- 健康检查 + 优雅跳过
- 验证字段集合，而非具体值（值依赖网络/AI）

#### 测试套件 2：UI 渲染回归测试

**目标**：防止前端各视图渲染出现"-"或空白

**新建文件**：`tests/test_info_layers_ui.py`

```python
"""验证 6 层信息职责的前端渲染不回归"""
import unittest
import time

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


@unittest.skipUnless(
    HAS_PLAYWRIGHT and __import__("os").environ.get("RUN_E2E_TESTS"),
    "需要 Playwright 和运行中的服务"
)
class TestInfoLayersRendering(unittest.TestCase):
    
    BASE_URL = "http://localhost:9855"
    
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        cls.page.goto(cls.BASE_URL)
    
    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
    
    def test_needs_confirm_task_shows_tier_short_reason(self):
        """NEEDS_CONFIRM 任务列表行显示 tier_short_reason"""
        # 1. 导航到任务列表
        # 2. 找一个 NEEDS_CONFIRM 任务
        # 3. 验证 .task-short-reason 元素非空
        pass
    
    def test_card_ai_reason_block_renders(self):
        """任务卡片'AI 怎么说'区块渲染"""
        # 1. 找有 ai_reason 的任务卡片
        # 2. 验证 .task-ai-reason-block 文本非空
        pass
    
    def test_detail_timeline_no_dash(self):
        """详情时间轴不出现 '-'"""
        # 1. 点开任务详情
        # 2. 遍历时间轴步骤
        # 3. 验证每步文本不为 '-'
        pass
```

**注意**：此测试套件需要测试数据（任务列表里需要有 AWAIT_REVIEW/FAILED 任务）。可结合下面的"测试数据准备"一起做。

#### 测试套件 3：完整入库流程测试

**目标**：投递真实文件，验证 DB 字段完整

**新建文件**：`tests/test_full_import_flow_e2e.py`

```python
"""完整入库流程的字段完整性测试"""
import unittest
import os
import time
import sqlite3
import requests


@unittest.skipUnless(
    os.environ.get("RUN_E2E_TESTS"),
    "需要启动服务和测试文件"
)
class TestFullImportFlowFields(unittest.TestCase):
    
    DB_PATH = "/Users/wangwei/Documents/code/nas_media_manage/data/tasks.db"
    BASE_URL = "http://localhost:9855"
    
    def test_task_db_has_structured_fields(self):
        """任务 DB 的 scrape_result JSON 含全部 L1-L4 字段"""
        conn = sqlite3.connect(self.DB_PATH)
        cur = conn.execute(
            "SELECT scrape_result FROM tasks "
            "WHERE status IN ('AWAIT_REVIEW','CONFIRMING') "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        
        if not row:
            self.skipTest("无 AWAIT_REVIEW 任务")
        
        import json
        scrape_result = json.loads(row[0])
        
        # 验证关键字段存在
        for field in ["match_level", "match_tier", "tier_short_reason"]:
            self.assertIn(field, scrape_result, 
                         f"DB scrape_result 缺字段 {field}")
        
        # 验证 selected_candidate 结构（若任务有候选）
        if scrape_result.get("selected_candidate"):
            sc = scrape_result["selected_candidate"]
            self.assertIn("why_selected", sc)
            self.assertIn(sc["why_selected"], 
                         ["unique_match", "top_rated", "ai_suggestion", 
                          "first_candidate", "user_pick"])
```

### 4.3 测试数据准备

E2E 测试需要：
- 一个运行中的服务（`RUN_E2E_TESTS=1` 触发）
- 测试 DB 中有不同状态的任务（AWAIT_REVIEW / FAILED / SUCCESS）
- 至少一个有 `selected_candidate` 的任务

**建议**：在 `scripts/` 新建 `prepare_e2e_fixtures.sh`：

```bash
#!/bin/bash
# 准备 E2E 测试数据
# 1. 清空测试 DB
# 2. 通过 API 投递几个不同类型的文件（垃圾文件 / 正常电影 / 同名多版本）
# 3. 等待任务完成
# 4. 验证 DB 中有预期状态的任务

set -e
BASE_URL=http://localhost:9855

# 通过模拟器 API 生成不同状态的任务（模拟器不实际入库，但可生成 scrape_result）
for f in "123uyyt.mkv" "Dune.2024.mkv" "美丽人生.mkv"; do
    curl -s -X POST "$BASE_URL/api/scrape/preview/start" \
        -H 'Content-Type: application/json' \
        -d "{\"filename\":\"$f\"}" > /dev/null
    sleep 30
done

echo "测试数据准备完成"
```

### 4.4 验收清单

- [ ] 3 个 E2E 测试文件创建
- [ ] 环境变量 `RUN_E2E_TESTS=1` 控制启用
- [ ] 无该环境变量时测试优雅跳过（不失败）
- [ ] `scripts/prepare_e2e_fixtures.sh` 可执行
- [ ] 文档 `docs/testing/feature-coverage.md` 更新，记录 E2E 测试运行方式

### 4.5 风险评估

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| CI 误触发 | 中 | 环境变量守卫 + 优雅 skip |
| Playwright 不可用 | 低 | 已有 `HAS_PLAYWRIGHT` 守卫模式 |
| 测试数据状态不稳定 | 中 | 测试前清理 + 固定测试用文件名 |
| 测试运行慢（每场景 30s+） | 中 | 并行运行 + 减少轮询间隔 |

---

## 五、实施顺序建议

```
Day 1（约 2h）：
├─ 优化项 1 阶段 A：删除 7 个孤立文件          (15min)
├─ 优化项 1 阶段 B：清理死代码分支              (15min)
├─ 优化项 2 阶段 A：代码层移除                  (30min)
├─ 优化项 2 阶段 B：DB 迁移守卫                 (30min)
└─ 优化项 2 阶段 C：文档更新                    (15min)

Day 2（约 4h）：
├─ 优化项 3 测试套件 1：字段传递 E2E            (1h)
├─ 优化项 3 测试套件 2：UI 渲染 E2E             (1.5h)
├─ 优化项 3 测试套件 3：完整流程 E2E            (1h)
└─ 测试数据准备脚本                            (30min)

可选（按需）：
└─ 优化项 1 阶段 C：迁移特性到 Cinema          (每项 30min)
```

---

## 六、整体验收

完成所有 3 个优化项后：

```bash
# 1. 测试全通过
cd /Users/wangwei/Documents/code/nas_media_manage
source .venv/bin/activate
python -m pytest tests/ -q --ignore=tests/test_*_ui.py -k "not test_ai_config_ui"

# 2. 架构守卫
python -m pytest tests/test_architecture_guards.py -q

# 3. E2E 测试（需启动服务）
RUN_E2E_TESTS=1 python -m pytest tests/test_scrape_result_fields_e2e.py -q

# 4. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

# 5. 残留 grep（应无输出）
grep -rn "tasks-detail.js\|tasks-list.js\|tasks-ops" media_importer/ 2>/dev/null
grep -rn "confirm_reason" media_importer/core/db/ 2>/dev/null
```

---

## 七、附：不在本计划范围的事项

明确**不做**的事（避免范围蔓延）：

- ❌ 内存 `MatchResult.confirm_reason` 字段清理（属于 Phase 5.1 延续，另开任务）
- ❌ tasks-detail.js 遗留特性迁移到 Cinema（阶段 C 是可选项，按需）
- ❌ 完整的 Playwright 测试基础设施重构
- ❌ fnOS SQLite 版本探测（守卫已经处理降级）
- ❌ DB 表其他字段的清理（只针对 confirm_reason）

---

**计划完毕。用户先自行验证当前状态，确认后开始执行。**
