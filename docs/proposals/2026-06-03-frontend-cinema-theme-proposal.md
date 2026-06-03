# Frontend Cinema Theme Proposal

## Direction

新前端建议采用“移动优先的私人影院控制台”方向，而不是传统 PC 管理后台。

关键词：

- 黑色底色：接近影院环境，降低灰蒙蒙观感。
- 金色主操作：用于扫描、确认、保存、恢复等关键动作。
- 少量红/绿/青状态色：只服务于失败、成功、进行中，不参与大面积装饰。
- 写实海报墙：顶部用影片海报墙/片库氛围建立影院感。
- 大卡片入口：移动端优先，桌面端只是横向扩展，而不是反过来。
- 首页减负：只显示当前最需要判断和操作的信息。

## Theme Tokens

| Token | Use |
|-------|-----|
| `#050505` | App background |
| `#11100d` | Card and panel background |
| `#eabf63` | Primary gold action |
| `#f6d98b` | Highlight text and active state |
| `#9b927f` | Secondary text |
| `#d94f45` | Failure / danger |
| `#26c281` | Success / running |
| `#43c7b7` | Active progress accent |

## Homepage Recommendation

已确认保留：

- 运行状态。
- 当前待处理数量。
- 今日/本轮入库数量。
- 需要人工确认或失败数量。
- 当前正在处理的影片。
- 最近活动。
- 顶部快速动作：立即扫描、暂停、重试失败。
- 3 个首页大入口：任务列表、回收站、系统配置。

移走到子页面：

- 详细系统健康表格。
- 大量路径文字。
- 配置明细。
- 低频诊断信息。
- 长任务列表。
- 独立快速操作面板。

这些内容放入二级工作区或详情页。

## Mobile Structure

移动端底部导航建议固定为 5 个入口：

1. 首页
2. 任务
3. 规则
4. AI
5. 系统

回收站保留为首页大卡片入口；系统健康、源目录清理和详细配置进入系统配置页。

## Prototype

静态原型：

- `docs/prototypes/cinema-dashboard-demo.html`
- `docs/prototypes/cinema-dashboard-demo.css`
- `docs/prototypes/cinema-task-list-demo.html`
- `docs/prototypes/cinema-recycle-demo.html`
- `docs/prototypes/cinema-config-demo.html`
- `docs/prototypes/cinema-subpage-demo.css`

该原型只用于确认视觉方向和首页信息架构，不作为最终实现。

## Confirmed Decisions

- 首页电影感偏写实海报墙。
- 移动端底部导航固定 5 项。
- 首页不显示系统健康，移动到系统页。
- 最近活动保留在首页当前下方位置。
- 顶部主按钮是立即扫描，旁边按钮是暂停和重试失败。
- 首页中间只保留 3 个大入口：任务列表、回收站、系统配置。
- 系统配置采用移动端步骤卡模式，优先展示目录配置、影视刮削配置、AI配置、定时任务。
- 配置卡片点击后进入独立配置页面，不在配置首页内锚点跳转。
- 默认只展示 01-04 主步骤；更多配置项通过向下提示按钮展开，展开后显示 05-11 一行卡片。

## Configuration IA

主步骤：

1. 目录配置：进入独立页面，按源目录 → 中转目录 → 回收站目录 → 入库规则展示。
2. 影视刮削配置：承接旧页面 `AI刮削 / 元数据源配置`。
3. AI配置：承接旧页面 `AI刮削 / LLM配置`。
4. 定时任务：承接旧页面 `高级配置 / 轮询监控配置`。

更多配置项：

- 入库名称规范：承接旧页面 `入库设置 / 入库选项`；其中“启用入库前检查”迁到入库规则。
- 影视分类维度：承接旧页面 `入库设置 / 影视分类配置`。
- AI刮削提示词：承接旧页面 `AI刮削 / AI刮削提示词` 折叠区。
- 置信度计算配置：承接旧页面 `AI刮削 / 置信度计算配置`。
- 安全配置：承接旧页面 `通知安全 / API安全配置`。
- Hermes通知：承接旧页面 `通知安全 / Hermes通知`。
- 系统设置：承接旧页面 `通知安全 / 高级配置`。

## Next Open Question

下一步需要把系统配置页每个卡片点击后的真实配置表单重新设计为移动端友好的分步界面。
