# Conversation Key Manager

> 历史设计文档：V1/V2 实现已删除，不代表当前服务接口。当前契约见 [V3 API](sessions-v3-zh.md)。

V2 现在使用 conversation 独立随机密钥材料签发格式 2 的 token。脱敏与恢复的请求结构保持不变。
`group_id` 对应 API key 所属 tenant 下的 conversation，直接复用业务会话 ID。
省略时仍使用 `default`，因此同一 tenant 下省略 ID 的请求会共用同一个会话。

## 密钥与存储

- 首次请求生成随机 256 位会话密钥材料及随机 opaque handle。
- `VG_TOKEN_KEYS` 作为主密钥 KEK keyring，用 64 字节 AES-SIV 密钥封装会话材料和业务 group ID。
  不持久化明文 DEK。
- HKDF-SHA256 按用途派生独立的 token、mapping、引用签名和幂等缓存密钥。
- 共享 Redis 保存封装密钥、group 索引、生命周期及可选 mapping；原子创建保证多实例只使用一个赢家，
  CAS 更新避免续期、重封装和关闭操作互相覆盖。
- 明文会话密钥仅在请求内使用，不做跨请求缓存。Memory 后端只用于开发，多实例须共享 Redis 和配置。
- 两种模式都依赖会话密钥记录。AES-SIV 虽不保存原文 mapping，Redis 故障时也会返回 503，
  不回退为实例本地密钥。需要持久化及备份 Redis。

新 token 不再携带主密钥 ID 和逐请求有效期，而是携带随机会话 handle 与 DEK 版本：

```text
[VG:2:s:PHONE_PERSONAL:<conversation-handle>:1:<ciphertext>]
[VG:2:m:PHONE_PERSONAL:<conversation-handle>:1:<reference>.<signature>]
```

tenant、handle、DEK 版本、后端和实体类型均受认证保护。AAD 固定，因此同一会话中相同原文及类型
在不同请求中产生相同 token；不同会话的密钥材料独立随机。完整 token 仍可自行定位：
恢复只传 `text` 与鉴权，无需另外提交 group ID 或 redaction ID。
Mapping 后台仍使用 AES-SIV；AES-GCM 后台加密和短占位符是独立的后续工作。
本次不提供别名学习或活跃会话内自动 DEK 轮换。

## 生命周期

`tokenization.ttl_seconds` 延长会话的空闲到期时间，短 TTL 请求不会缩短已有期限。
会话初次创建时确定最大寿命，后续活动不能突破：

```yaml
tokenization:
  conversation_max_lifetime_seconds: 86400
  conversation_tombstone_seconds: 86400
```

新 group 在检测和评估完成、开始生成 token 时才创建会话，模型处理不会消耗首次空闲 TTL。
已有活跃会话在处理前续期，同时延长已有映射的保留时间；已关闭或过期的会话仍在处理前拒绝。
映射发布会在返回前核对并发续期，确保映射不会按旧期限提前过期。

响应中的 `expires_at` 是会话期限快照，后续可能延长，不是每个 token 的固定期限。
AES-SIV 请求也会延长已有 Mapping 数据的保留时间，支持混合模式会话。
各实例需要同步系统时钟；续期不会重置最大寿命起点。

会话过期或关闭后，新脱敏返回 410；恢复返回 HTTP 200 + `BLOCKED`。开启另一个会话需使用新的
业务 group ID，不会静默为旧会话重新生成密钥。首次观察到过期时，CAS 清除封装密钥。
元数据保留至“创建时间 + 最大寿命 + tombstone 时长”，随后由 Redis TTL 清理。
元数据清理后也不要复用旧业务会话 ID。开发内存后端按访问检查过期，不提供后台擦除保证。

## 关闭与删除映射

```http
DELETE /v2/groups/{group_id}           # 关闭会话：鉴权、幂等、204
DELETE /v2/groups/{group_id}/mappings  # 仅删除映射：保留原有语义、204
```

关闭会话会清除封装密钥并删除 Mapping 数据，阻断两种格式 2 token 的恢复和后续脱敏，也阻断
原本可以命中缓存的重试。关闭尚未使用的 ID 会创建 tombstone，避免随后又创建密钥。
若关闭成功后映射清理失败，可以重试；会话不会因此重新开放。
已经返回的明文和关闭前已读取密钥的在途操作无法被撤回。

新幂等响应使用会话派生密钥加密。重放会重新加载密钥并检查返回消息中的 token，
包含其他 conversation 的 token 也会检查。关闭会话使缓存逻辑失效，加密缓存内容仍按 TTL 物理清理。
仅删除 mapping 不影响 AES-SIV 或会话密钥；包含已删除 mapping 的缓存返回 409，不会重放失效 token。

## 主密钥轮换与兼容

先给所有实例分发同时包含新旧 KEK 的 keyring，再统一切换 active KEK。
会话记录在访问时通过 CAS 重封装，密钥材料、DEK 版本、token 和原有期限保持不变。
内部维护方法 `ConversationKeyManager.rewrap(principal, group)` 可重封装已知的活跃 group，且不延长 TTL。
所有相关记录迁移完成、旧格式对象也不再需要旧 KEK 后才能移除它；滚动部署期间保留新旧两把 KEK。

格式 1 的 `[VG:1:...]` 继续按照原主密钥与有效期规则恢复，可与格式 2 混合使用，但无法追溯获得
会话独立密钥。旧 v1 记录接口保持不变。删除组内映射覆盖旧 mapping；关闭会话无法撤销旧的无状态
格式 1 AES-SIV 密文。需要保留旧 KEK 至旧 token 到期，或单独安排旧格式下线。旧幂等缓存仍可读取。

过期与关闭是服务端控制，不等同于擦除备份，或擦除已经同时复制了密文和密钥的数据。
本次不包含单 token 撤销和外部 KMS 接入。

## 验证

在 `service/` 执行 `python -m pytest tests -q`。测试覆盖多实例并发创建、密钥隔离、稳定 token、
空闲及硬期限、关闭与续期竞争、缓存绕过、封装篡改、KEK 轮换、重启恢复、存储失败及旧格式固定向量。
Redis 测试使用支持 Lua 的模拟器，真实部署的持久化/故障切换和真实模型表现仍需单独验证。
现有 HTML 展示页及 notebook 保持不变。
