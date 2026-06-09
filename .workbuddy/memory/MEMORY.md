# 项目记忆

## 首页海报墙设计
- 从原始3条胶片条改为3D胶卷轮转（reel wheel）效果
- 帧尺寸与任务卡片缩略图一致（92×138px，2:3海报比例），含左右胶片孔
- 布局：hero grid 从 `1fr 340px` 改为 `1fr 2fr`（右侧占2/3）
- 进度条（now-strip）从独立 spotlight 区域移到左侧 hero-copy 的按钮下方
- 帧间距系数从1.15调整为1.6，基线半径从180增加到220

## 缩略图 API
- 新增 `/api/thumbnails`（GET）— 列出 source_dir/Thumbnail 下的图片
- 新增 `/api/thumbnails/{filename}`（GET）— 提供单张缩略图文件服务
- 后端实现在 `api/thumbnail_handlers.py`（ThumbnailHandlersMixin）
- 前端 `loadReelWheelFromTasks()` 优先使用缩略图API，无图时回退到任务封面色
- 缩略图30秒客户端缓存，避免重复请求

## 任务卡片缩略图
- 任务卡片使用纯色渐变封面（`.cover-gold`/`.cover-red`/`.cover-cyan`），非真实图片
- 任务数据中无 `poster_image` 或 `thumbnail` 字段
- `getTaskTone(task)` 根据 status 返回 "gold"/"red"/"cyan"
