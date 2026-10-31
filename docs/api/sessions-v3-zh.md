# V3 脱敏与还原 API

客户接入请使用[客户契约与 curl 示例](customer-contract-v3-zh.md)和[OpenAPI 规范](openapi-v3.yaml)。
本页补充实现和部署细节。

V3 以服务端生成的 `session_id` 唯一标识一次脱敏及其还原记录。这里的 session
不代表多轮会话；每次 redact 独立编号占位符，不读取历史请求或会话上下文。
V3 是首个对客户提供的接口版本。旧 V1/V2 路由及专属逻辑已删除，不再启动或提供兼容接口。

## 客户需要保存什么

客户只需保存 `session_id`，并在还原时提供待还原文本。`expires_at` 用来告知有效期，
不要求客户在 restore 时回传。每次 HTTP 调用的 `X-Request-ID` 仅供日志关联和故障排查，
不参与 mapping 查找，也不要求客户保存或回传。

所有 V3 接口使用原有 Bearer API key 认证。服务端将记录绑定到认证身份的 tenant：
配置在 `VG_API_IDENTITIES` 中的同 tenant API key 可以访问同一记录；未配置身份的 key
以自身摘要为 tenant，彼此隔离。标识本身不授予访问权限。当前没有额外的用户或 group
级还原权限模型，也没有独立的 403 业务分支。身份配置只需要 `{tenant_id}`。

## POST `/v3/redaction`

请求必须是 JSON，包含 `purpose`、`email`，可选 `policy`。`email` 保留 V1 邮件结构，
支持 subject、from、to、cc、body、thread；`policy` 沿用原有约束，高风险类型不能放宽。

```json
{
  "purpose": "Draft a reply",
  "email": {"body": "Call 202-555-0102."}
}
```

不接受 `session_id`、`request_id`、`mapping`、`tokenization`、`group_id`、
`source_context` 或 `purpose_source`。未知字段返回 422，不静默忽略。
mapping 始终保留，TTL 由服务端的 `default_ttl_seconds` 决定，上限为 `max_ttl_seconds`。

成功返回 200：

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "redacted_email": {"body": "Call [PHONE_1].", "to": [], "cc": [], "thread": []},
  "redacted_purpose": "Draft a reply",
  "expires_at": "2026-10-28T16:00:00+00:00",
  "degraded": false
}
```

`session_id` 使用独立组件生成 `sid_<ULID>`，不对原文计算 hash。存储原子预留标识，
冲突时重试，最多 8 次；不会覆盖原记录。相同文本的两次调用各自生成新记录，当前
V3 不提供幂等缓存。即使没有产生占位符，也会保存有效的空 mapping 并返回标识。

`degraded=true` 表示使用原有保守降级脱敏路径，结果同样支持还原。
成功响应固定为以上五个顶层字段；不返回 spans、模型/策略/prompt 版本、mapping、
内部后端类型、降级细节、record 容器或 request_id，也不重复发送 `X-Degraded`。
具体版本、检测结果及降级诊断仍保留在原有服务端审计/监控中。

## POST `/v3/restore`

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "text": "Please call [PHONE_1]."
}
```

成功返回 200，正文只有：

```json
{"restored_text": "Please call 202-555-0102."}
```

复用现有占位符精确匹配逻辑：存在未知占位符时，整次还原失败，不返回部分还原文本。
原文 purpose/email 中已有的占位符作为字面量保留，mapping 将其映射到自身；
新占位符跳过这些已有编号（包含大小写变体），避免将原文中的 `[PHONE_1]` 误还原为电话号码。
restore 不消费记录，不延长 TTL，可重复调用。同一文本应只使用对应一次脱敏的占位符，
不能混合多个 session 的结果；短占位符本身不携带来源，服务端不能识别编号相同的混用。

替换前会计算展开后的 UTF-8 文本字节数（包含重复占位符与普通文本）。
`max_restored_bytes` 默认 1,048,576 字节（1 MiB），超限返回 413 `restored-text-too-large`，
不会先分配巨大结果，也不返回部分文本。记录仍可用于较小的还原请求；`/v3/info` 返回此限制。

## DELETE `/v3/redaction`

与 restore 一样，从 JSON 请求正文读取 `session_id`，不在 URL 或请求头中传入：

```json
{"session_id": "sid_01M60000000000000000000000"}
```

提前清除记录的还原载荷，成功返回 204，无响应正文。删除不存在或已删除的标识同样返回
204；其他 tenant 的已有记录或 tombstone 返回 404。
已经通过授权并取得快照的还原可以继续完成；删除之后开始的新还原请求返回 410。

