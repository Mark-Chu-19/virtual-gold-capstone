# Service Engineering 实现方案与组件接口(契约 0.4.2 草案)

**状态:** 草案,待团队确认 · **Owner:** Zhexuan Ye · **基于:** API 契约 0.4.1、midterm slides、架构图 v1、development-schedule

## 背景

依据:期中 slides(原则:本地优先 / model proposes, code decides / fail safe;18 步流程;Gateway + 串联 + 记录生命周期 + 指标 + Prometheus/Grafana 是我的交付)、`redaction-api-report-en-v0.4.1.md`(API 契约)、`development-schedule.md`(W9–W13 计划)、两张架构图(组件图 + 18 步时序图)。

目标:把"我负责的部分"落成可直接开写的方案,并把**队友组件必须暴露的函数签名**固定下来,这样 W9 起我用桩代码就能开发,10/30 队友组件到位后直接替换。批准后的产出物是一份 `service-interfaces-v0.4.2.md`(放进 `service engineering/` 文件夹)+ 契约 0.4.2 的修订点,代码骨架在 W9 开写。

假设(可推翻):Python 3.11 + FastAPI + pydantic v2 + uvicorn;`httpx` 调 Ollama;`prometheus_client`;`structlog`。进程内存存记录(契约已定:重启即丢,restore 返回 404)。

---

## 1. 对 0.4.1 契约的发现(需在 0.4.2 里定下来)

| # | 问题 | 建议 |
|---|---|---|
| 1 | 时序图写的是 `POST /redact`,契约是 `POST /v1/redactions` | **已定**:以 `POST /v1/redactions` 为准,时序图第 1 步同步改写 |
| 2 | `spans[].field` 只举了 `email.body` | 定义字段路径语法(§3.3);offset 一律相对**原始字段文本** |
| 3 | `policy.overrides` 内容在契约里是占位 | 采用 §3.2 的结构 |
| 4 | Presidio 抛异常、规则引擎抛异常在契约里没有对应行为 | Presidio 失败 → 降级 200,`degraded_reason: recognizer_failure`;规则引擎失败 → 500(没有安全兜底)。**已定** |
| 5 | `/restore` 410 含"一次性消费":调用方网络重试会拿到 410,拿不到回复 | **已定**:restore **不消费**记录,是只读、幂等、可安全重试的操作;记录由 TTL 或 `DELETE` 结束,调用方用完应主动 `DELETE`。契约里 410 只剩"已过期/已删除",去掉"已消费";暴露窗口由 TTL(默认 3600s,上限 `max_ttl_seconds`)限定 |
| 6 | 降级时 allow-list 是否生效(OQ13) | **已定**:默认**不生效**(更安全),配置项 `allow_list_in_degraded=false` |
| 7 | 409(幂等)、429(限流)属 P1 | 0.4.2 标"暂不实现";`/metrics` 加入契约(仅本机端口) |
| 8 | DELETE 的 404/204 矛盾 | **已定**:`DELETE` 幂等,无论记录存在、已过期、已删除还是从未存在,一律 `204`(符合 RFC 9110 对 DELETE 幂等的惯例,也不向调用方泄露 id 是否存在);`DELETE` 的 404 去掉 |
| 9 | `request_id` 与记录 id | 同一个 id:收到请求即生成(`req_<ULID>`),错误响应和 200 都带它,200 时它就是 restore/DELETE 的 id |

---

## 2. 代码结构

```
vg_redactor/
  api/            # 我:FastAPI app、路由、鉴权、校验、problem+json、中间件
  pipeline/       # 我:orchestrator.py、deadline.py、degrade.py
  model/          # 我:client.py(Ollama/Groq 适配,只管调用+失败分类)
  records/        # 我:store.py(TTL/容量/session 标签状态)
  obs/            # 我:metrics.py、logging.py、audit.py
  contracts/      # 共享:types.py(pydantic 模型)、errors.py、protocols.py(下面 §4)
  components/     # 队友:segmentation.py rules.py presidio_det.py prompts.py
                  #       calibration.py decision.py pseudonym.py context_store.py
  stubs/          # 我:每个 Protocol 的桩实现(W7/W9 交给队友对着开发)
config/           # policy.yaml(tier 表+taxonomy+阈值+policy_version)、service.yaml、context/
dashboards/       # Grafana provisioning JSON、prometheus.yml
tests/contract|failure_injection|leak|load
```

