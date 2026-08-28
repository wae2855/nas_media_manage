---
title: "全项目功能简洁化评估"
type: proposal
date: 2026-08-22
status: approved
requirement: REQ-20260822-000001
---

# 全项目功能简洁化评估

> §1-§4 技术事实（实测）；§5 业务决策（用户 2026-08-22 拍板）；§6 分期路线图（最终）。执行计划见 [plans/2026-08-22-simplification-roadmap.md](../plans/2026-08-22-simplification-roadmap.md)，AI 刮削移除决策见 [ADR-0010](../decisions/0010-remove-ai-scraping.md)。

## 1. 规模全景（2026-08-22 实测）

| 维度 | 规模 | 说明 |
|------|------|------|
| Python 后端 | 140 文件 / 17,872 行 | features 10,254（57%）、core 3,101、api 2,924、infra 356、scraper 兼容层 157、monitor+notify 699 |
| 前端 webui | 88 文件 / 25,178 行 | JS 46 个/12,103 行 + CSS 42 个/13,075 行；**前端体量超后端 41%** |
| 前端死代码 | 36 文件 / 9,376 行 | 存在于磁盘但 `index.html` 未加载（旧版拆分残留），占前端 37% |
| 测试 | 76 文件 / 17,156 行 | 与后端代码近 1:1 |
| API | 69 端点 | 12 个功能域 |
| 配置 | 20 顶层块 / 294 行 | config.yaml.example |

## 2. 功能域清单（按 API 面划分）

| 域 | 端点数 | 前端界面 | 复杂度来源 |
|----|--------|----------|-----------|
| 任务管理（列表/详情/确认/预览/重分类/忽略/重命名/取消/重试/删除） | 17 | 任务工作台（cinema-tasks 系列 10+ JS） | 三级匹配 + 6 层信息模型 + 确认流 |
| 配置管理（读写/分区保存/校验/连通测试） | 12 | 配置页（cinema-config 系列 8 JS） | 20 配置块 + 脱敏 + 热重载 |
| 维度管理（增删改/启停/重置） | 6 | 维度页（dimension 系列 6 JS） | 维度联动刮削与路径规则 |
| Provider（TMDB 检索/测试/预览/详情） | 6 | Provider 卡片 | 单一 Provider（TMDB）但抽象齐全 |
| 刮削模拟器（preview job） | 2 | 模拟器（cinema-config-simulator 2 JS） | 异步 job + 决策路径可视化 |
| 源目录清理器 | 5 | 清理配置页 | LLM 辅助预览 + 清理记录 |
| 回收站 | 3 | 回收页（cinema-recycle） | 安全删除边界 |
| 队列控制 | 4 | 队列状态条 | 并发/暂停/重试 |
| 文件监控 watcher | 2 | 开关 | 轮询扫描 |
| 手动处理（run/run-file） | 2 | 批量/单文件按钮 | — |
| 系统运维（health/metrics/logs/restart） | 5 | 仪表盘 | — |
| Hermes Skill（skill/skills） | 2 | 无界面 | 读 hermes/skills/ 供飞书对话 |
| 缩略图 | 2 | 海报墙 | 文件服务 |
| 通知（Hermes webhook） | 0（配置测试 1） | 无 | notify/ 354 行 |

## 3. 已确定的技术简化项（零业务依赖，技术上可直接执行）

| # | 项 | 收益 | 风险 |
|---|----|------|------|
| T1 | 删除 36 个未加载前端文件（9,376 行死代码） | 前端体量 -37%，消除排查干扰 | 零（未被引用） |
| T2 | 删除 `scraper/` 兼容层（157 行 re-export） | 消除旧导入路径认知负担 | 零（guard 已拦截新引用，验证无生产 import） |
| T3 | CSS 42 文件合并重组（机械拆分的 -1/-2/-3 后缀系） | 前端可维护性显著提升 | 低（需按页面回归视觉） |
| T4 | pyproject.toml + Ruff + Prettier 落地 | 统一格式化与静态检查 | 低 |
| T5 | core/safety.py facade 收敛（真实实现已在 infrastructure/filesystem） | 减一层转发 | 低 |

