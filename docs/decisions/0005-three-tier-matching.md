# ADR-0005: Three-Tier Matching Strategy

Date: 2026-06-12
Status: Accepted
Supersedes: Confidence formula system (`T x R x data_gate`)
Plan: [2026-06-12-refactor-three-tier-matching-plan.md](../plans/2026-06-12-refactor-three-tier-matching-plan.md)

## Context

The current scraping confidence system uses a mathematical formula to produce a continuous confidence value:

```
final_confidence = T x R x data_gate
```

- **T** (Title Match): L1-L7 matching levels from TitleMatcher
- **R** (Result Count Penalty): log/inverse/sqrt decay formula
- **data_gate**: Binary gate checking dimension source trust

This system has 20+ configuration parameters, per-dimension trust configs, and presents continuous probability values (0.83) to users who cannot meaningfully interpret them.

Industry comparison:
- **Plex**: File name -> Agent search -> first result, no confidence concept
- **Jellyfin**: File name -> Provider search -> similarity ranking, take best
- **Kodi**: Regex extract -> Provider search -> top 1
- **TinyMediaManager**: File name -> search -> user selects (auto-select by closest match)

All use discrete match/no-match decisions, not continuous probability values.

## Decision

Replace the mathematical confidence formula with a three-tier discrete matching strategy:

1. **Tier 1 - Provider Exact Match**: Clean filename -> extract title/year/season/episode -> search Provider -> exact match (title + year) -> AUTO_PASS
2. **Tier 2 - Context-Assisted Match**: Collect directory context (parent folder, sibling files) + Provider candidates -> AI selects from candidates -> AUTO_PASS
3. **Tier 3 - User Confirmation**: Present top Provider candidates + match concern reasons -> user selects

Key principles:
- Matching (which work) and dimensions (what category) are decoupled
- Match concern reasons replace confidence numbers for user communication
- AI is used for context-assisted judgment (Tier 2) and dimension completion, not for primary matching
- TitleMatcher L1-L7 levels are preserved but T values are no longer used as multiplication factors

Dimension confirmation follows a three-level priority:
1. **Provider Direct Mapping**: Structured data from Provider (TMDB/豆瓣) mapped via deterministic rules. 100% trusted. Example: `genre_ids=99` → `documentary=true`, `origin_country=["JP"]` → `region=jp`. `media_type` is hardcoded from the search endpoint used (`/search/movie` → movie, `/search/tv` → tv).
2. **AI Assist Analysis**: When Provider has data but mapping is complex (e.g., `restricted_level` — different countries have different certification systems, AI maps them to unified age brackets). No web search needed. Source marked as `ai_assist`.
3. **AI Web Search Enhancement**: When Provider and AI assist both fail to fill a dimension, AI with web search capability supplements missing values. Requires explicit enable switch. Source marked as `ai_search`.

Each dimension has two independent trust switches: `trust_ai_assist` (trust AI assist mapping) and `trust_ai_search` (trust AI web search results). Untrusted AI-sourced dimensions require user confirmation.

## Alternatives Considered

### A: Keep current formula, simplify configuration
Reduce 20+ parameters to 5-8 sensible defaults. Keep the T x R x gate formula but hide complexity.

**Rejected because**: The formula itself is the problem, not just the configuration count. R (result count penalty) has questionable value when title+year already uniquely identifies a work. The data_gate binary switch is too harsh.

### B: Hybrid approach - formula for edge cases only
Use simple exact-match for clear cases, fall back to formula for ambiguous cases.

**Rejected because**: Creates two systems to maintain. The three-tier model is simpler and covers all cases uniformly.

### C: Pure AI matching (no Provider)
Let AI identify works directly from filename + context.

**Rejected because**: TMDB provides structured, verifiable data. AI hallucination risk is too high for primary matching. Provider data should be the source of truth.

## Consequences

### Positive
- **Dramatically simpler configuration**: From 20+ parameters to 3 optional ones
- **Clearer user communication**: "No year, 3 works with same name" vs "confidence 0.45"
- **Lower maintenance cost**: ~300 lines vs ~800 lines for matching logic
- **Better edge case handling**: Directory context provides strong signals that formulas cannot capture
- **Industry alignment**: Matches how Plex/Jellyfin/Kodi handle matching

### Negative
- **Loss of fine-grained tuning**: Users who understood the formula can no longer tweak thresholds
  - Mitigation: The vast majority of users never touched these settings
- **AI dependency for Tier 2**: Every non-exact match triggers an AI call
  - Mitigation: Cost is ~0.3 yuan per 1000 files, negligible
- **ai_only mode removal**: Breaking change for users who configured it
  - Mitigation: Auto-migration to provider_first with graceful degradation when no Provider is configured
- **No probability output**: Cannot rank candidates by likelihood
  - Mitigation: Provider returns popularity-ranked results, which is a better ranking signal

### Risks
- Tier 1 exact match rate may be below 80% for poorly named files
  - Mitigation: Benchmark dataset of 100+ real filenames to validate
- AI Tier 2 may not be reliable enough without web search
  - Mitigation: Graceful degradation to Tier 3, and assumption marked as "to be verified"