核心规则:**所有组件只依赖 `contracts/`,不 import 彼此**;orchestrator 是唯一把它们串起来的地方。

---

## 3. 对外 HTTP API(0.4.2 具体格式)

通用:`Authorization: Bearer <key>`(`/healthz`、`/readyz` 免;`/metrics` 不在主端口)。key 从 env/文件加载,存 SHA-256,`hmac.compare_digest` 比对。所有错误 `application/problem+json`:

```json
{
  "type": "urn:vg:problem:capacity-exhausted",
  "title": "Request-record capacity exhausted",
  "status": 503,
  "request_id": "req_01J...",
  "detail": "no private text here, ever",
  "violations": [{"field": "policy.overrides.thresholds.high", "code": "high_tier_fixed"}]
}
```

`type` 枚举:`malformed-json`(400)、`unauthorized`(401)、`not-found`(404)、`gone`(410)、`payload-too-large`(413)、`unsupported-media-type`(415)、`validation-failed`(422,带 `violations`)、`internal`(500)、`capacity-exhausted`(503,带 `Retry-After`)、`deadline-exceeded`(504)。`detail`/`violations` 只含字段路径和错误码,**不回显输入值**。

### 3.1 `POST /v1/redactions`
请求/响应字段与 0.4.1 §3 相同(不重复),补充:

- 头:`Content-Type: application/json`(否则 415);可选 `X-Request-ID` 忽略(服务自己发号)。
- 校验:`purpose` 必填 1–2,000 字符;`email.body` 必填;`email.thread` ≤ 50 条;`session_id` 匹配 `^[A-Za-z0-9_-]{1,64}$` 且要求 `mapping.retain=true`(否则 422 `session_requires_retain`);`mapping.ttl_seconds` 1–`max_ttl_seconds`(默认 86,400);未知字段 → 422(`extra=forbid`,防止拼错 `retain` 静默失效);`max_request_bytes` 默认 262,144(临时,OQ6),先看 Content-Length 再流式计数。
- 响应新增(0.4.2):`degraded_reason` 增加 `recognizer_failure`;`record: {"expires_at": "ISO-8601", "mapping_retained": bool}`;响应头 `X-Request-ID`、`X-Degraded: true|false`。

### 3.2 `policy.overrides` 结构(提案)
```json
"policy": {"overrides": {
  "thresholds": {"medium": 0.6},
  "entity_types": {"exclude": ["ORG_NAME"]},
  "allow_list": ["support@example.test"],
  "deny_list": ["Project Falcon"]
}}
```
`thresholds` 的 key 只能是 `medium`;`low`/`public` 规则不是单一阈值,不开放(待 Yudi 确认);触及 High 类型(含在 `exclude`、`allow_list` 命中 High 类候选)→ 422 `high_tier_fixed`。`deny_list` 命中按 High 候选处理。

### 3.3 字段路径语法(`spans[].field`)
`purpose` · `email.subject` · `email.from.name` · `email.from.address` · `email.to[0].name` · `email.to[0].address` · `email.cc[i].*` · `email.body` · `email.thread[0].text`。`start/end` 是该字段**原文**的字符偏移(Unicode code point,半开区间 `[start,end)`);`redacted_email` 与输入同形。

### 3.4 `POST /v1/redactions/{id}/restore`
请求 `{"reply_text": "..."}`(≤ `max_request_bytes`)。逻辑:

1. 查记录 → 404(从未有过,或进程重启后)/410(已过期或已删除)。服务保留已删除/过期 id 的墓碑(只存 id,不含数据,保留 `max_ttl_seconds`),用来区分 410 与 404。
2. `mapping` 为空 → 200 `BLOCKED` + `mapping_not_retained`。
3. (实现:此步在 `Pseudonymizer.restore` 内完成,网关只负责查记录和 `mapping_not_retained`)用正则 `\[[A-Za-z]+_\d+\]`(大小写不敏感)抓出回复里所有疑似占位符;不在映射表(精确大小写)的全部进 `unmatched_placeholders`,有任意一个 → `BLOCKED` + `unknown_placeholder`(OQ9 当前结论)。
4. 否则 `restored_text` 由 `Pseudonymizer.restore` 生成。**不消费记录**,同一 id 可重复 restore,直到 TTL 或 `DELETE`。

