# Prompts Feature

> **AI 提示词契约事实源**：本文件描述代码组织。Tier 2 AI 辅助匹配的输入/输出 JSON 契约、is_valid/certainty 语义、边界判定规则以 [../standards/ai-prompt-design.md](../standards/ai-prompt-design.md) 为准。

提示词能力负责 AI 刮削提示词模板、变量、用户配置和与刮削结果解析相关的可维护边界。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/prompts/__init__.py` | Feature public API for prompt builder and LLM prompt defaults. |
| `media_importer/features/prompts/application_service.py` | Prompt file load/save/reset service for global and provider-specific prompts. |
| `media_importer/features/prompts/prompt_builder.py` | Prompt template loading and JSON schema rendering. |
| `media_importer/scraper/llm_prompts.py` | Thin legacy import wrapper for `LLMPromptBuilder`. |
| `media_importer/scraper/llm_scraper.py` | Builds prompts and parses LLM responses. |
| `media_importer/api/prompt_handlers.py` | Prompt-related HTTP handlers if enabled in current routes. |
| `media_importer/webui/js/` | Prompt configuration UI dependencies. |

## Related Areas

- Config: AI provider, model, prompt templates, output parsing options.
- Scraping: prompt changes affect metadata extraction and confidence decisions.
- Tests: prompt rendering and parsing should be deterministic and network-free.

## Target Shape

- Keep prompt template and prompt file ownership in `features/prompts/`.
- New prompt API code should import from `media_importer.features.prompts`.
- Keep provider-specific API calls outside prompt template logic; provider prompt file names and defaults are resolved through the prompts feature service.
- Record any prompt contract change in scraping docs and tests.