## 错误响应

使用 `application/problem+json`，基本字段为 `type`、`title`、`status`。
参数校验错误增加 `violations`（字段路径和错误码），不会回显输入值。
正文不包含 request_id；排查编号仅放在 `X-Request-ID` 响应头。

| 情况 | HTTP | type 后缀 |
|---|---|---|
| 未认证或 API key 无效 | 401 | unauthorized |
| Content-Type 不支持 | 415 | unsupported-media-type |
| JSON 错误 | 400 | malformed-json |
| 请求过大 | 413 | payload-too-large |
| 展开后的还原文本超出字节上限 | 413 | restored-text-too-large |
| 参数缺失、标识格式错误、非法 Unicode、未知字段或策略非法 | 422 | validation-failed |
| 未知占位符 | 422 | unknown-placeholder |
| 标识不存在或属于其他 tenant | 404 | session-not-found |
| 有权访问的标识已过期或删除 | 410 | session-gone |
| 记录容量不足 | 503 | capacity-exhausted，附 Retry-After |
| 标识冲突重试耗尽 | 503 | session-id-unavailable |
| 记录写入失败 | 503 | session-store-unavailable |
| AES 密钥缺失 | 503 | session-key-unavailable |
| 载荷损坏或后端版本不支持 | 503 | session-payload-unavailable |
| 脱敏或还原处理超时 | 504 | deadline-exceeded |
| 其他内部失败 | 500 | internal |

所有 type 都使用 `urn:vg:problem:` 前缀。tombstone 仅保存失效时间和归属，不保留原文；
保留期为 `max_ttl_seconds`，清理后查询返回 404。对其他 tenant 不暴露 410。
脱敏发生失败时不返回 session_id，并清理已预留或已提交的记录，包括响应序列化失败。
JSON 字符串或键中的孤立代理字符会在预留记录前返回 422 `validation-failed`，
violation code 为 `invalid_unicode`，不会回显输入值。

占位符生成、加密、审计写入和 JSON 响应序列化在线程中执行，deadline 覆盖准备及序列化阶段，
提交记录和返回成功前也会显式检查时间。超时后，后台准备工作可能继续完成，但不能再提交记录。
`session_created` 日志保留 session_id 与 request_id 的关联，输入文本和 mapping 值仍由白名单过滤。

## 内部后端与部署约束

默认配置：

```yaml
v3:
  backend: mapping
```

`mapping` 保存原始占位符到原文的字典，不依赖 token keyring。
客户端不能通过请求改变后端。V3 的恢复载荷适配器与已有检测、判断、占位符生成和
还原组件分离，使用同一编排流程和 RecordStore 实现。

保留可选内部后端 `aes_siv`：使用已有 `VG_SESSION_KEYS` keyring 和
`v3.active_key_id`（可用 `VG_ACTIVE_SESSION_KEY_ID` 覆盖），按 V3 用途派生独立密钥，将整份 mapping 用 AES-SIV 加密后保存。
认证附加数据绑定 tenant、session_id、key ID 和格式版本。AES 模式的可见占位符格式
与原始 mapping 相同，服务端仍需保存加密载荷，不提供无状态还原。
未配置持久化 keyring 时启用 AES 会拒绝启动；密钥不得放入仓库配置。

每条记录保存实际的 backend、backend_version，AES 载荷额外保存 key ID。
restore 按记录选择后端，不按当前部署默认值选择，因此默认值切换不会改变已有记录
的解析方式；轮换密钥时须保留旧 key，直到旧记录全部失效。
是否切换 AES、是否向客户开放后端选择，留待后续确认；首期保持 mapping 默认值。

## 服务信息与健康检查

- `GET /v3/info`：需要认证；返回服务版本、contract_version、策略与模型版本、tiers、实体类型、
  限制、失败行为、restoration 后端/存储/默认 TTL，以及 `supported_contracts: ["v3"]`。
- `GET /healthz`：不需要认证；返回 `{"status":"ok"}`。
- `GET /readyz`：不需要认证；返回 `mode` 和 `components`，报告模型、session_store 和 restoration 状态。

服务版本为 `3.0.0`，API 契约版本为 `v3`。V1/V2 路径不再注册，已认证请求访问旧路径返回 404。

## 部署约束

V3 使用单一内存 RecordStore，最多保存 `max_records` 条记录，监控容量与该配置一致。
必须使用单进程；重启后记录丢失，旧标识返回 404，即使使用 AES 也不会自动持久化。
旧 token keyring、Redis、会话密钥和幂等缓存配置已删除。需要多实例时，应另行增加共享记录存储适配器。
