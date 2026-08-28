# AI Prompt Design（源目录清理器专用契约）

---
title: ai-prompt-design-standard
type: standard
date: 2026-08-22
status: accepted
note: ADR-0010 后 LLM 唯一消费者是源目录清理器；原 5 场景提示词体系（title_clean/match_assist/dimension_mapping/dimension_supplement/scrape）已随 AI 刮削移除归档。
---

## 范围

LLM 仅在源目录清理器中使用：分析目录文件构成 → 输出 keep/delete 建议。

- Client：`media_importer/infrastructure/llm/`（OpenAI 兼容 HTTP，主模型+fallback 重试）
- 提示词：`media_importer/features/source_cleaning/prompts.py`（内置常量，无用户自定义文件）
- 调用方：`features/source_cleaning/cleaner.py::_ai_analyze_directory`

## 输入/输出契约

```text
system: "你是影音库AI智能整理系统的源目录清理助手。判断源目录中哪些文件应清理、哪些应保留。"
user:   【分析原则】保守判定原则（见 prompts.py INSTRUCTION）
        + 【输出格式】严格 JSON
        + 【待分析目录】目录路径 + 文件列表 JSON

输出（严格 JSON，无解释文字）:
{
  "analysis": "简要分析说明",
  "decisions": {
    "文件名": {"action": "keep|delete", "reason": "判断理由"}
  }
}
```

## 行为边界

- LLM 输出**仅是建议**：清理器按自身扩展名/黑名单/保护规则最终裁决，AI 无法强制删除任何文件。
- 删除永远走回收站（safety 规则），AI 分析失败时静默降级为纯规则模式。
- `LLMClient.enabled = api_key && base_url && model`；未配置时清理器纯规则运行。
- 温度 0.3；不启用联网搜索工具。

## 测试

- `tests/test_feature_source_cleaning.py`（规则+AI mock）
- `tests/test_source_cleaner_e2e.py`（gated，手动跑）

## 变更前置

提示词原则或 JSON 契约变更须先更新本文件。
