# Providers Feature

Provider 能力负责接入 TMDB 或后续外部元数据源，并为刮削流程提供统一的查询和匹配结果。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/providers/__init__.py` | Feature public API for provider registry and factory functions. |
| `media_importer/features/providers/base.py` | Provider interface and shared result/detail dataclasses. |
| `media_importer/features/providers/tmdb_provider.py` | TMDB provider implementation. |
| `media_importer/features/scraping/metadata_scraper.py` | Calls providers during scrape orchestration. |
| `media_importer/core/config_view.py` | Reads provider-related configuration values. |

## Related Areas

- Config: provider enablement, API keys, language, region, timeout.
- API: provider configuration and scrape endpoints.
- Tests: provider behavior should be mocked, deterministic, and network-free by default.
- 手动刮削搜索可临时覆盖 Provider 的返回语言（中文、英文、日文、韩文），不修改全局 Provider 配置。候选应用必须按 `provider_type + item_id + media_type` 获取完整详情，禁止只把搜索卡片上的标题和年份写入任务。
- Provider 只声明可提供的标准化原始字段与数据形态，不在适配器内写死“原始值 → 产品维度值”。当前 TMDB 声明 `genres/origin_country/original_language/release_dates/adult`，由版本化 Provider 映射合同执行。
- `restricted_level` 的产品名为“观看分级”；TMDB 优先采用香港本地分级，`HK/I → 0-6`、`HK/IIA/IIB → 13-16`、`HK/III → 17+`，并保留 `US/R → 17+` 等其他地区预置。`17+ / 限制观看` 不等同于成人内容。`content_sensitivity` 的产品名为“成人电影标记”，只显示“否/是”：TMDB `adult=false/true` 分别映射到稳定内部值 `normal/adult`，不表示全年龄或内容警示。
- 自动刮削和手动应用 Provider 候选都保存精简映射证据（字段、原始值、规则 ID、目标值和 schema 版本），不保存 API Key 或完整 Provider 响应。
- Provider 的确定性身份扩展点为 `get_by_provider_id(item_id, media_type)` 和 `lookup_external_id(external_id, external_source, media_type)`，统一返回 `SearchResult`。不支持的 Provider 返回空结果，通用 MatchEngine 不得识别具体 Provider 的 URL 或原始响应字段。
- TMDB 原生 ID 通过电影/剧集详情端点解析；IMDb/TVDB ID 通过 TMDB `/find/{external_id}` 解析。TVDB 外部 ID 只接受 TMDB 官方接口实际返回的剧集结果；查询异常由匹配层留痕并保守降级。

## TMDB Credential Contract

- 当前客户端调用 TMDB v3 接口并以 `api_key` 查询参数认证，配置页必须引导用户填写个人 API 页面中的 **API Key（v3 auth）**，不能填写较长的 API Read Access Token。
- 非商业用途可免费申请，但界面必须保留 TMDB 来源声明；商业用途需由使用者向 TMDB 单独确认授权。
- TMDB 不公布固定的每日次数配额；界面按官方动态限流说明展示约 40 次/秒，并把 HTTP 429 解释为稍后重试，不承诺永久固定值。
- 网络检查分两步：先打开 TMDB 官网，再打开 `https://api.themoviedb.org/3/configuration`。后者即使返回缺少/无效密钥 JSON，也证明 DNS、TLS 和 API 域名已连通；打不开或超时才进入 NAS 网络/代理排查。
- 官方入口：`https://www.themoviedb.org/settings/api`。网络是否需要代理取决于用户所在地区和运营商，产品不得承诺所有网络直连可用。

## Target Shape

- Keep provider-specific client code isolated from import flow.
- New API/scraping code should import registry functions and provider types from `media_importer.features.providers`.
- Add a new provider by updating provider docs, config loader/migration/validator, API/frontend settings, and tests.
- If provider selection affects architecture, add an ADR.

## Tests

- Provider unit tests with mocked HTTP responses.
- Scraping integration tests with provider calls stubbed.
- `tests/test_media_identity_resolution_v2.py` 覆盖原生 ID、外部 ID、类型消歧、异常降级和标准结果转换。
