# Virtual Gold API contract — 客户接入说明

**API：** V3 · **服务版本：** 3.0.0 · **核对日期：** 2026-10-29

**实现基线：** `main`，提交 `1e805ab3714643a03029216469683f5751ceb3d8`

[English](customer-contract-v3-en.md) · [OpenAPI 3.1 契约](openapi-v3.yaml)

本文说明当前已实现的客户调用方式：提交邮件脱敏，将脱敏文本交给下游完成任务，再将结果中的
受支持占位符还原。OpenAPI 文件可导入支持该格式的 API 工具。所有示例均为虚构数据。

## 1. 地址、鉴权与数据归属

向服务提供方获取接入 **base URL** 和 **API key**。仓库没有定义已上线的客户地址或可用性 SLA。
本地开发地址为 `http://127.0.0.1:8080`；非本机接入请使用提供方确认的 HTTPS 地址。

所有 `/v3/` 接口均需携带：

```http
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

有 JSON 请求正文的调用必须设置 `Content-Type`，DELETE 也不例外。成功正文为
`application/json`；应用错误为 `application/problem+json`。`X-Request-ID` 响应头用于每次调用的
故障排查，不是 session 标识。服务不返回 `X-Degraded`，应读取响应正文的 `degraded`。

API key 决定 tenant。还原和删除必须使用归属于创建记录的 tenant 的 key。只有服务提供方将
两个 key 配置为同一 tenant 时，才可跨 key 使用同一记录。客户端不能在请求中选择 tenant、group
或用户权限。仅知道 `session_id` 不代表拥有访问权限。

## 2. 如何完成一次任务

1. 调用 **POST `/v3/redaction`**，提交任务目的和原始邮件。
2. 将返回的 `session_id` 与这一次的脱敏结果关联保存；可同时保存 `expires_at` 管理期限。
   下游应使用 `redacted_purpose` 和所需的 `redacted_email` 字段，不再转发原始任务目的。
   要求下游原样保留占位符，包括大小写。
3. 到期前调用 **POST `/v3/restore`**，提交下游返回的文本和同一个 `session_id`。
   只有 HTTP 200 时才读取 `restored_text`。
4. 不再需要还原时，调用 **DELETE `/v3/redaction`** 清理记录。

一个 `session_id` 标识**一次独立脱敏**，不是多轮对话。客户端必须维护“脱敏结果—session”对应关系。
不同记录中相同的 `[PHONE_1]` 可以代表不同值；混合多个 session 的占位符时，服务无法识别同名占位符
来自哪个原始记录，可能还原为错误内容。

| 方法 | 路径 | 鉴权 | 成功响应 |
|---|---|---|---|
| POST | `/v3/redaction` | Bearer key | 200，脱敏结果与 session |
| POST | `/v3/restore` | Bearer key | 200，还原文本 |
| DELETE | `/v3/redaction` | Bearer key | 204，无正文 |
| GET | `/v3/info` | Bearer key | 200，服务配置与限制 |
| GET | `/healthz` | 公开 | 200，存活状态 |
| GET | `/readyz` | 公开 | 200，正文中的就绪状态 |

## 3. 邮件脱敏

### 请求：POST `/v3/redaction`

```json
{
  "purpose": "Draft a reply",
  "email": {"body": "Call 202-555-0102."}
}
```

| 字段 | 必填 | 类型及约束 |
|---|---|---|
| `purpose` | 是 | 字符串，1–2,000 个 Unicode 字符，说明任务目的 |
| `email` | 是 | 邮件对象 |
| `policy` | 否 | 对象；默认没有请求级覆盖 |
| `email.body` | 是 | 字符串，可为空；受整个请求的字节限制 |
| `email.subject` | 否 | 字符串或 null |
| `email.from` | 否 | 地址对象或 null |
| `email.to`、`email.cc` | 否 | 地址对象数组，默认 `[]` |
| `email.thread` | 否 | 引用邮件数组，最多 50 项，默认 `[]` |

**地址对象：** 必填 `address`，字符串，长度 1–320；可选 `name`，字符串或 null。
`address` 按文本处理，服务不校验其是否符合 RFC 邮箱地址语法。JSON 字段名使用 `from`。

**引用邮件对象：** 必填 `text` 字符串；可选 `message_id` 字符串或 null；可选 `source`，
唯一允许值为 `"quoted_thread"`，默认也是此值。
服务处理 `purpose`、subject、姓名、地址、body 和 `thread[].text`。
`message_id` 作为元数据原样传递，请勿在其中放入敏感内容。

各请求模型层级的未知字段都会被拒绝。不得提交 `session_id`、`request_id`、`mapping`、
`tokenization`、`group_id`、`source_context`、`purpose_source`、后端选择或客户端 TTL。
没有附件、二进制上传或 OCR 字段。虽然可提交 Unicode 文本，检测能力仍取决于部署组件和双方约定的
输入语言；接受 Unicode 不等于承诺多语言检测效果。

### 可选策略覆盖

常规客户接入可省略 `policy`，沿用部署策略。高级用法可在完整请求中加入以下片段：

```json
{
  "policy": {
    "overrides": {
      "thresholds": {"medium": 0.5},
      "entity_types": {"exclude": []},
      "allow_list": [],
      "deny_list": []
    }
  }
}
```

只有 `medium` 阈值可覆盖，范围为 0–1。`entity_types` 中只允许 `exclude`，且不能排除 high-tier 类型。
allow list 命中 high-tier 候选时返回 422。列表填写精确匹配文本，请使用非空词条；默认降级流程通常
不应用 allow list。通过 `/v3/info` 查询当前实体类型及其 tier。
覆盖策略可能改变明文保留范围，放宽前请与服务提供方确认。

### 成功响应：HTTP 200

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "redacted_email": {
    "body": "Call [PHONE_1].",
    "to": [],
    "cc": [],
    "thread": []
  },
  "redacted_purpose": "Draft a reply",
  "expires_at": "2026-10-29T17:00:00+00:00",
  "degraded": false
}
```

