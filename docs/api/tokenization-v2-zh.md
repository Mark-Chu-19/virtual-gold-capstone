# V2 可逆 token API

> 历史设计文档：V1/V2 实现已删除，不代表当前服务接口。当前契约见 [V3 API](sessions-v3-zh.md)。

V2 在现有检测、评估和决策流程后增加 Mapping / AES-SIV 两个后端。恢复只需要消息和鉴权，
不再需要 redaction ID 或 mode。v1 接口保持兼容，但记录仍在进程内存中，不能任意跨实例路由。

新增 Conversation Key Manager：新 token 使用格式 2、conversation 独立随机密钥，请求结构保持不变。
密钥生命周期与旧格式迁移见 [会话密钥说明](conversation-keys-zh.md)。

## 配置与启动

在 `service/` 安装 `pip install -e '.[dev]'`。通过环境变量提供长期保存的密钥：

- `VG_TOKEN_KEYS`：JSON，例如 `{"k1":"<标准 Base64 编码的 64 字节密钥>"}`。
- `VG_ACTIVE_TOKEN_KEY_ID`：当前生成 token 的密钥 ID，默认 `k1`。
- `VG_API_KEYS`：逗号分隔的有效 API key。
- `VG_TOKEN_STORE`：`memory` 或 `redis`，默认 memory 仅用于开发/测试。
- `VG_REDIS_URL`：私有 Redis >= 7 的连接地址。
- `VG_API_IDENTITIES`：以 API key 的 SHA256 摘要为键，配置 `tenant_id` 和允许的 `groups`。

配置中的 64 字节主密钥（KEK）使用成熟库的 AES-256-SIV 封装会话随机密钥材料，
会话密钥再通过 HKDF 按用途派生；不是 AES-GCM-SIV。
各实例和重启必须使用相同密钥配置；未配置时 v2 返回 503，v1 仍可使用。
不要在每次启动时重新生成密钥，也不要将真实数据、凭据或实验输出提交到仓库。

未配置身份的 API key 各自拥有隔离的 tenant。多个 agent 协作时，将不同 key 显式配置到
同一 tenant 和业务 group。例如：

```json
{
  "<agent-a-key 的 SHA256>": {"tenant_id":"customer-a","groups":["workflow1"]},
  "<agent-b-key 的 SHA256>": {"tenant_id":"customer-a","groups":["workflow1"]}
}
```

只有 `VG_API_KEYS` 中的 key 可以鉴权。`groups: ["*"]` 允许该 tenant 的所有 group。
恢复和删除同样检查权限，token 中的信息不能代替调用者身份。不要把旧 tenant ID 重新分配给其他客户。

共享存储可通过 `docker compose -f infra/compose.yaml up -d` 启动开发用 Redis。
配置文件启用 AOF、持久卷及 noeviction，端口只绑定本机。生产环境需配置私有网络、认证/TLS、
容量和备份；故障切换的持久性取决于 Redis 部署配置，本 API 不提供同步复制承诺。
实例须共享 Redis、密钥、身份和策略；可用 `VG_HOST`、`VG_PORT`、`VG_METRICS_PORT` 设置监听地址。

## 脱敏与恢复

```http
POST /v2/redactions
Authorization: Bearer <agent-key>
Idempotency-Key: workflow1-message1
Content-Type: application/json

{
  "purpose":"Draft a reply",
  "email":{"body":"Call 202-555-0102"},
  "group_id":"workflow1",
  "tokenization":{"mode":"aes_siv","ttl_seconds":3600},
  "include":["service_info"]
}
```

- `mode` 支持 `mapping | aes_siv`；省略时使用配置中的默认值，初始为 Mapping，不会自动降级切换。
- `group_id` 复用业务 conversation/workflow/task ID，允许 1–64 位字母、数字、下划线或连字符。
  默认 `default`，受 tenant 隔离；集成层传递业务 ID，用户不必维护脱敏记录列表。
- TTL 为 1 至 `max_ttl_seconds`，省略时使用默认 TTL（受上限约束）。
- `policy` 与邮件结构沿用 v1；不再接受 v1 的 `mapping`、`session_id`、`source_context` 字段。
  为容纳长 token，受保护地址可扩展至 4,096 字符，purpose 可扩展至 32,768 字符；
  普通地址仍限 320 字符，purpose 的非 token 文本仍限 2,000 字符。
- `include: ["service_info"]` 按需内联 `/v1/info`，独立 info 接口继续保留。
- 响应保留脱敏邮件、purpose、spans、版本和降级信息，另含 `tokenization` 元数据。
  `expires_at` 是会话到期时间快照，使用 Unix 秒；后续活动可在最大寿命内延长。`request_id` 只用于追踪，不用于恢复。
  v2 不创建 v1 record，也不受 v1 的 `max_records` 容量预留限制。

```http
POST /v2/restorations
Authorization: Bearer <agent-key>
Content-Type: application/json

{"text":"Call [VG:2:...]"}
```

