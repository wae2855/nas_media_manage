# Backend Architecture Standards

---
title: backend-architecture-standards
type: standard
date: 2026-08-27
status: accepted
---

> 简洁化完成后（Phase 0-4）的后端架构事实与规则。改后端前必读。

## 1. 分层与依赖方向（硬约束）

```text
api/（HTTP 入口，不载业务策略）
  → features/（业务事实源：import_flow / scraping / tasks / source_cleaning /
              recycle / source_files / providers / configuration）
    → infrastructure/（db / filesystem / llm 基础能力）
core/            # 迁移期兼容层（config/task_manager/db facade），只减不增
monitor/         # 文件监控 + 权限检查（有效保留）
notify/          # 仅 hooks.py（高级脚本钩子）
```

- 依赖只允许上层引下层；features 之间可横向引用（经对方 `__init__` 公共 API）。
- **禁止**新增 `media_importer.scraper` / `core.safety` / `storage` 导入（已删除，architecture guard 拦截复活）。
- 新业务能力一律进对应 feature 或新建 feature 包；api/ 只做参数解析与响应。

## 2. 任务状态机（唯一事实源）

- 全部状态写入必须经 `features/tasks/transitions.py`：
  - `status`: PENDING/FAILED/SKIPPED/SUCCESS/CANCELLED；`stage`: QUEUED/RUNNING/AWAIT_REVIEW/DONE；`file_location`: source/temp/import/recycle。
  - 转换表 `TRANSITIONS` 定义 13 个动作的合法源→目标；非法转换抛 `TransitionError`。
  - 负向全组合测试自动生成（`tests/test_task_transitions.py`）——新增动作必须同步转换表，否则测试失败。
- 并发守护：confirm/retry/cancel 用 `task_repo.compare_and_update_task`（CAS）。并发操作只成功一次。
- retry 语义：`resume=True` 默认开——temp checkpoint 文件存在则保留（`_step_copy` 跳过复制从刮削续跑），不存在自动降级从头。
- `retry_all_failed` 默认仅 FAILED；SKIPPED/CANCELLED 需显式参数（用户终态决策不可批量推翻）。
- import 幂等：目标已存在且指纹相同 → 幂等成功；不同 → 报冲突。

## 3. 刮削链路（两级匹配，ADR-0010）

```text
FilenameCleaner 正则清洗 → TMDB 搜索（CJK 优先，L4/L6/L7 回退英文）
  → 匹配等级判定（TitleMatcher L1-L7）
    ├─ AUTO_PASS → 分类 → 去重 → 命名 → 入库
    └─ 不确定 → NEEDS_CONFIRM → 人工检索(scrape-search)/编辑 → 确认入库
```

- **禁止**引入任何 AI 参与刮削、匹配、维度判断（退役词 guard 拦截）。
- 维度来源枚举：`file` / `provider:{type}` / `default` / `unknown`；不允许新来源。
- 维度兜底：`_apply_dimension_defaults`（DB `dimensions.default_value`，标记 source=default）→ 无默认值留空进人工确认。**不猜测**。
- 限制级映射：`CERTIFICATION_TO_LEVEL` 9 国优先级（US>GB>DE>FR>CN>JP>KR>AU>CA）。
- manual_review 开关 = AUTO_PASS 强制走人工确认（合法配置项）。

## 4. LLM 边界

- 唯一入口 `infrastructure/llm/LLMClient`（OpenAI 兼容，主模型+fallback 重试）。
- 唯一消费者 `features/source_cleaning`（提示词内置 `prompts.py`，JSON 契约见 ai-prompt-design.md）。
- 配置唯一来源 `config.yaml` 的 `llm` 块（8 字段）；`RETIRED_CONFIG_SECTIONS` 视图剥离退役块。
- LLM 输出仅是建议；删除永远走回收站规则，AI 失败静默降级纯规则模式。

## 5. 文件操作安全（红线）

- 删除/覆盖影视文件必须走回收站；禁止直接 `os.remove()` 源文件或入库文件。
- 文件操作限制在 `allowed_dirs_from_config` 白名单（含 fallback_dir——2026-08 修复的历史缺口，勿回退）。
- 临时文件只在明确 `temp_dir` 或 `.tmp`/`.copying` 边界内可直接删。
- 敏感配置返回前端前必须脱敏（`mask_sensitive` 覆盖 llm 块全部 `*api_key` 字段）。

## 6. 配置面

- 19 个配置块全部有运行时消费者；新增块必须同步 loader/validator/view/API/前端/文档/tests（见 ai-map §3）。
- hooks 是高级扩展点（路径白名单校验）；manual_review 是合法开关——两者保留不删。

## 7. 质量门禁

| 命令 | 要求 |
|------|------|
| `.venv/bin/python -m pytest tests/` | 全绿（UI gated 自动跳过） |
| `.venv/bin/python -m pytest tests/test_architecture_guards.py` | 架构护栏（禁止旧路径复活） |
| `.venv/bin/ruff check media_importer tests` | 全绿（存量已清零，保持） |
| `python scripts/check_docs.py` | 断链/行数/front-matter/退役词 |

- 新增 feature 必须带 feature smoke 测试（`test_feature_` 前缀）+ `docs/features/` 文档。
- 状态机改动 = 改 transitions.py + 负向测试同步，禁止在调用方手写 status 赋值。
