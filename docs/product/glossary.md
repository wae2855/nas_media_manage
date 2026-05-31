# Glossary

| 术语 | 含义 |
|------|------|
| source | 源目录，用户放入待整理文件的位置 |
| temp | 临时目录，处理过程中的工作副本 |
| import | 入库目录，整理后的目标位置 |
| recycle | 回收站，安全移除文件的唯一出口 |
| task | 单个视频及其字幕组成的处理任务 |
| provider | TMDB 等外部元数据源 |
| scrape | 刮削，识别影视标题、年份、类型、维度 |
| dimensions | 分类维度，如地区、类型、分级、质量 |
| confidence | 置信度，用于决定自动入库、确认或失败 |
| path_rules | 维度到目标路径的规则 |
| cleanup_source_after_done | 任务完成后是否把源文件移入回收站 |
