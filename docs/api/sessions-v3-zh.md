# V3 脱敏与还原 API

V3 以服务端生成的 `session_id` 唯一标识一次脱敏及其还原记录。这里的 session
不代表多轮会话；每次 redact 独立编号占位符，不读取历史请求或会话上下文。
V1、V2 的原有字段和行为保持兼容。

## 客户需要保存什么

客户只需保存 `session_id`，并在还原时提供待还原文本。`expires_at` 用来告知有效期，
不要求客户在 restore 时回传。每次 HTTP 调用的 `X-Request-ID` 仅供日志关联和故障排查，
不参与 mapping 查找，也不要求客户保存或回传。

所有 V3 接口使用原有 Bearer API key 认证。服务端将记录绑定到认证身份的 tenant：
配置在 `VG_API_IDENTITIES` 中的同 tenant API key 可以访问同一记录；未配置身份的 key
以自身摘要为 tenant，彼此隔离。标识本身不授予访问权限。当前没有额外的用户或 group
级还原权限模型，因此 V3 不使用 V2 的 `group_id`，也没有独立的 403 业务分支。

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
成功响应固定为以上六个顶层字段；不返回 spans、模型/策略/prompt 版本、mapping、
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
restore 不消费记录，不延长 TTL，可重复调用。同一文本应只使用对应一次脱敏的占位符，
不能混合多个 session 的结果；短占位符本身不携带来源，服务端不能识别编号相同的混用。

## DELETE `/v3/redaction`

与 restore 一样，从 JSON 请求正文读取 `session_id`，不在 URL 或请求头中传入：

```json
{"session_id": "sid_01M60000000000000000000000"}
```

提前清除记录的还原载荷，成功返回 204，无响应正文。删除不存在或已删除的标识同样返回
204；其他 tenant 的已有记录或 tombstone 返回 404。删除不影响 V1、V2 记录。

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
| 参数缺失、标识格式错误、未知字段或策略非法 | 422 | validation-failed |
| 未知占位符 | 422 | unknown-placeholder |
| 标识不存在或属于其他 tenant | 404 | session-not-found |
| 有权访问的标识已过期或删除 | 410 | session-gone |
| 记录容量不足 | 503 | capacity-exhausted，附 Retry-After |
| 标识冲突重试耗尽 | 503 | session-id-unavailable |
| 记录写入失败 | 503 | session-store-unavailable |
| AES 密钥缺失 | 503 | session-key-unavailable |
| 载荷损坏或后端版本不支持 | 503 | session-payload-unavailable |
| 端到端脱敏超时 | 504 | deadline-exceeded |
| 其他内部失败 | 500 | internal |

所有 type 都使用 `urn:vg:problem:` 前缀。tombstone 仅保存失效时间和归属，不保留原文；
保留期为 `max_ttl_seconds`，清理后查询返回 404。对其他 tenant 不暴露 410。
脱敏发生失败时不返回 session_id，并清理已预留或已提交的记录。

## 内部后端与部署约束

默认配置：

```yaml
v3:
  backend: mapping
```

`mapping` 保存原始占位符到原文的字典，不依赖 token keyring。
客户端不能通过请求改变后端。V3 的恢复载荷适配器与已有检测、判断、占位符生成和
还原组件分离，复用同一编排流程和 RecordStore 实现。

保留可选内部后端 `aes_siv`：使用已有 `VG_TOKEN_KEYS` keyring 和
`tokenization.active_key_id`，按 V3 用途派生独立密钥，将整份 mapping 用 AES-SIV 加密后保存。
认证附加数据绑定 tenant、session_id、key ID 和格式版本。AES 模式的可见占位符格式
与原始 mapping 相同；它不是 V2 的自带加密原文 token，也不是无状态还原。
未配置持久化 keyring 时启用 AES 会拒绝启动；密钥不得放入仓库配置。

每条记录保存实际的 backend、backend_version，AES 载荷额外保存 key ID。
restore 按记录选择后端，不按当前部署默认值选择，因此默认值切换不会改变已有记录
的解析方式；轮换密钥时须保留旧 key，直到旧记录全部失效。
是否切换 AES、是否向客户开放后端选择，留待后续确认；首期保持 mapping 默认值。

目前 V3 复用内存 RecordStore，使用独立实例与 V1 隔离，容量为每套存储各自最多
`max_records` 条记录。监控中的记录数量和容量汇总两套存储。
V3 必须使用单进程，重启后记录丢失，旧标识返回 404；即使启用 AES 或 V2 Redis，
V3 记录也不会自动持久化或共享。需要多实例时，应另行增加共享记录存储适配器。
