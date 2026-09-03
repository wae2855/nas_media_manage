# Bug Registry — test_def 系统性测试发现

测试执行过程中发现的问题登记。按发现阶段和严重程度分类。

---

## FilenameCleaner 解析缺陷（阶段二 scrape 测试发现）

### BUG-FC-01: `DTS.X` 模式残留 X 字符 ✅ 已修复

| 字段 | 值 |
|------|-----|
| 输入 | `Avengers.Endgame.2019.1080p.HDR.HEVC.DTS.X-PTP.mkv` |
| 修复前 | `clean_title='Avengers Endgame X', year=2019` |
| 修复后 | `clean_title='Avengers Endgame', year=2019` |
| 修复方式 | 在 `_SOURCE_CODEC_PATTERNS` 中增加 `DTS-X` 和 `DTS\.X` 模式 |
| 修复提交 | 2026-06-10 |

### BUG-FC-02: `BD` 不在 source/codec 模式中，中文描述词阻断 CJK 分离 ✅ 已修复

| 字段 | 值 |
|------|-----|
| 输入 | `盗梦空间.Inception.2010.BD.1080P.国英双语.mkv` |
| 修复前 | `clean_title='盗梦空间 Inception BD 国英双语', year=2010, cjk_title=None` |
| 修复后 | `clean_title='Inception', year=2010, cjk_title='盗梦空间'` |
| 修复方式 | 1) 在 `_SOURCE_CODEC_PATTERNS` 中增加 `BD` 模式；2) 新增 `_CJK_DESCRIPTOR_PATTERN` 清理 `国英双语/国语/粤语/双语/中字/中英` 等描述词 |
| 修复提交 | 2026-06-10 |

### BUG-FC-03: 标题中的数字被误提取为年份 ✅ 已修复

| 字段 | 值 |
|------|-----|
| 输入 | `Blade.Runner.2049.2017.Directors.Cut.1080p.BluRay.x264.mkv` |
| 修复前 | `clean_title='Blade Runner 2017', year=2049` |
| 修复后 | `clean_title='Blade Runner 2049', year=2017, year_suspect=True` |
| 修复方式 | 改进年份提取逻辑：优先选择不超过当前年份+1的第一个4位数字；多个年份候选时标记 `year_suspect=True` |
| 修复提交 | 2026-06-10 |

### BUG-FC-04: `.srt` 不在扩展名模式中，字幕语言代码残留 ✅ 已修复

| 字段 | 值 |
|------|-----|
| 输入 | `Breaking.Bad.S01E01.720p.BluRay.eng.srt` |
| 修复前 | `clean_title='Breaking Bad eng srt', year=None` |
| 修复后 | `clean_title='Breaking Bad', year=None` |
| 修复方式 | 1) 在 `_EXTENSION_PATTERN` 中增加字幕扩展名 `srt|ass|ssa|sub|idx|vtt`；2) 新增 `_SUBTITLE_LANG_PATTERN` 清理 `eng/chs/cht/zh-cn/chs&eng/cht&eng` 等语言代码 |
| 修复提交 | 2026-06-10 |

### BUG-FC-05: `EXTENDED`/`REMASTERED` 被 source/codec 模式移除，`Edition` 残留 ✅ 已修复

| 字段 | 值 |
|------|-----|
| 输入 | `The.Lord.of.the.Rings.The.Fellowship.of.the.Ring.2001.Extended.Edition.1080p.BluRay.mkv` |
| 修复前 | `clean_title='The Lord of the Rings The Fellowship of the Ring Edition', year=2001` |
| 修复后 | `clean_title='The Lord of the Rings The Fellowship of the Ring', year=2001` |
| 修复方式 | 在 `_EDITION_PATTERN` 中增加独立的 `Edition` 匹配 |
| 修复提交 | 2026-06-10 |

### BUG-FC-06: 字幕语言代码 `zh-cn` 被错误拆分，`cht&eng` 未清理 ✅ 已修复

| 字段 | 值 |
|------|-----|
| 输入1 | `The.Matrix.1999.1080p.BluRay.zh-cn.srt` |
| 输入2 | `Game.of.Thrones.S08E01.cht&eng.srt` |
| 修复前1 | `clean_title='The Matrix zh', year=1999` |
| 修复前2 | `clean_title='Game of Thrones cht&eng srt', year=None` |
| 修复后1 | `clean_title='The Matrix', year=1999` |
| 修复后2 | `clean_title='Game of Thrones', year=None` |
| 修复方式 | 与 BUG-FC-04 同源，通过 `_SUBTITLE_LANG_PATTERN` 统一修复 |
| 修复提交 | 2026-06-10 |

---

## 架构/设计问题（测试编写过程发现）

### ARCH-01: PipelineRunner 缺少断点恢复机制

| 字段 | 值 |
|------|-----|
| 描述 | 历史问题：进程中断时无法证明应从哪个业务步骤继续 |
| 影响 | 已由 ADR-0022 关闭：产品明确不做步骤断点，提交前从来源重来，完整提交后复核成功，歧义转人工检查 |
| 严重程度 | 已解决 |
| 修复建议 | 保持整任务重启合同，不重新引入步骤级续跑 |
| 影响范围 | `runner.py`、DB schema、task_manager |

### ARCH-02: 目标侧任务临时文件残留

| 字段 | 值 |
|------|-----|
| 描述 | 历史问题：SIGKILL 后目标侧 `.copying` / `.bundle.tmp` 可能残留 |
| 影响 | 已由任务清单驱动的启动恢复关闭；不扫描整座片库，只访问非终态任务明确记录的路径 |
| 严重程度 | 已解决 |
| 修复建议 | 保持清单、目标根、任务标识、临时后缀四重门禁；歧义时保留现场 |
| 影响范围 | `bundle_recovery.py`、bundle journal、启动逻辑 |

### ARCH-03: FilenameCleaner 与 AI 刮削的职责边界模糊

| 字段 | 值 |
|------|-----|
| 描述 | `FilenameCleaner.clean()` 做了大量正则清理，但结果仍可能包含残留（如 BUG-FC-01~06）。AI 刮削 (`ai_clean()`) 能修正部分问题，但两者之间的职责划分不清 |
| 影响 | 测试中难以确定"期望结果"应以 regex 还是 AI 结果为准 |
| 严重程度 | 低（设计层面问题，不影响当前功能） |
| 修复建议 | 明确文档化：regex 是快速预处理，AI 是最终修正。测试应分别验证 regex 和 AI 的行为 |
| 影响范围 | 文档和测试策略 |

---

## 测试框架问题

### TEST-01: API handler 直接测试需要大量 mock

| 字段 | 值 |
|------|-----|
| 描述 | UI 测试（test_def_ui_*.py）通过 `APIHandler.__new__()` 创建 handler 实例并手动设置属性来测试，需要 mock 大量依赖（task_manager, config, db 等） |
| 影响 | 测试代码较脆弱，handler 内部实现变更可能导致测试失败 |
| 严重程度 | 低（测试技术债务，不影响被测代码质量） |
| 修复建议 | 后续考虑引入 Flask/FastAPI 测试客户端模式，或增加 handler 工厂方法简化测试创建 |
| 影响范围 | `test_def_ui_*.py` 系列测试 |

---

## 统计

| 类别 | 数量 | 高严重 | 中严重 | 低严重 |
|------|------|--------|--------|--------|
| FilenameCleaner 缺陷 | 6 | 3 | 2 | 0 |
| 架构/设计问题 | 3 | 0 | 1 | 2 |
| 测试框架问题 | 1 | 0 | 0 | 1 |
| **合计** | **10** | **3** | **3** | **3** |