### 3.5 其余端点
- `DELETE /v1/redactions/{id}` → 一律 `204`(幂等:存在、已删除、已过期、从未存在都返回 204;只有 401 例外)。
  仅删除实际存在的记录时写墓碑；从未存在的 id 在 DELETE 后 restore 仍返回 `404`，重复 DELETE 不延长墓碑保留时间。
  DELETE 释放该记录的 mapping，但保留 session 标签状态（以实体类型和规范化原值为键，以及标签计数器），即使该 session 已没有记录，也保留跨请求的占位符一致性。
  DELETE 不缩短 session 到期时间；该时间由 session 请求及其记录 TTL 延长，到期后由 TTL sweep 清理，进程重启也会丢失。因此 DELETE 不会立即释放 session 中所有原值引用。
- `GET /v1/info`:
```json
{"service_version":"","contract_version":"0.4.2","policy_version":"","model_version":"",
 "prompt_versions":{"detection":"","assessment":""},"context_store_version":"",
 "tiers":{"high":{"rule":"redact","threshold":0.2},"medium":{"rule":"redact","threshold":0.5},
          "low":{"rule":"retain_unless_combined"},"public":{"rule":"retain_if_confident"}},
 "entity_types":[{"type":"PHONE_PERSONAL","tier":"medium"}],
 "limits":{"max_request_bytes":262144,"timeout_ms":15000,"max_ttl_seconds":86400,"max_records":1000},
 "failure_behavior":"redact_all_candidates"}
```
- `GET /healthz` → 200 `{"status":"ok"}`;`GET /readyz` → 200 `{"mode":"ready|degraded", "components":{"rules":"up","presidio":"up","model_detection":"up|down","model_assessment":"up|down"}}`,规则/Presidio 没加载好才 503。
- `GET :9100/metrics`(独立端口,绑 127.0.0.1)。

---

## 4. 组件接口(交给队友的函数签名)

共享类型在 `contracts/types.py`(我 W9 前发出,队友只读不改):

```python
FieldPath = str                       # §3.3
Tier = Literal["high","medium","low","public"]
Detector = Literal["rules","presidio","model"]

class Segment(BaseModel):             # 一个字段文本 + 来源标签
    field: FieldPath; text: str
    source: Literal["purpose","header","subject","body","quoted_thread","signature"]
class Candidate(BaseModel):
    field: FieldPath; start: int; end: int; type: str   # type 属 taxonomy
    detectors: set[Detector]; hint: str | None = None   # hint:term_list_match / allow_list ...
class ScoredCandidate(BaseModel):
    candidate: Candidate
    raw_score: float | None           # None = 模型无法分类
    is_private: bool | None
class Decision(BaseModel):
    candidate: Candidate; tier: Tier; action: Literal["redact","retain"]
    confidence: float | None; reason: str          # 稳定码,无原文
class ModelCallError(Exception): ...  # 子类:ModelUnavailable / ModelTimeout / ModelOutputUnparseable
```

**所有 offset 相对 `Segment.field` 的原文,组件内部若加了前缀/拼接,返回前必须换算回来。**