服务自动识别后端，支持跨请求、跨 agent、跨实例及两种 token 混合恢复。
成功返回 `RESTORED` 和 `restored_text`；未知、畸形、篡改、过期、已删除或无权限的 token
统一返回 `BLOCKED / invalid_or_unavailable_token`，不返回部分原文。存储故障返回 503。
无 token 的文本原样返回；旧 `[PHONE_1]` 在 v2 中被阻断，需要使用旧 v1 记录恢复入口。
恢复不消费 token；解密只进行一轮，原文中类似 token 的内容不会被递归解释。

再次脱敏包含 token 的消息时，先验证并授权已有 token，以等长空白屏蔽后再送入检测器和模型。
只脱敏新增敏感内容；已有 token 不可用或检测结果跨越已有 token 时返回 422。
spans 仍按原输入的 Unicode 码点定位。`[VG...]` 为保留命名空间。

## 两种后端与 token

```text
[VG:2:m:PHONE_PERSONAL:<conversation-handle>:1:<reference>.<signature>]
[VG:2:s:PHONE_PERSONAL:<conversation-handle>:1:<ciphertext>]
```

格式、后端、类型、会话 handle、DEK 版本及可信 tenant 受认证保护。handle 随机生成，不是原始业务 ID。
主密钥 ID 和有效期保存于会话记录，不再放进新 token。模型只看到类型、opaque token 与上下文。
固定上下文内的重复关系仍可见，AES-SIV 还会暴露明文字节长度；这是可逆假名化，不是匿名化。

Mapping 在共享 Redis 中保存加密后的原文映射。相同 tenant/group/type/key 下，精确原文的
reference 稳定。每次请求的映射以 group 为单位原子写入，成功后才返回 token；短 TTL 请求不会
缩短旧映射的保留时间。存储内容可能保留至 group 最长 TTL；AES-SIV 请求也会延长已有映射的保留时间。恢复时统一检查会话状态和有效期。

AES-SIV 不保存原文 mapping，使用会话派生密钥加密精确的 UTF-8 文本。AAD 固定绑定格式、后端、
类型、tenant、会话和 DEK 版本，不包含逐请求有效期，因此同一会话中相同原文及类型的 token
在后续请求中保持一致。两种模式均不统一大小写、不展开姓名；加密不提供别名学习或实体解析。
完整 token 长度仍需测量，不能把纯加密载荷长度当作完整输出长度。

## 幂等、删除与轮换

可选 `Idempotency-Key` 支持 1–128 位字母、数字、连字符、下划线。同 tenant、同 key、同输入
重试返回相同 token、有效期和结果，追踪 request ID 更新，并带 `Idempotency-Replayed: true`。
不同输入返回 409；处理中重复请求返回 409 和 `Retry-After: 1`。失败请求释放有界租约。
跨实例幂等需要 Redis，缓存响应也使用会话派生密钥加密。AES-SIV 虽然不保存原文 mapping，
但新格式同样依赖共享会话密钥记录，Redis 故障时不能继续生成或恢复。
租约用于重试协调，不能保证任意长进程暂停场景下的 exactly-once。

`DELETE /v2/groups/{group_id}/mappings` 检查权限，幂等返回 204，删除所有已配置 key ID 下该
业务 group 的 Mapping 内容，**不撤销 AES-SIV token**。删除后并发的新脱敏可以重新建立映射；
停用会话请使用下面的会话关闭接口。缓存重放会重新检查 token，不可用时返回 409；新的业务操作应使用新幂等键。

两种后端目前均没有单 token 撤销接口。AES-SIV 要支持逐条即时撤销，需要额外状态。
有效期由服务执行，不能替代密钥销毁；持有旧密钥的人仍可能离线解密留存密文。
主密钥轮换时保留旧 KEK 并增加新 active key，会话记录在访问时重封装，token 不变。
所有相关记录重封装完毕前不能移除旧 KEK；旧格式 token 和缓存仍可能依赖旧 key。
切换默认模式不会改变历史 token。Mapping 故障时不返回成功的脱敏结果；新 AES-SIV 模式也依赖会话密钥存储。崩溃可能留下等待 TTL 清理的加密映射，不会提前返回尚未提交的 token。

审计增加后端类型，不记录原文、token、mapping 或密钥。
新增指标为 `vg_token_redactions_total{backend,mode}`、`vg_token_restorations_total{decision}`。
`/readyz` 报告 Mapping 存储故障和未配置的 tokenization 状态。

新增 `DELETE /v2/groups/{group_id}` 关闭会话：清除封装密钥、删除映射，使新格式的两种 token
均不可恢复；后续脱敏与缓存重试返回 410。旧格式的迁移边界参阅会话密钥说明。

## 验证与模型实验

```bash
python -m pytest tests -q
VG_EVAL_API_KEY='<agent-key>' python scripts/evaluate_tokens.py \
  --model llama3:8b --hops 3 --output /tmp/token-evaluation.jsonl
```

脚本使用内置合成消息及本地 Ollama，对两种模式运行相同复制/回复任务和多次转交。
记录 token 保留、缺失、新增、精确复制、恢复结果、模型 token 数和延迟。
任务质量和实体引用正确性仍需人工评估：成功解密不能证明模型保留了所有实体。
该脚本提供可复现实验入口，不代表 AES-SIV 的真实模型效果已验证。现有 notebook 独立保留。

完整英文契约及更多部署说明见 [tokenization-v2-en.md](tokenization-v2-en.md)。
