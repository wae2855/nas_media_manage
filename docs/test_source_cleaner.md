# 源目录自动清理功能 — 联测用例文档

## 一、配置项总览

| 配置项 | 类型 | 可选值 | 默认值 | 说明 |
|--------|------|--------|--------|------|
| enabled | 开关 | true/false | false | 总开关，关闭时隐藏所有子配置 |
| cleanup_mode | 单选 | media_only / media_and_related | media_only | 清理模式 |
| ai_enabled | 开关 | true/false | false | AI辅助判断 |
| merge_strategy | 下拉 | intersection / union | intersection | 合并策略（仅AI开启时可见） |
| ai_prompt | 大文本 | 自由文本 | 预置提示词 | AI系统提示词（弹窗编辑） |
| delete_extensions | 大文本 | 后缀名列表 | .url,.log,.txt | 指定删除的后缀名 |
| protect_extensions | 大文本 | 后缀名列表 | .nfo,.jpg,.png | 指定保护的后缀名 |
| blacklist_patterns | 大文本 | 关键词/通配符列表 | RARBG*,*/Sample/*,*/sample/* | 黑名单模式 |
| junk_video_max_size_mb | 数字 | ≥0 | 50 | 垃圾视频大小阈值(MB)，0=不检测 |
| cleanup_empty_dirs | 开关 | true/false | true | 清理空目录 |
| schedule | 文本 | cron表达式 | 0 3 * * * | 执行时间 |

---

## 二、测试阶段一：配置界面保存验证

### TC-1.1 启用开关保存

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 打开配置→入库设置→源目录自动清理 | 开关未勾选，下方配置区域隐藏 |
| 2 | 勾选"启用源目录自动清理" | 下方配置区域展开显示 |
| 3 | 点击保存 | 提示保存成功 |
| 4 | 刷新页面重新加载配置 | 开关仍为勾选状态，配置区域可见 |

### TC-1.2 清理模式保存

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 选择"仅保留影视+字幕" | radio选中第一项 |
| 2 | 点击保存 | 保存成功 |
| 3 | 刷新页面 | 仍选中"仅保留影视+字幕" |
| 4 | 切换为"保留影视+字幕+相关文件" | radio选中第二项 |
| 5 | 点击保存 | 保存成功 |
| 6 | 刷新页面 | 仍选中"保留影视+字幕+相关文件" |

### TC-1.3 AI辅助判断 + 合并策略保存

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 勾选"AI辅助判断" | 合并策略下拉框和"AI清理提示词"按钮出现 |
| 2 | 合并策略选择"激进/并集" | 下拉框选中union |
| 3 | 点击保存 | 保存成功 |
| 4 | 刷新页面 | AI仍勾选，合并策略仍为union |
| 5 | 取消AI勾选 | 合并策略和提示词按钮隐藏 |
| 6 | 点击保存 | 保存成功 |
| 7 | 刷新页面 | AI未勾选，合并策略区域隐藏 |

### TC-1.4 AI清理提示词保存

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 勾选AI辅助判断 | "AI清理提示词"按钮出现 |
| 2 | 点击"AI清理提示词" | 弹窗打开，textarea可见 |
| 3 | 在textarea中输入自定义提示词内容 | 内容输入成功 |
| 4 | 点击"确定" | 弹窗关闭，提示"已暂存" |
| 5 | 点击保存 | 保存成功 |
| 6 | 刷新页面后再次打开提示词弹窗 | textarea中显示之前输入的自定义内容 |
| 7 | 点击"恢复默认" | textarea内容变为预置默认提示词 |
| 8 | 点击"确定"→保存 | 保存成功 |
| 9 | 刷新后再次打开弹窗 | 显示默认提示词 |

### TC-1.5 后缀名页签保存（三个tab互不干扰）

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 在"指定删除的后缀名"tab输入 .url .log .nfo | 内容输入成功 |
| 2 | 切换到"指定保护的后缀名"tab输入 .srt .ass .sup | 第一个tab内容不丢失 |
| 3 | 切换到"黑名单模式"tab输入 sample trailer 预告 | 前两个tab内容不丢失 |
| 4 | 点击保存 | 保存成功 |
| 5 | 刷新页面 | 三个tab各自内容正确保留 |
| 6 | 切换回"指定删除的后缀名"tab | 显示 .url .log .nfo |
| 7 | 切换到"指定保护的后缀名"tab | 显示 .srt .ass .sup |
| 8 | 切换到"黑名单模式"tab | 显示 sample trailer 预告 |

### TC-1.6 高级配置保存

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 展开"高级配置" | 垃圾视频大小阈值、清理空目录、执行时间可见 |
| 2 | 垃圾视频大小阈值设为 30 | 输入成功 |
| 3 | 勾选"清理空目录" | 开关打开 |
| 4 | 执行时间输入 0 4 * * * | 输入成功 |
| 5 | 点击保存 | 保存成功 |
| 6 | 刷新页面 | 高级配置默认折叠，展开后各值正确 |
| 7 | 垃圾视频大小阈值改为 0 | 输入成功 |
| 8 | 点击保存 | 保存成功 |
| 9 | 刷新页面 | 阈值显示为0 |

### TC-1.7 配置项互不干扰验证

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 设置清理模式=media_only，保存 | 成功 |
| 2 | 修改删除后缀名（添加.bak），保存 | 清理模式仍为media_only |
| 3 | 开启AI，设置合并策略=union，保存 | 清理模式和后缀名不变 |
| 4 | 关闭AI，保存 | 合并策略值保留但不生效（AI关闭） |
| 5 | 重新开启AI | 合并策略仍为union |
| 6 | 修改高级配置中的阈值，保存 | 其他配置项均不变 |

---

## 三、测试阶段二：BT下载文件结构测试数据

### 3.1 测试数据分类与目录结构

以下50个测试目录覆盖了市面上几乎所有BT下载的文件结构类型，每个目录模拟一个BT下载结果。

#### A. 标准电影（10个）

```
A01_标准电影_单视频单字幕/
├── The.Matrix.1999.1080p.BluRay.x264.mkv          (15GB)
├── The.Matrix.1999.1080p.BluRay.x264.srt           (80KB)
└── The.Matrix.1999.1080p.BluRay.x264.nfo           (5KB)

A02_标准电影_多字幕/
├── Inception.2010.2160p.UHD.BluRay.x265.mkv        (25GB)
├── Inception.2010.2160p.chi.srt                     (65KB)
├── Inception.2010.2160p.eng.srt                     (58KB)
├── Inception.2010.2160p.jpn.ass                     (42KB)
└── Inception.2010.nfo                               (3KB)

A03_电影_带海报和元数据/
├── Interstellar.2014.1080p.BluRay.mkv               (18GB)
├── Interstellar.2014.1080p.chi&eng.srt              (72KB)
├── Interstellar.2014.nfo                            (4KB)
├── Interstellar.2014-poster.jpg                     (350KB)
├── Interstellar.2014-fanart.jpg                     (800KB)
└── Interstellar.2014-banner.jpg                     (120KB)

A04_电影_带BT广告文件/
├── Parasite.2019.1080p.BluRay.x264.mkv             (12GB)
├── Parasite.2019.1080p.chi.srt                      (55KB)
├── www.YTS.mx.url                                   (1KB)
├── YTS.mx.txt                                       (2KB)
├── Parasite.2019.nfo                                (3KB)
└── Torrent-downloaded-from-demo.txt                 (1KB)

A05_电影_带广告图片/
├── 1917.2019.1080p.BluRay.x264.mkv                  (14GB)
├── 1917.2019.chi.srt                                (48KB)
├── RARBG.mp4                                        (8MB) ← 广告视频
├── RARBG.txt                                        (1KB)
├── RARBG.jpg                                        (150KB)
└── RARBG.do-not-mirror-this-folder.txt              (1KB)

A06_电影_带Sample目录/
├── Dunkirk.2017.1080p.BluRay.x264/
│   ├── Dunkirk.2017.1080p.BluRay.x264.mkv           (16GB)
│   ├── Dunkirk.2017.chi.srt                         (50KB)
│   └── Sample/
│       ├── Dunkirk.2017.1080p.Sample.mkv            (50MB)
│       └── Sample.nfo                               (1KB)

A07_电影_多版本同目录/
├── Blade.Runner.2049.2017.1080p.mkv                 (10GB)
├── Blade.Runner.2049.2017.720p.mkv                  (5GB)
├── Blade.Runner.2049.2017.chi.srt                   (45KB)
└── Blade.Runner.2049.2017.nfo                       (3KB)

A08_电影_蓝光原盘结构/
├── The.Godfather.1972.UHD.BluRay/
│   ├── BDMV/
│   │   ├── index.bdmv                               (1KB)
│   │   ├── MovieObject.bdmv                         (2KB)
│   │   ├── STREAM/
│   │   │   ├── 00001.m2ts                           (40GB)
│   │   │   └── 00002.m2ts                           (200MB)
│   │   ├── CLIPINF/
│   │   │   ├── 00001.clpi                           (5KB)
│   │   │   └── 00002.clpi                           (3KB)
│   │   └── PLAYLIST/
│   │       └── 00001.mpls                           (1KB)
│   ├── CERTIFICATE/
│   │   └── id.bdmv                                  (1KB)
│   └── The.Godfather.1972.nfo                       (4KB)

A09_电影_极小视频混淆/
├── Avatar.2009.1080p.mkv                            (20GB)
├── Avatar.2009.chi.srt                              (60KB)
├── Avatar.2009.Trailer.1080p.mkv                    (180MB) ← 同名预告片
├── Avatar.2009.Behind.the.Scenes.mkv                (300MB) ← 花絮
└── Avatar.2009.nfo                                  (3KB)

A10_电影_纯视频无其他/
├── The.Shawshank.Redemption.1994.1080p.mkv          (12GB)
└── (无其他文件)
```

#### B. 电视剧/剧集（8个）

```
B01_剧集_标准S01结构/
├── Breaking.Bad.S01/
│   ├── Breaking.Bad.S01E01.1080p.mkv                (4GB)
│   ├── Breaking.Bad.S01E02.1080p.mkv                (3.8GB)
│   ├── Breaking.Bad.S01E03.1080p.mkv                (4.2GB)
│   ├── Breaking.Bad.S01E01.chi.srt                  (40KB)
│   ├── Breaking.Bad.S01E02.chi.srt                  (38KB)
│   └── Breaking.Bad.S01E03.chi.srt                  (42KB)

B02_剧集_带季封面/
├── Game.of.Thrones.S02/
│   ├── Game.of.Thrones.S02E01.1080p.mkv             (3.5GB)
│   ├── Game.of.Thrones.S02E02.1080p.mkv             (3.2GB)
│   ├── Game.of.Thrones.S02.nfo                      (5KB)
│   ├── Season02-poster.jpg                          (200KB)
│   └── fanart.jpg                                   (500KB)

B03_剧集_带广告和说明/
├── The.Witcher.S01/
│   ├── The.Witcher.S01E01.2160p.mkv                 (8GB)
│   ├── The.Witcher.S01E02.2160p.mkv                 (7.5GB)
│   ├── The.Witcher.S01E01.chi.srt                   (45KB)
│   ├── The.Witcher.S01E02.chi.srt                   (42KB)
│   ├── Downloaded.from.1337x.txt                    (2KB)
│   ├── www.1337x.to.url                             (1KB)
│   └── The.Witcher.S01.nfo                          (3KB)

B04_剧集_多季混合/
├── Stranger.Things/
│   ├── Season 1/
│   │   ├── Stranger.Things.S01E01.1080p.mkv         (3GB)
│   │   └── Stranger.Things.S01E01.chi.srt           (35KB)
│   ├── Season 2/
│   │   ├── Stranger.Things.S02E01.1080p.mkv         (3.5GB)
│   │   └── Stranger.Things.S02E01.chi.srt           (38KB)
│   └── tvshow.nfo                                   (4KB)

B05_剧集_带预告目录/
├── The.Mandalorian.S01/
│   ├── The.Mandalorian.S01E01.2160p.mkv             (6GB)
│   ├── The.Mandalorian.S01E02.2160p.mkv             (5.8GB)
│   ├── Trailers/
│   │   ├── S01.Trailer.1080p.mkv                    (120MB)
│   │   └── S01.Teaser.720p.mkv                      (60MB)
│   └── The.Mandalorian.S01.nfo                      (3KB)

B06_剧集_带花絮目录/
├── Chernobyl.S01/
│   ├── Chernobyl.S01E01.1080p.mkv                   (4GB)
│   ├── Chernobyl.S01E02.1080p.mkv                   (3.8GB)
│   ├── Extras/
│   │   ├── Behind.the.Scenes.1080p.mkv              (500MB)
│   │   └── Interview.1080p.mkv                      (300MB)
│   └── Chernobyl.S01.nfo                            (3KB)

B07_剧集_整季单文件/
├── The.Office.S03/
│   ├── The.Office.S03E01-E10.1080p.mkv              (15GB)
│   ├── The.Office.S03.chi.srt                       (120KB)
│   └── The.Office.S03.nfo                           (4KB)

B08_剧集_带字幕子目录/
├── Money.Heist.S01/
│   ├── Money.Heist.S01E01.1080p.mkv                 (3.5GB)
│   ├── Money.Heist.S01E02.1080p.mkv                 (3.2GB)
│   ├── Subs/
│   │   ├── Money.Heist.S01E01.chi.srt               (38KB)
│   │   ├── Money.Heist.S01E01.eng.srt               (35KB)
│   │   ├── Money.Heist.S01E02.chi.srt               (36KB)
│   │   └── Money.Heist.S01E02.eng.srt               (33KB)
│   └── Money.Heist.S01.nfo                          (3KB)
```

#### C. 动画/动漫（6个）

```
C01_动漫_标准结构/
├── [SubGroup] Sword Art Online - 01 [1080p].mkv     (1.2GB)
├── [SubGroup] Sword Art Online - 02 [1080p].mkv     (1.1GB)
├── [SubGroup] Sword Art Online - 01.chi.ass          (25KB)
└── [SubGroup] Sword Art Online - 02.chi.ass          (23KB)

C02_动漫_带字体文件/
├── [ANIME-GROUP] Demon Slayer - 01 [1080p].mkv      (1.5GB)
├── [ANIME-GROUP] Demon Slayer - 02 [1080p].mkv      (1.4GB)
├── [ANIME-GROUP] Demon Slayer - 01.chi.ass           (30KB)
├── Fonts/
│   ├── font1.ttf                                    (5MB)
│   ├── font2.otf                                    (3MB)
│   └── font3.ttf                                    (4MB)
└── [ANIME-GROUP] Demon Slayer.nfo                   (2KB)

C03_动漫_带CD镜像/
├── [R2J] Evangelion - 01 [BD 1080p].mkv             (2GB)
├── [R2J] Evangelion - 02 [BD 1080p].mkv             (1.8GB)
├── [R2J] Evangelion - 01.chi.ass                    (28KB)
├── CD/
│   ├── OST01.flac                                   (40MB)
│   ├── OST02.flac                                   (35MB)
│   └── cover.jpg                                    (200KB)
└── [R2J] Evangelion.nfo                             (2KB)

C04_动漫_带SP和OVA/
├── [GROUP] Attack on Titan - 01 [1080p].mkv         (1.3GB)
├── [GROUP] Attack on Titan - 02 [1080p].mkv         (1.2GB)
├── [GROUP] Attack on Titan - SP01 [1080p].mkv       (200MB) ← SP特别篇
├── [GROUP] Attack on Titan - OAD01 [1080p].mkv      (500MB) ← OVA
├── [GROUP] Attack on Titan - 01.chi.ass              (22KB)
└── [GROUP] Attack on Titan.nfo                      (2KB)

C05_动漫_带广告图片/
├── [SubGroup] One Piece - 1000 [1080p].mkv          (800MB)
├── [SubGroup] One Piece - 1001 [1080p].mkv          (780MB)
├── [SubGroup] One Piece - 1000.chi.ass               (20KB)
├── [SubGroup] ad_banner.jpg                         (100KB) ← 广告横幅
├── [SubGroup] recruitment.txt                       (2KB) ← 招新广告
└── [SubGroup] One Piece.nfo                         (1KB)

C06_动漫_内封字幕无外挂/
├── [GROUP] Jujutsu Kaisen - 01 [1080p].mkv          (1.1GB)
├── [GROUP] Jujutsu Kaisen - 02 [1080p].mkv          (1.0GB)
└── (无字幕文件，字幕内封)
```

#### D. 纪录片/特别篇（5个）

```
D01_纪录片_标准/
├── Planet.Earth.III.S01E01.2160p.mkv                (8GB)
├── Planet.Earth.III.S01E02.2160p.mkv                (7.5GB)
├── Planet.Earth.III.S01E01.chi.srt                  (50KB)
└── Planet.Earth.III.nfo                             (3KB)

D02_纪录片_带花絮/
├── Blue.Planet.II.S01E01.1080p.mkv                  (5GB)
├── Blue.Planet.II.S01E02.1080p.mkv                  (4.8GB)
├── Extras/
│   ├── Behind.the.Lens.1080p.mkv                    (400MB)
│   └── Interview.1080p.mkv                          (250MB)
└── Blue.Planet.II.nfo                               (3KB)

D03_特别篇_单文件/
├── The.World.At.War.1973.1080p.Remastered.mkv       (8GB)
└── The.World.At.War.1973.nfo                        (4KB)

D04_纪录片_带PDF手册/
├── Cosmos.A.Spacetime.Odyssey.S01E01.1080p.mkv      (4GB)
├── Cosmos.A.Spacetime.Odyssey.S01E02.1080p.mkv      (3.8GB)
├── Cosmos.A.Spacetime.Odyssey.S01E01.chi.srt        (42KB)
├── Study.Guide.pdf                                  (15MB) ← 学习手册
└── Cosmos.nfo                                       (2KB)

D05_纪录片_带ISO/
├── National.Geographic.Collection/
│   ├── NatGeo.Ep01.1080p.mkv                        (3GB)
│   ├── NatGeo.Ep02.1080p.mkv                        (2.8GB)
│   └── Bonus_Disc.iso                               (4.7GB) ← ISO镜像
```

#### E. PT站/高质量资源（6个）

```
E01_PT站_带NFO和截图/
├── 2001.A.Space.Odyssey.1968.2160p.UHD.BluRay.REMUX.mkv (55GB)
├── 2001.A.Space.Odyssey.1968.chi.srt                (55KB)
├── 2001.A.Space.Odyssey.1968.nfo                    (8KB)
├── 2001.A.Space.Odyssey.1968-thumb1.jpg             (300KB)
├── 2001.A.Space.Odyssey.1968-thumb2.jpg             (280KB)
├── 2001.A.Space.Odyssey.1968-thumb3.jpg             (310KB)
└── 2001.A.Space.Odyssey.1968-thumb4.jpg             (290KB)

E02_PT站_带MediaInfo/
├── Lawrence.of.Arabia.1962.1080p.BluRay.REMUX.mkv   (40GB)
├── Lawrence.of.Arabia.1962.chi.srt                   (48KB)
├── Lawrence.of.Arabia.1962.nfo                       (6KB)
├── MediaInfo.txt                                     (3KB) ← MediaInfo报告
└── Lawrence.of.Arabia.1962-poster.jpg                (250KB)

E03_PT站_多CD结构/
├── Schindlers.List.1993.1080p.BluRay/
│   ├── CD1/
│   │   └── Schindlers.List.1993.CD1.1080p.mkv       (8GB)
│   ├── CD2/
│   │   └── Schindlers.List.1993.CD2.1080p.mkv       (7GB)
│   ├── Schindlers.List.1993.chi.srt                 (55KB)
│   └── Schindlers.List.1993.nfo                     (5KB)

E04_PT站_带校验文件/
├── The.Seven.Samurai.1954.1080p.BluRay.mkv          (15GB)
├── The.Seven.Samurai.1954.chi.srt                    (40KB)
├── The.Seven.Samurai.1954.nfo                        (4KB)
├── The.Seven.Samurai.1954.sfv                        (2KB) ← SFV校验
└── The.Seven.Samurai.1954.nfo.bak                    (4KB) ← NFO备份

E05_PT站_REMUX带完整结构/
├── Casablanca.1942.1080p.BluRay.REMUX/
│   ├── Casablanca.1942.1080p.REMUX.mkv              (30GB)
│   ├── Casablanca.1942.chi.srt                      (35KB)
│   ├── Casablanca.1942.nfo                           (5KB)
│   ├── Casablanca.1942-poster.jpg                    (200KB)
│   └── Proof/
│       └── proof.jpg                                 (150KB) ← 发布证明

E06_PT站_带说明文件/
├── Citizen.Kane.1941.1080p.BluRay.mkv               (12GB)
├── Citizen.Kane.1941.chi.srt                         (38KB)
├── Citizen.Kane.1941.nfo                             (4KB)
├── README.txt                                        (3KB) ← 说明文件
└── Torrent.Info.txt                                  (2KB) ← 种子信息
```

#### F. 混合/特殊场景（10个）

```
F01_混淆广告_同名小视频/
├── The.Dark.Knight.2008.1080p.mkv                    (15GB)
├── The.Dark.Knight.2008.chi.srt                      (52KB)
├── The.Dark.Knight.2008.mkv                          (20MB) ← 同名广告视频！
└── The.Dark.Knight.2008.nfo                          (3KB)

F02_混淆广告_大小写变体/
├── Inception.2010.1080p.mkv                          (12GB)
├── Inception.2010.chi.srt                            (48KB)
├── SAMPLE.mp4                                        (5MB) ← 大写SAMPLE
└── Trailer.720p.mp4                                  (30MB) ← 预告片

F03_中文资源_带说明/
├── 让子弹飞.2010.1080p.BluRay.mkv                    (10GB)
├── 让子弹飞.2010.chi.srt                             (40KB)
├── 让子弹飞.2010.nfo                                 (3KB)
├── 下载说明.txt                                      (2KB)
├── 免责声明.txt                                      (1KB)
└── 关注公众号获取更多.txt                             (1KB)

F04_中文资源_带预告/
├── 流浪地球2.2023.2160p.mkv                          (25GB)
├── 流浪地球2.2023.chi.srt                            (55KB)
├── 流浪地球2.预告片.1080p.mkv                        (150MB) ← 中文预告
├── 流浪地球2.花絮.720p.mkv                           (200MB) ← 花絮
└── 流浪地球2.nfo                                     (3KB)

F05_空目录_清理后残留/
├── (空目录，无任何文件)

F06_深层嵌套_空目录/
├── Movie.Collection/
│   └── Action/
│       └── (空目录)

F07_混合文件_全类型/
├── Everything.Everywhere.2022.1080p.mkv              (10GB)
├── Everything.Everywhere.2022.chi.srt                (45KB)
├── Everything.Everywhere.2022.nfo                    (3KB)
├── poster.jpg                                        (200KB)
├── fanart.png                                        (500KB)
├── banner.jpg                                        (100KB)
├── www.demo-site.com.url                             (1KB)
├── download-info.txt                                 (2KB)
├── Sample.mkv                                        (30MB)
├── RARBG.mp4                                         (8MB)
├── .DS_Store                                         (6KB)
└── Thumbs.db                                         (20KB)

F08_纯音频_非影视/
├── Album.Collection/
│   ├── track01.flac                                  (40MB)
│   ├── track02.flac                                  (35MB)
│   ├── track03.flac                                  (38MB)
│   ├── cover.jpg                                     (200KB)
│   └── playlist.m3u                                  (1KB)

F09_软件/游戏_非影视/
├── Some.Software.2024/
│   ├── setup.exe                                     (50MB)
│   ├── readme.txt                                    (5KB)
│   ├── crack/
│   │   └── patch.exe                                 (10MB)
│   └── docs/
│       └── manual.pdf                                (8MB)

F10_图片集_非影视/
├── Photo.Collection/
│   ├── IMG_001.jpg                                   (5MB)
│   ├── IMG_002.jpg                                   (4MB)
│   ├── IMG_003.png                                   (6MB)
│   └── metadata.json                                 (2KB)
```

#### G. 极端/边界场景（5个）

```
G01_超大文件_4KREMUX/
├── Ben.Hur.1959.2160p.UHD.BluRay.REMUX.mkv          (80GB)
├── Ben.Hur.1959.chi.srt                              (60KB)
└── Ben.Hur.1959.nfo                                  (5KB)

G02_极小视频_短视频广告/
├── Ad.Videos/
│   ├── ad001.mp4                                     (2MB)
│   ├── ad002.mp4                                     (3MB)
│   ├── ad003.mp4                                     (1.5MB)
│   └── ad004.mp4                                     (2.5MB)

G03_零字节文件/
├── Empty.Files/
│   ├── movie.mkv                                     (0字节)
│   ├── subtitle.srt                                  (0字节)
│   └── info.nfo                                      (0字节)

G04_特殊字符文件名/
├── 特殊字符测试/
│   ├── 电影[2024][4K].mkv                            (5GB)
│   ├── 电影[2024].chi.srt                            (30KB)
│   ├── 电影's cut.nfo                                (2KB)
│   └── 电影 & 更多.jpg                               (100KB)

G05_隐藏文件/
├── Hidden.Files/
│   ├── Movie.2024.1080p.mkv                          (8GB)
│   ├── .hidden_file                                  (1KB)
│   ├── .gitkeep                                      (0字节)
│   └── Movie.2024.chi.srt                            (35KB)
```

### 3.2 测试数据预期分类表

| 编号 | 目录名 | 应保留 | 应删除 | 关键判定点 |
|------|--------|--------|--------|------------|
| A01 | 标准电影 | mkv,srt,nfo | 无 | nfo保护 |
| A02 | 多字幕 | mkv,srt,ass,nfo | 无 | 多字幕保留 |
| A03 | 带海报 | mkv,srt,nfo,jpg | 无 | 海报保护 |
| A04 | BT广告 | mkv,srt,nfo | .url,.txt | 删除后缀命中 |
| A05 | 广告图片 | mkv,srt | RARBG.mp4,RARBG.txt,RARBG.jpg | 垃圾视频+删除后缀 |
| A06 | Sample目录 | 主mkv,srt | Sample/整目录 | 黑名单目录 |
| A07 | 多版本 | 两个mkv,srt,nfo | 无 | 两个都是正常视频 |
| A08 | 蓝光原盘 | m2ts,bdmv,mpls,clpi,nfo | 无 | media_and_related应保留 |
| A09 | 极小视频混淆 | 主mkv(20G),srt,nfo | Trailer(180M),Behind(300M) | 垃圾视频阈值判定 |
| A10 | 纯视频 | mkv | 无 | 最简结构 |
| B01 | 标准剧集 | mkv,srt | 无 | 多集保留 |
| B02 | 带季封面 | mkv,nfo,jpg | 无 | 海报保护 |
| B03 | 带广告 | mkv,srt,nfo | .txt,.url | 删除后缀命中 |
| B04 | 多季混合 | mkv,srt,nfo | 无 | 嵌套目录 |
| B05 | 预告目录 | 主集mkv | Trailers/整目录 | 黑名单目录 |
| B06 | 花絮目录 | 主集mkv,nfo | Extras/整目录 | 黑名单目录 |
| B07 | 整季单文件 | mkv,srt,nfo | 无 | 大文件保留 |
| B08 | 字幕子目录 | mkv,srt,nfo | 无 | Subs/内字幕保留 |
| C01 | 标准动漫 | mkv,ass | 无 | ass字幕保留 |
| C02 | 带字体 | mkv,ass,nfo | Fonts/目录 | media_only:删除; media_and_related:保留 |
| C03 | 带CD镜像 | mkv,ass,nfo | CD/(flac,jpg) | 非影视文件 |
| C04 | SP和OVA | 全部mkv,ass,nfo | 无 | SP/OVA也是正片 |
| C05 | 广告图片 | mkv,ass,nfo | ad_banner.jpg,recruitment.txt | 删除后缀+非媒体 |
| C06 | 内封字幕 | mkv | 无 | 无外挂字幕 |
| D01 | 标准纪录片 | mkv,srt,nfo | 无 | 同剧集逻辑 |
| D02 | 带花絮 | 主集mkv,nfo | Extras/整目录 | 黑名单目录 |
| D03 | 单文件 | mkv,nfo | 无 | 最简 |
| D04 | 带PDF | mkv,srt | pdf,nfo | media_only:删除pdf; media_and_related:保留nfo |
| D05 | 带ISO | mkv | iso | 非影视文件 |
| E01 | PT截图 | mkv,srt,nfo,jpg | 无 | 截图保护 |
| E02 | MediaInfo | mkv,srt,nfo,jpg | MediaInfo.txt | 删除后缀 |
| E03 | 多CD | mkv,srt,nfo | 无 | CD子目录内视频保留 |
| E04 | 校验文件 | mkv,srt,nfo | sfv,bak | 删除后缀 |
| E05 | REMUX | mkv,srt,nfo,jpg | proof/ | media_only:删除proof; media_and_related:保留 |
| E06 | 说明文件 | mkv,srt,nfo | txt | 删除后缀 |
| F01 | 同名广告 | 主mkv(15G),srt,nfo | 小mkv(20M) | 垃圾视频阈值 |
| F02 | 大小写变体 | 主mkv,srt | SAMPLE.mp4,Trailer.mp4 | 垃圾视频+黑名单 |
| F03 | 中文资源 | mkv,srt,nfo | txt | 删除后缀 |
| F04 | 中文预告 | 主mkv,srt,nfo | 预告mkv,花絮mkv | 垃圾视频阈值 |
| F05 | 空目录 | 无 | 整个空目录 | cleanup_empty_dirs |
| F06 | 深层空目录 | 无 | 整个空目录 | cleanup_empty_dirs |
| F07 | 全类型 | mkv,srt,nfo,jpg,png | url,txt,Sample.mkv,RARBG.mp4,.DS_Store,Thumbs.db | 综合判定 |
| F08 | 纯音频 | 无(media_only) | flac,jpg,m3u | 非影视文件 |
| F09 | 软件 | 无 | exe,txt,pdf | 非影视文件 |
| F10 | 图片集 | 无 | jpg,png,json | 非影视文件 |
| G01 | 超大文件 | mkv,srt,nfo | 无 | 大文件保留 |
| G02 | 极小视频 | 无 | mp4 | 全部垃圾视频 |
| G03 | 零字节 | mkv(0B) | srt(0B),nfo(0B) | 零字节边界 |
| G04 | 特殊字符 | mkv,srt,nfo,jpg | 无 | 特殊字符路径 |
| G05 | 隐藏文件 | mkv,srt | .hidden_file,.gitkeep | 非媒体文件 |

---

## 四、测试阶段三：最优配置调优

### 4.1 推荐最优配置

基于上述50个测试数据，通过【预览清理结果】反复验证，推荐以下最优配置：

```yaml
source_cleaner:
  enabled: true
  cleanup_mode: media_and_related
  ai_enabled: false            # 阶段三先不开启AI，纯规则验证
  merge_strategy: intersection
  delete_extensions:
    - .url
    - .log
    - .txt
    - .sfv
    - .bak
    - .m3u
    - .db
  protect_extensions:
    - .nfo
    - .jpg
    - .png
    - .bdmv
    - .clpi
    - .mpls
  blacklist_patterns:
    - RARBG*
    - "*/Sample/*"
    - "*/sample/*"
    - "*/Trailers/*"
    - "*/trailers/*"
    - "*/预告/*"
    - "*/花絮/*"
    - "*/Extras/*"
    - "*/extras/*"
  junk_video_max_size_mb: 50
  cleanup_empty_dirs: true
  schedule: "0 3 * * *"
```

### 4.2 配置调优验证步骤

| 步骤 | 操作 | 验证点 |
|------|------|--------|
| 1 | 使用默认配置，点击【预览清理结果】 | 记录默认配置下的清理结果 |
| 2 | 添加 .sfv,.bak,.m3u,.db 到删除后缀名 | 验证E04/F08等用例是否命中 |
| 3 | 添加 .bdmv,.clpi,.mpls 到保护后缀名 | 验证A08蓝光原盘结构是否保留 |
| 4 | 添加 Trailers/预告/花絮/Extras 到黑名单 | 验证B05/B06/D02目录是否命中 |
| 5 | 设置垃圾视频阈值为50MB | 验证A09/F01/F02/G02小视频是否命中 |
| 6 | 切换为 media_only 模式 | 验证A03海报/A08蓝光结构是否被误删 |
| 7 | 切换回 media_and_related 模式 | 验证海报/元数据保留 |
| 8 | 每次调整后点击【预览清理结果】 | 对比3.2预期分类表，确认结果一致 |

### 4.3 关键判定规则对照

| 场景 | media_only | media_and_related | 判定依据 |
|------|-----------|-------------------|----------|
| .nfo元数据 | 删除 | 保留 | protect_extensions |
| .jpg/.png海报 | 删除 | 保留 | protect_extensions |
| .bdmv/.clpi蓝光 | 删除 | 保留 | protect_extensions |
| .url/.txt广告 | 删除 | 删除 | delete_extensions |
| Sample/目录 | 删除 | 删除 | blacklist_patterns |
| 50MB以下视频 | 删除 | 删除 | junk_video_max_size_mb |
| .flac音频 | 删除 | 删除 | 非媒体非保护 |
| .iso镜像 | 删除 | 删除 | 非媒体非保护 |
| Fonts/目录 | 删除 | 保留(关联) | _is_companion_file |
| Subs/字幕目录 | 删除 | 保留(关联) | _is_companion_file |

---

## 五、测试阶段四：配置组合笛卡尔积测试

### 5.1 配置维度与取值

| 维度 | 取值数 | 取值列表 |
|------|--------|----------|
| D1: cleanup_mode | 2 | media_only, media_and_related |
| D2: ai_enabled | 2 | false, true |
| D3: merge_strategy | 2 | intersection, union |
| D4: junk_video_max_size_mb | 3 | 0(不检测), 50(推荐), 200(宽松) |
| D5: cleanup_empty_dirs | 2 | true, false |
| D6: delete_extensions | 2 | 默认(.url,.log,.txt), 扩展(+.sfv,.bak,.m3u,.db) |
| D7: protect_extensions | 2 | 默认(.nfo,.jpg,.png), 扩展(+.bdmv,.clpi,.mpls) |

**全量笛卡尔积**: 2×2×2×3×2×2×2 = **192种组合**

### 5.2 简化测试矩阵

AI关闭时 merge_strategy 无实际影响，可简化。按实际有意义组合缩减：

| 组号 | mode | ai | merge | junk_mb | empty_dirs | del_ext | prot_ext | 说明 |
|------|------|-----|-------|---------|------------|---------|----------|------|
| 1 | media_only | off | - | 50 | on | 默认 | 默认 | 基线：纯规则保守 |
| 2 | media_only | off | - | 0 | on | 默认 | 默认 | 无垃圾视频检测 |
| 3 | media_only | off | - | 50 | off | 默认 | 默认 | 不清空目录 |
| 4 | media_only | off | - | 50 | on | 扩展 | 默认 | 扩展删除后缀 |
| 5 | media_only | off | - | 50 | on | 默认 | 扩展 | 扩展保护后缀 |
| 6 | media_only | off | - | 50 | on | 扩展 | 扩展 | 双扩展 |
| 7 | media_only | off | - | 200 | on | 默认 | 默认 | 宽松垃圾阈值 |
| 8 | media_and_related | off | - | 50 | on | 默认 | 默认 | 基线：关联模式 |
| 9 | media_and_related | off | - | 0 | on | 默认 | 默认 | 无垃圾视频检测 |
| 10 | media_and_related | off | - | 50 | off | 默认 | 默认 | 不清空目录 |
| 11 | media_and_related | off | - | 50 | on | 扩展 | 默认 | 扩展删除后缀 |
| 12 | media_and_related | off | - | 50 | on | 默认 | 扩展 | 扩展保护后缀 |
| 13 | media_and_related | off | - | 50 | on | 扩展 | 扩展 | 双扩展 |
| 14 | media_and_related | off | - | 200 | on | 默认 | 默认 | 宽松垃圾阈值 |
| 15 | media_only | on | intersection | 50 | on | 默认 | 默认 | AI交集保守 |
| 16 | media_only | on | union | 50 | on | 默认 | 默认 | AI并集激进 |
| 17 | media_and_related | on | intersection | 50 | on | 默认 | 默认 | 关联+AI交集 |
| 18 | media_and_related | on | union | 50 | on | 默认 | 默认 | 关联+AI并集 |
| 19 | media_only | on | intersection | 0 | on | 扩展 | 扩展 | AI交集+全扩展 |
| 20 | media_and_related | on | union | 200 | on | 扩展 | 扩展 | AI并集+全扩展 |

### 5.3 每组测试验证要点

每组组合执行以下步骤：
1. 设置对应配置并保存
2. 点击【预览清理结果】
3. 对照3.2预期分类表验证结果
4. 记录误删（应保留被删）和漏删（应删未删）数量

**关键验证矩阵**（每组必须检查的场景）：

| 验证点 | 涉及测试数据 | media_only预期 | media_and_related预期 |
|--------|-------------|---------------|----------------------|
| 海报保留 | A03 | 删除 | 保留 |
| NFO保留 | A01 | 删除 | 保留 |
| 蓝光结构 | A08 | 删除bdmv等 | 保留 |
| 广告url/txt | A04 | 删除 | 删除 |
| RARBG广告 | A05 | 删除 | 删除 |
| Sample目录 | A06 | 删除整目录 | 删除整目录 |
| 垃圾视频 | A09 | <50MB删除 | <50MB删除 |
| 同名小视频 | F01 | <50MB删除 | <50MB删除 |
| 字幕子目录 | B08 | 删除Subs/ | 保留Subs/ |
| 字体目录 | C02 | 删除Fonts/ | 保留Fonts/ |
| 空目录 | F05 | 删除 | 删除 |
| 纯音频 | F08 | 全删 | 全删 |
| 零字节 | G03 | 视频保留,其他删 | nfo保留,其他删 |
| 隐藏文件 | G05 | 删除 | 删除 |

### 5.4 AI组合专项验证

AI开启的组合（15-20）额外验证：

| 验证点 | 预期行为(intersection) | 预期行为(union) |
|--------|----------------------|----------------|
| 规则判定删除+AI判定保留 | 不删除(交集需双方同意) | 删除(并集任一即删) |
| 规则判定保留+AI判定删除 | 不删除 | 删除 |
| 规则+AI都判定删除 | 删除 | 删除 |
| 规则+AI都判定保留 | 保留 | 保留 |
| AI识别广告视频(规则未覆盖) | 不删除(交集) | 删除(并集) |

**AI专项测试数据**：F01(同名小视频)是最关键的AI测试场景——规则可能因同名无法区分，AI应通过容量对比识别。

### 5.5 缺陷等级定义

| 等级 | 定义 | 示例 |
|------|------|------|
| P0-致命 | 正片视频被误删 | 15GB主电影被清理 |
| P1-严重 | 字幕/海报被误删 | .srt字幕文件被清理 |
| P2-一般 | 垃圾文件漏删 | .url广告文件未被清理 |
| P3-轻微 | 空目录未清理 | cleanup_empty_dirs=true但空目录仍在 |
| P4-建议 | 优化建议 | 垃圾视频阈值建议值调整 |

---

## 六、测试执行流程

```
阶段一：配置保存验证 (TC-1.1 ~ TC-1.7)
    ↓ 全部通过
阶段二：生成测试数据 (50个目录)
    ↓ 数据就绪
阶段三：最优配置调优 (4.2步骤 + 4.3对照)
    ↓ 配置确定
阶段四：笛卡尔积测试 (20组组合 × 14个验证点)
    ↓ 全部通过
输出：测试报告 + 最优配置 + 缺陷清单
```