| 组件(负责人均待讨论确认) | 暴露的函数 | 说明 |
|---|---|---|
| Segmentation (负责人待确认) | `segment(purpose: str, email: EmailIn) -> list[Segment]` | 纯函数,不抛异常(无法判断的归 body) |
| Rules (负责人待确认) | `detect_rules(segments: list[Segment], ctx: ContextStore) -> list[Candidate]` | 含校验和(Luhn 等)、词表匹配(`hint="term_list_match"`)。**同步、CPU 型,我在线程池里跑** |
| Presidio (负责人待确认) | `detect_presidio(segments: list[Segment]) -> list[Candidate]` | 同上;启动时 `warmup()` |
| ContextStore (负责人待确认) | `ContextStore.load(path) -> ContextStore`;`.term_list`、`.allow_list`、`.version: str`、`.is_allowed(type, text) -> bool` | 启动加载,只读 |
| Detection prompt (负责人待确认) | `build_detection_prompt(segments) -> str`;`parse_detection(raw: str, segments) -> list[Candidate]`;`DETECTION_PROMPT_VERSION: str` | 解析失败抛 `ModelOutputUnparseable` |
| Assessment prompt (负责人待确认) | `build_assessment_prompt(segments, cands) -> str`;`parse_assessment(raw: str, cands) -> list[ScoredCandidate]`(漏掉的候选 `raw_score=None`);`ASSESSMENT_PROMPT_VERSION` | 同上 |
| Calibration (负责人待确认) | `Calibrator.load(path)`;`.calibrate(raw: float) -> float`;`.version` | 纯函数 |
| Merge (负责人待确认) | `merge_candidates(*lists: list[Candidate]) -> list[Candidate]` | 按字符位置合并重叠,`detectors` 取并集,type 冲突取更高 tier |
| Tier/Decision (负责人待确认) | `decide(scored: list[ScoredCandidate], policy: Policy, overrides: Overrides, ctx) -> list[Decision]`;`decide_degraded(cands: list[Candidate], policy) -> list[Decision]`(全部 redact、`confidence=None`、`reason="degraded_redact_all"`) | 纯函数;`Policy.load(path)`、`.tier_of(type)`、`.version` |
| Pseudonymizer (负责人待确认) | `pseudonymize(purpose: str, email: EmailIn, decisions: list[Decision], labels: LabelState) -> PseudonymResult`;`restore(reply_text: str, mapping: dict[str,str]) -> RestoreOutcome` | `PseudonymResult{redacted_purpose, redacted_email, spans: list[SpanOut], mapping: dict[str,str]}`;占位符格式 `[TYPE_n]`;`LabelState` 由我传入(§5.3),同实体同标签 |

**我暴露给队友的**:`Deadline`(`.remaining_ms()`)、`ModelClient`(队友不直接调,只写 prompt/parse)、`audit.log_decision(...)` 不暴露——orchestrator 统一记,避免组件碰日志。

**我自己实现的 Protocol(队友可对着用)**:
```python
class ModelClient(Protocol):
    async def generate(self, prompt: str, *, prompt_name: Literal["detection","assessment"],
                       deadline_ms: int) -> str: ...   # 抛 ModelUnavailable / ModelTimeout
```

测试验收:每个组件交付时必须通过 `tests/contract/test_component_<name>.py`(我写,用 Karina 的标注邮件子集 + 边界用例,包括 offset 往返正确性、空输入、Unicode、重叠)。

---

## 5. 编排(`pipeline/orchestrator.py`)

### 5.1 流程(对应 18 步)
```python
async def redact(req, rid, deadline) -> RedactionResult:
    segs = segment(req.purpose, req.email)                                  # 3-4
    async def det_model():                                                  # 6-7
        raw = await model.generate(build_detection_prompt(segs),
                prompt_name="detection", deadline_ms=deadline.model_budget())
        return parse_detection(raw, segs)
    r_rules, r_pres, r_model = await asyncio.gather(                        # 5 ∥ 6
        to_thread(detect_rules, segs, ctx), to_thread(detect_presidio, segs),
        det_model(), return_exceptions=True)
    degraded = classify_failures(r_rules, r_pres, r_model, stage="detection")
    cands = merge_candidates(*ok_lists)                                     # 8
    if not degraded:
        try:                                                                # 9-12
            raw = await model.generate(build_assessment_prompt(segs, cands),
                    prompt_name="assessment", deadline_ms=deadline.model_budget())
            scored = parse_assessment(raw, cands); calibrate(scored)
        except ModelCallError as e: degraded = Degraded(e.reason, "assessment")
    decisions = decide_degraded(cands_rules_presidio, policy) if degraded \
                else decide(scored, policy, overrides, ctx)                 # 13-14 / F1-F2
    out = pseudonymize(req.purpose, req.email, decisions, labels)           # 15
    records.put(rid, out.mapping if retain else None, ...)                  # 15
    audit.log(...)                                                          # 16
    return out.with_flags(degraded)                                         # 17
```
要点:
- **降级候选集** = 仅 rules + presidio(含词表命中),丢弃模型检测结果(OQ15 当前结论);规则引擎异常 → 抛 500。Presidio 异常 → 降级(`recognizer_failure`),此时候选 = rules(+ 若检测调用成功则模型候选),跳过评估与阈值,全 redact。
- **截止时间**:`Deadline(timeout_ms)` 在收到请求时创建。`model_budget() = min(model_call_timeout_ms, remaining − degraded_reserve_ms)`;`degraded_reserve_ms`(默认 1,500,压测后调)保证模型失败后降级路径还能跑完。最外层 `asyncio.timeout(timeout_ms)`,超时 → 504 并释放记录槽位;线程池里已在跑的 Presidio 无法取消,结果丢弃。
- **模型并发**:`asyncio.Semaphore(model_concurrency)`(默认 1,Ollama 单卡);排队时间计入截止时间,单独打指标 `vg_model_queue_wait_seconds`。
- **容量**:请求一进来先**预留**记录槽(满 → 503 `capacity_exhausted`,在做任何处理之前),失败/504 时归还。
- **每阶段计时**用 `with stage_timer("segment")` 上下文管理器,同时写 Prometheus 与 audit。
- 模型适配层失败分类:连接拒绝/5xx → `unavailable`;超过 `deadline_ms` → `timeout`;(prompt/parse 的解析异常由 Anmol 的 parse 抛 `unparseable`,orchestrator 统一捕获 `ModelCallError`)。

