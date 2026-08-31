# 目标片库冲突确认与安全替换

REQ-20260831-004019 已于 2026-08-31 完成本地实施和自评审，当前等待 fnOS 实机验收。

本次确立“目标片库默认只新增”边界：冲突检测零写入，普通/批量确认不能绕过，用户逐项选择保留现有、保留两份或安全替换；替换只走本地回收并禁止永久删除降级。

验证证据：定向回归 112 项通过；全量测试 783 项、181 个子测试通过；桌面 1440px 与手机 390px 真实浏览器预览无 console error。

- [Proposal](2026-08-31-target-library-conflict-safety.md)
- [Plan](2026-08-31-feat-target-library-conflict-safety-plan.md)
- [ADR-0018](../../decisions/0018-target-library-additive-conflict-boundary.md)
