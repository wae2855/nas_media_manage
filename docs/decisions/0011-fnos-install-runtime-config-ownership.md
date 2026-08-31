# ADR-0011: fnOS 安装与运行配置归属

Date: 2026-08-28
Status: Accepted
Requirement: REQ-20260828-151346

Amended: 2026-08-30（fnOS 托管端口与服务认证迁移）

Amended: 2026-08-31（空服务认证下仅回环监听）

## Context

当前安装向导只采集端口；安装回调会创建应用私有目录并修改 YAML。运行服务和 Web 保存共同使用包变量目录中的 `config.yaml`，但重新安装时仍可能重写已有 `/vol1/...` 路径，且错误被 `|| true` 吞掉。

用户希望在 fnOS 安装阶段选择来源、片库和回收目录，Web 配置复用这些选择，而不是再次询问。安装授权是外部事实，应用仍需在正式运行前实测目录存在、权限和位置能力。

## Decision

1. `${TRIM_PKGVAR}/config/config.yaml` 继续作为运行配置唯一事实源。
2. 安装向导值只在“首次初始化事务”写入；配置记录 schema version、initialized 和 origin。
3. 升级、修复安装和保留数据重装只执行 schema 迁移，绝不重写用户目录和业务开关。fnOS 托管字段 `server.port` 与 `server.api_key` 例外：安装和升级都幂等迁移为固定端口 `14591` 与空服务认证，避免 manifest、桌面入口和实际进程形成双源。
4. 安装回调失败必须终止并给出原因，不再对关键创建、复制和配置迁移使用无条件成功。
5. Web 展示安装值及其校验结论；目录失效时允许用户更换，但保存前必须全量预检。
6. 端口只保留一个生效事实源；向导值进入同一配置事务，不再形成环境变量与 YAML 的长期双源。
7. fnOS 是否支持目录选择器与授权联动必须在真实设备验证；若不支持，安装阶段只做授权提示，首次 Web 启动补录目录，但仍遵守同一配置归属。
8. fnOS 原生桌面应用不要求用户创建服务 API Key，安装与普通配置界面均不暴露该字段；fnOS 包运行配置固定为空服务认证。TMDB、LLM 等业务凭据仍按敏感配置规则保存和脱敏。
9. 后端继续保留显式 YAML 服务认证能力，供非 fnOS 或高级部署使用；它不改变 fnOS 托管包的固定端口和桌面 CGI 契约。
10. fnOS 包固定空服务认证时，后端只监听 `127.0.0.1:14591`；桌面和移动端通过同源 CGI 访问。非 fnOS CLI 仍可显式选择其他监听地址，但不属于托管包默认合同。

## Consequences

- 首次配置减少重复输入，升级和重装行为可预测。
- 安装脚本需要区分 initialize、migrate、repair，并增加回滚和 smoke 测试。
- fnOS 用户无需维护服务 Key；旧包升级会清除遗留服务 Key，避免桌面页面因 401 无法初始化。
- NAS 局域网不能直接访问空认证后端端口，fnOS 桌面入口仍由 CGI 代理到回环地址。
- 不能仅凭安装向导声称目录可用；应用预检仍是运行门禁。

## Alternatives

- 安装和 Web 各维护一套配置：会漂移且无法确定生效值，否决。
- 每次安装都以向导值覆盖：破坏升级和修复安装，否决。
- 完全不在安装收集目录：首次体验更复杂，仅作为 fnOS 平台能力不足时的降级方案。
- CGI 运行时读取旧 YAML 端口：fnOS 不保证向 CGI 注入包数据目录变量，且会延续端口双源，否决。

## Links

- [提案](../proposals/2026-08-28-storage-safe-configuration-redesign.md)
- [计划](../plans/2026-08-28-storage-safe-configuration-redesign-plan.md)
- [ADR-0003](0003-deploy-package-generation-strategy.md)
- [ADR-0017](0017-fnos-first-run-directory-authorization.md)（落实本决策第 7 条：目录改由首次 Web 启动授权选择）