### 5.2 降级响应字段
由 `degrade.py` 统一构造:`degraded=true`、`degraded_reason`、`degraded_stage`;所有 span `confidence=None`、`reason="degraded_redact_all"`、`detectors ⊆ {rules,presidio}`。

### 5.3 记录存储(`records/store.py`)
```python
@dataclass
class Record: id; created_at; expires_at; mapping: dict[str,str] | None
              session_id: str | None
class RecordStore:
    def reserve(rid) -> None                   # 满 → CapacityExhausted
    def commit(rid, mapping|None, ttl_s, session_id|None) -> Record
    def release(rid) -> None                   # 失败时归还预留
    def get(rid) -> Record                     # NotFound / Gone
    def delete(rid) -> bool                    # 幂等;留墓碑
    def label_state(session_id) -> LabelState  # 同 session 共享、TTL 与最长记录一致
    def sweep() -> int                         # 后台任务每 30s,过期记录清掉并 zeroize mapping
```
`threading.Lock` 保护;`max_records` 默认 1,000(OQ10 待压测定);容量不满足时**绝不淘汰**存活记录。

---

## 6. 可观测性

**指标**(`obs/metrics.py`,所有标签基数有界,绝不含文本/ID):

| 指标 | 类型 | 标签 |
|---|---|---|
| `vg_http_requests_total` | counter | route, method, status |
| `vg_request_duration_seconds` | histogram | route, mode=`normal|degraded|error` |
| `vg_stage_duration_seconds` | histogram | stage∈{validate,segment,detect_rules,detect_presidio,detect_model,merge,assess_model,calibrate,decide,pseudonymize,audit} |
| `vg_model_calls_total` | counter | prompt, outcome∈{ok,unavailable,timeout,unparseable} |
| `vg_model_call_duration_seconds` / `vg_model_queue_wait_seconds` | histogram | prompt |
| `vg_degraded_total` | counter | reason, stage |
| `vg_spans_total` | counter | tier, action, mode |
| `vg_records_active` / `vg_records_capacity` | gauge | — |
| `vg_records_removed_total` | counter | reason∈{expired,deleted} |
| `vg_inflight_requests` | gauge | — |
| `vg_service_mode` | gauge | mode∈{ready,degraded,down}(0/1) |
| `vg_build_info` | gauge=1 | service/contract/policy/model/prompt_det/prompt_assess/context_store 版本 |

8 个面板与 §4 P0 清单一一对应:面板 1←http_requests;2←(2xx/(2xx+5xx));3←duration 按 mode 分;4←stage;5←degraded;6←model_calls;7←records;8←service_mode+build_info。Grafana JSON 与 `prometheus.yml` 放 `dashboards/`,以代码提交。

**日志**:structlog JSON,字段**白名单**处理器(不在白名单的 key 直接丢弃),白名单 = request_id、route、status、duration、stage、tier、action、counts、error_type、versions。**审计日志**单独 JSONL 文件,每请求一行:`request_id, ts, degraded, degraded_reason, spans:[{type,tier,action,raw_score,calibrated,detectors}], timings, versions`;raw_score 只在这里出现。

**泄漏检查**(验收):测试里发 canary 字符串(如 `CANARY-412-555-0182`、`ZXQ_PERSON`),跑完后 grep 全部日志、审计、`/metrics` 输出、错误 body,命中即失败;包含异常堆栈路径(自定义异常 message 不拼入输入)。

