# Release Workflow

1. 确认工作树干净。
2. 跑必要测试。
3. 检查配置示例和迁移。
4. 检查文档入口和接口规范。
5. 如果发布 fnOS package，运行 `./deploy/build_fpk.sh <version>` 从根源码重建 `deploy/nas-media-importer/`。
6. 不手动修改 `deploy/nas-media-importer/app/server/media_importer/`。
7. 记录版本变更和已知问题。
