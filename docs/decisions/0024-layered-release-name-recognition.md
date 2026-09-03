# ADR-0024: Layered release-name recognition

Date: 2026-09-03
Status: Accepted

## Context

入库源包含国际 Scene/PT 命名、中文网盘命名、非规范文件夹及多集目录。现有单体正则解析器既提取技术字段又删除广告，已经出现正常片名被 `.me` 域名规则截断、中文季标记残留在搜索词中的问题。媒体身份错误会影响后续判重与入库目标，必须在复制前保守决策。

## Decision

采用四层识别结构：

1. 中文输入规范化，仅处理中文数字季集、全角符号和具有强证据的中文发布说明。
2. GuessIt 负责通用发布名语法，输出标题、年份、季集范围、画质、来源、编码和发布组。
3. 文件与受控目录证据独立保留并按 Provider ID 融合，单文件具体集号优先于目录范围。
4. Provider 标题、原始标题和官方别名共同验证稳定身份；证据不足或冲突时进入用户确认。

GuessIt 是解析组件而非身份事实源。不得为具体影片增加代码白名单，不得因为 Provider 仅返回一条结果就自动通过。身份确认前不得开始大文件复制、来源清理或目标片库写入。

## Consequences

- 通用发布名能力由成熟依赖维护，自研范围收敛到中文生态和业务证据。
- fnOS 包必须离线携带 GuessIt 及其传递依赖，并保留第三方许可证声明。
- 解析结果变化必须通过真实语料回归；升级 GuessIt 视为匹配行为变更，不能自动漂移版本。
- 官方别名读取会增加少量 Provider 请求，只允许在唯一、同年、同类型的模糊候选上触发，并应缓存到单次匹配上下文。

## Alternatives

- 继续维护单体正则：拒绝，误伤不可控。
- 完全以 GuessIt 结果自动入库：拒绝，解析结果不是稳定媒体身份。
- 使用 AI 猜测标题：拒绝，与 ADR-0010 冲突，且不可形成可验证的稳定身份。

## Links

- [方案](../proposals/2026-09-03-structured-release-name-recognition.md)
- [实施计划](../plans/2026-09-03-refactor-layered-release-name-recognition-plan.md)
- [刮削匹配规范](../standards/scrape-matching.md)