---

## 7. 测试与验收(写成测试,不靠肉眼)

- **契约测试**:从 0.4.1/0.4.2 文档生成,覆盖每个状态码、每个字段、`extra=forbid`、High-tier override → 422、session 无 retain → 422、restore 的 4 种结果。
- **失败注入**(W10 全通过):模型停止、模型超时、乱码输出、评估调用失败(检测成功)、Presidio 抛异常、规则抛异常(→500)、容量耗尽、超大请求体、`timeout_ms` 极小(→504)。断言:状态码、`degraded_*` 字段、所有 span 都 redact、指标计数正确。
- **泄漏**(§6)、**压测**(locust/k6:并发 1/2/4 × 输入长度,正常与降级分开,输出 `timeout_ms` 和 `model_call_timeout_ms` 建议值)。
- **组件契约测试**(§4 末)。

---

## 8. 里程碑对应(沿用 development-schedule)

| 周 | 本方案交付 |
|---|---|
| 现在(W8 假期) | 定稿 0.4.2 + 本接口文档发给 Yudi/Anmol(队友要的东西必须在 W8 前交完,时程里 W7 已承诺) |
| W9 | `contracts/` + 桩、gateway 全部端点、校验、problem+json、records、model 适配层、基础指标 |
| W10 | orchestrator 后半(并行、deadline 预算、降级)、失败注入、真组件接入(入口:10/30) |
| W11 | 仪表盘 8 面板、压测、定 `timeout_ms`/`degraded_reserve_ms` |
| W12 | 泄漏检查、加固、契约冻结 |
| W13 | README/API 文档/demo 脚本 |

## 9. 仍需团队确认

1. **组件负责人**:Segmentation、Rules/Presidio/ContextStore、Prompts、Calibration、Merge、Decision、Pseudonymizer 全部**待讨论确认**(时程 §7 #1)。接口按组件划分,与负责人无关,确认后直接对号入座。
2. §3.2 的 `policy.overrides` 结构请 Privacy Research 过目。
3. 产出物同步:本文件已放在 `service engineering/`,0.4.2 契约正文与 `virtual-gold-capstone/docs/api/` 待同步。

已定决策(本轮):路径以 `POST /v1/redactions` 为准;Presidio 失败走降级、规则失败返回 500;DELETE 恒返回 204;restore 不消费记录;降级时 allow-list 不生效;技术栈 Python + FastAPI(局限见 §10)。

## 10. 技术栈局限(Python + FastAPI)与对策

结论:对本项目够用,没有硬性障碍,但有以下约束,已在设计里处理:

| 局限 | 影响 | 对策 |
|---|---|---|
| 记录存在进程内存 | 不能多 worker / 多进程部署(各进程记录不共享,restore 会随机 404) | 单进程部署;吞吐瓶颈本来就是单卡本地模型(`model_concurrency=1`),单进程不是瓶颈。写进部署文档 |
| Presidio/规则是 CPU 型同步代码,GIL | 线程池里并发 CPU 请求会互相拖慢;超时后线程无法强杀,504 后仍占 CPU | 线程池大小设上限(与 `model_concurrency` 同量级);压测测输入长度的影响;如压测显示不行,再把检测换成进程池 |
| Presidio/spaCy 模型体积和冷启动 | 启动慢,`/readyz` 需要等预热 | 启动时 `warmup()`,`/readyz` 在加载完成前返回 503;镜像/依赖提前下载 |
| "无外网"要求 | sandbox 里 `pip`、spaCy 模型、Ollama 模型无法在线拉取 | 提前打包 wheels 和模型文件离线安装(W7 沙盒确认时一并问) |
| Python 字符串不可清零 | `mapping` 过期后内存里的原值不能保证被擦除 | 删除即丢弃引用;不落盘;不声称"内存清零"。这是原型,文档里如实写 |
| 延迟 | 框架本身开销毫秒级,相对秒级的两次模型调用可忽略 | 无需处理 |

## 自检
- 逐步对照时序图 1–18、F1–F3、R1–R4、D1–D3,每一步在 §5/§3.4/§3.5 都有落点。
- 逐项对照 slides 35/37 的交付与指标清单,§6 全部覆盖。
- 批准后:先写桩 + 契约测试,`pytest tests/contract` 全绿即为 W9 第一个检查点。