## 4. 结构性观察（供业务决策参考）

1. **前端是复杂度大头**：删死代码后仍有 ~15.8k 行，主因是 cinema 重做期间新旧两套 UI 并存后遗留的拆分文件。
2. **配置面偏重**：20 个配置块、12 个配置 API；其中 `hooks`（自定义脚本钩子）、`hermes`、`manual_review` 等块使用频率存疑。
3. **低频/边缘功能面**：Hermes Skill 端点、文件监控 watcher、刮削模拟器、源目录清理器的 LLM 辅助预览——每个都有独立界面/端点/测试面。
4. **单 Provider 多抽象**：providers 框架完整但只有 TMDB 一个实现。
5. **monitor/notify 独立小域**（共 699 行）未 feature 化，属历史遗留归置问题。

## 5. 业务决策（用户拍板，2026-08-22）

| # | 决策 |
|---|------|
| B1 前端方向 | **现状够用，只做减法**：不继续 cinema 重做，砍死代码与被移除功能的界面，CSS 合并 |
| B2 功能取舍 | 保留：文件监控 watcher、源目录清理器、刮削模拟器、维度管理界面、手动批量/单文件处理。移除：**Hermes 通知 + Skill（整链路）**、**AI 刮削（刮削链路收敛为 TMDB 主导，见 ADR-0010）**。AI 配置界面收缩为「LLM 连接 + 清理器提示词」（保留一部分，方案见路线图 Phase 1）。AI 维度判断随 AI 刮削移除消失，维度来源=TMDB+规则映射+人工确认兜底（评估结论：无不可替代性，见 ADR-0010） |
| B2+ 新增重点 | **文件全流程状态机需重构**：拷贝→临时区→处理→入库各环节的回退/继续/重试语义不专业，测试与场景覆盖不足，需重新梳理（REQ-20260822-000004，测试矩阵以 `_drafts/2026-06-18-file-flow-cartesian-product.md` 为设计源） |
| B3 使用场景 | **公开发布 fpk 包**：保留安装向导、配置可用性打磨与部署链路 |
| 未来 | 授权系统接入：注册为 Draft 需求（REQ-20260822-000005），暂不启动 |

## 6. 分期路线图（最终）

```text
Phase 0  工程基础（纯技术零风险）：T1 删 9,376 行前端死代码 / T2 删 scraper/ 兼容层
         / T4 pyproject+Ruff+Prettier / T5 core/safety facade 收敛
Phase 1  功能删减（业务已拍板）：Hermes 全移除（notify/+API+配置块+前端+hermes/ 目录）
         + AI 刮削移除（ADR-0010：llm_scraper/prompt_resolver 场景收敛/scene_strategy/
         web_search_config/llm_match_assist 删除或收缩，保留清理器最小 LLM 通路）
         + AI 配置界面收缩 + 相关标准文档重写（scrape-matching/ai-prompt-design）
Phase 2  状态机重构（REQ-20260822-000004）：设计先行，回退/继续/幂等/崩溃恢复语义
         + 笛卡尔积测试矩阵落地
Phase 3  配置面简化：hooks/manual_review 等低频块评估，20 块收敛
Phase 4  收尾：CSS 42 文件合并（T3）、monitor 归置、README 重写、全量回归 + fpk 构建验证
```

依赖关系：Phase 0/1 可并行启动；Phase 2 设计可与 Phase 1 重叠；Phase 3/4 依赖 Phase 1 落定。

## 7. 评估方法说明

- 规模数据为实测（find/wc/index.html 引用比对），非估算。
- 功能域以 API 路由表为事实源（`media_importer/api/routes.py`，69 端点）。
- 死代码判定：文件存在于 webui/ 但未被 index.html 引用，且全 JS 无动态加载代码（已核实）。
- AI 依赖面核实：源目录清理器 import `LLMScraper`/`PromptResolver`/`_assemble_prompt`，故 AI 刮削移除必须保留最小 LLM 通路（`llm_client`）供清理器使用。