这是示意输出，不代表任意部署的检测结果必然相同。响应恰有**五个**顶层字段：

| 字段 | 含义 |
|---|---|
| `session_id` | 服务端生成的 `sid_<ULID>`，与本次结果关联保存 |
| `redacted_email` | 文本已处理的邮件结构；null 可选字段省略，默认数组会返回 |
| `redacted_purpose` | 已处理的任务目的，下游应使用此值 |
| `expires_at` | UTC 的 ISO 8601 / RFC 3339 日期时间，还原时无需回传 |
| `degraded` | 是否使用了保守降级流程 |

`degraded: true` 仍表示成功且可还原，降级流程对仍可用的检测器提供的候选执行脱敏。
它不保证识别了全部敏感信息，客户端应执行双方约定的复核／放行策略。`degraded: false` 同样
不是允许发送到云端的授权；此 API 不返回整请求的放行或路由决策。

每次成功调用都生成新 session，即使输入相同或没有检测出需要替换的内容。V3 没有实现
`Idempotency-Key` 语义，不能依靠该请求头去重。记录必须保留，保留期限由服务端决定。

## 4. 还原下游结果

### 请求：POST `/v3/restore`

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "text": "Please call [PHONE_1]."
}
```

两个字段均为必填字符串。`session_id` 格式为 `^sid_[0-7][0-9A-HJKMNP-TV-Z]{25}$`，
请直接使用收到的值。`text` 可以为空或不含占位符，但记录仍须有效且属于当前 tenant。

HTTP 200：

```json
{"restored_text": "Please call 202-555-0102."}
```

对 `[PHONE_1]` 等可识别占位符进行精确、区分大小写的匹配。出现未知的可识别占位符时，
返回 422 `unknown-placeholder`，不返回部分还原文本。不符合占位符语法的文本会按普通文字处理，
因此拼写损坏或完全遗漏的占位符不一定能被识别；服务不会猜测、修复或补回下游遗漏的实体。
替换只执行一轮，不递归展开。

还原的是该 session 保存的映射值。同一次脱敏中，邮件头姓名的明确别名可能合用占位符并还原为全名；
归一化后的其他变体也可能共用映射。因此不承诺逐字节重建原文的每一种写法。
原文中已有的字面量占位符会被保留，新生成编号会避开其保留编号。
请勿改变占位符拼写，或使用另一条 session 还原。

还原可以重复执行，不消费记录，不续期；无需回传原始邮件、`expires_at`、内部后端类型或 `X-Request-ID`。

## 5. 删除还原记录

### 请求：DELETE `/v3/redaction`

```json
{"session_id": "sid_01M60000000000000000000000"}
```

必须发送 JSON 正文和 `Content-Type: application/json`。成功为 **204 No Content**，不要继续解析 JSON。
session 引用位于正文，不在 URL 中。请确认 HTTP 库、网关和代理会转发 DELETE 正文；下方 curl 示例
显式发送所需的 JSON 正文。

删除幂等：不存在、已过期或已删除的 ID 也返回 204。属于其他 tenant 的已知记录或 tombstone 返回 404。
删除后新发起的还原失败；已授权并取得快照的在途还原仍可能完成。删除无法撤回已经返回给客户的明文。

## 6. 限制与有效期

通过需要鉴权的 **GET `/v3/info`** 查询当前部署值。仓库默认配置如下：

| 配置／响应字段 | 默认值 | 客户影响 |
|---|---|---|
| `limits.max_request_bytes` | 262,144 字节（256 KiB） | 整个编码后的 JSON 正文，不只是文本；适用于所有有正文的调用 |
| `limits.max_restored_bytes` | 1,048,576 字节（1 MiB） | 展开后的 UTF-8 文本，包含重复占位符与普通文字 |
| `limits.timeout_ms` | 15,000 毫秒 | 脱敏／还原处理预算，不是网络延迟 SLA |
| `restoration.default_ttl_seconds` | 3,600 秒 | 处理后记录提交时开始计时，固定有效期；还原不续期 |
| `limits.max_ttl_seconds` | 86,400 秒 | 服务端 TTL 上限，客户端不能选择 |
| `limits.max_records` | 1,000 | 已存 session 与处理中预留记录共用的容量 |

新脱敏创建另一条记录，不延长旧记录寿命。还原已过期／已删除且有权访问的 session 通常返回 410；
失效元数据清理后变为 404。未知 ID 和其他 tenant 的 ID 也返回 404。

**当前部署边界：** session 存储在单进程内存中，不具备持久化。服务重启后全部记录失效，
即使内部选择 AES 后端也一样。当前要求一个 worker，不支持将请求任意路由到独立副本。
如需重启恢复或多副本，请先与提供方确认部署变更。内部后端由服务端选择，客户端请求不能切换。

`/v3/info` 还返回服务、contract、模型／策略等版本，`tiers`、`entity_types`、`failure_behavior`、
还原配置及 `supported_contracts: ["v3"]`。
`GET /healthz` 返回 `{"status":"ok"}`。`GET /readyz` 返回 `mode` 和组件状态；
`ready` 与 `degraded` 正常均为 HTTP 200，应检查正文。

## 7. 错误与重试

应用错误采用 [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)。
客户端应根据 HTTP 状态和 `type` 分支处理，不依赖英文 `title`。例如：

```json
{
  "type": "urn:vg:problem:validation-failed",
  "title": "Request failed validation",
  "status": 422,
  "violations": [{"field": "purpose", "code": "missing"}]
}
```

必含 `type`、`title`、`status`；可选 `detail`、`violations`（`field` 和 `code`）。
错误正文不返回 session 或 request ID；排查编号在 `X-Request-ID` 响应头中。
以下 type 均带 `urn:vg:problem:` 前缀。

| HTTP | type 后缀 | 建议处理 |
|---|---|---|
| 400 | `malformed-json` | 修复 JSON／正文，不原样重试 |
| 401 | `unauthorized` | 获取或修正 Bearer key |
| 404 | `session-not-found` | 核对结果对应关系及 tenant；重启也可能导致记录消失 |
| 410 | `session-gone` | 数据已失效，重试相同 ID 无法恢复 |
| 413 | `payload-too-large` | 减少编码后请求大小 |
| 413 | `restored-text-too-large` | 减少展开后文本，包括重复占位符；较小请求仍可使用原 session |
| 415 | `unsupported-media-type` | 设置 `Content-Type: application/json` |
| 422 | `validation-failed` | 按 `violations` 修正字段、策略或 Unicode；未知字段代码为 `extra_forbidden` |
| 422 | `unknown-placeholder` | 核对占位符和匹配 session，不使用部分还原结果 |
| 503 | `capacity-exhausted` | 等待 `Retry-After`，当前为 5 秒；释放不再需要的记录 |
| 503 | `session-id-unavailable`、`session-store-unavailable` | 有上限地退避重试；持续失败时联系提供方 |
| 503 | `session-key-unavailable`、`session-payload-unavailable` | 联系提供方恢复密钥／载荷；更换 ID 无法修复 |
| 504 | `deadline-exceeded` | 谨慎重试；持续失败时提供排查编号 |
| 500 | `internal` | 谨慎重试；联系提供方并提供排查编号 |

JSON 字符串或键包含孤立 Unicode 代理字符时返回 422，violation code 为 `invalid_unicode`。
应用错误不回显输入值，但会包含字段路径。不存在的路径或不支持的方法可能返回框架／网关错误格式，
客户端也应能处理非 JSON 的代理或传输错误。

重复还原和删除不会消费额外的 session。重复 POST `/v3/redaction` 会创建新记录；若服务已成功而连接
中断，客户端可能拿不到 session ID，该记录仍可能保留至到期。暂时性错误使用有上限的退避重试。
没有幂等或 session 查询接口可消除这类不确定结果。客户端超时应为服务处理预算加上网络开销。
API 没有约定内置限流或 429 行为。

## 8. 接入示例

以下 curl 调用使用虚构数据执行“脱敏 → 还原 → 删除”，不调用云模型。继续下一步前请检查脱敏结果：
若 `degraded` 为 true，执行约定的复核策略。复制实际返回的 session ID 并原样保留占位符拼写；
下方还原请求假设实际结果包含示例中的 `[PHONE_1]`。

```bash
export VG_BASE_URL='http://127.0.0.1:8080'  # 仅本地开发，客户接入时替换
export VG_API_KEY='<operator-issued-key>'

