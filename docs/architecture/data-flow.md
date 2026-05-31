# Data Flow

## Main Import Data Flow

```text
source files
  -> FileScanner
  -> TaskManager / SQLite
  -> PipelineRunner
  -> temp files
  -> MetadataScraper + Provider + LLM
  -> classification / dedup
  -> import directory
  -> source cleanup / recycle
```

## Persistence

- SQLite 存储任务、字幕、维度、源目录清理记录等结构化状态。
- 刮削结果、维度、追踪信息使用 JSON 字段保存。
- 文件真实位置由 `file_location` 与路径字段共同表达。

## Future Work

状态和文件位置规则会在后续 `TaskLifecycle` 重构中集中化。当前文档只保留高层数据流。