curl --fail-with-body --silent --show-error "$VG_BASE_URL/v3/redaction" \
  -H "Authorization: Bearer $VG_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"purpose":"Draft a reply","email":{"body":"Call 202-555-0102."}}'

# 检查响应后，将返回的 session_id 填在这里。
export VG_SESSION_ID='<session_id returned by redaction>'

curl --fail-with-body --silent --show-error "$VG_BASE_URL/v3/restore" \
  -H "Authorization: Bearer $VG_API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"session_id\":\"$VG_SESSION_ID\",\"text\":\"Please call [PHONE_1].\"}"

# 不再需要还原时执行；成功为 204，无正文。
curl --fail-with-body --silent --show-error -X DELETE "$VG_BASE_URL/v3/redaction" \
  -H "Authorization: Bearer $VG_API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"session_id\":\"$VG_SESSION_ID\"}"
```

`VG_BASE_URL` 为服务根地址，不要自行加 `/v3`。不要将 key 写入源码或公开日志。
服务提供方还需单独确认目标环境的检测配置、语言覆盖及放行策略；当前仓库仍含 stub 模型 prompts／parsers，
接口测试通过不等于已经验证检测质量。

## 9. 版本与兼容性

目前只注册 V3。V1/V2 的 token、conversation key、Redis 和幂等文档均为已退役的开发版本，
客户接入不要使用。本文描述已核对的实现，不代表承诺尚未实现的接口、共享存储、用户级授权或自动云路由。
升级客户端前，应与提供方确认不兼容变更和部署限制。

机器可读契约采用 [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)。
导入 API 工具请使用本目录的 `openapi-v3.yaml`：当前框架自动生成的 `/openapi.json` 缺少手动解析的
请求正文、Bearer 鉴权和应用错误定义。此次文档整理不会修改该运行时接口。
