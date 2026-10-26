# 團隊代辦事項

所有待決事項與待辦動作集中在這裡。決定會影響架構的,同一個 PR 一併更新 `docs/`。
**負責人**與**期限**在團隊會議上填。英文版:[`TODO.md`](TODO.md)。

會議時間(美東,皆每週):客戶 週一 18:00–19:00 · 教授 週二 17:00–18:20 · 團隊 週五 15:30–16:30。

> **基準:2026-10-05 實際報告的期中簡報。**
> [`meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf`](<../meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf>)(49 頁)即團隊共識,已經團隊內部討論並與教授確認。**本文件的頁碼都指這一版。**2026-10-23 以前本文件引用的是 10/3 的 42 頁草稿,頁碼已全部改過。
> 9/28 與 10/5 的客戶會議紀錄已歸檔(`meetings/client/2026-09-28/`、`2026-10-05/`,Gemini)。9/29 教授會議與 10/2 團隊會議沒有紀錄。這裡較早的條目、9/27 團隊筆記或研究文件與簡報不一致時,一律以簡報為準。10/19 客戶會議有 Zhexuan 的 9 頁報告(先講服務與隱私元件,再由 Anmol 講模型工作)在 `meetings/client/2026-10-19/`;那次還沒有 Gemini 紀錄。10/26 客戶會議的素材(Zhexuan 的加密與 API v2 簡介、Anmol 的 VPC 模型報告、Yudi 的規則 + Presidio 評測與給客戶審的分級表)在 `meetings/client/2026-10-26/`。
> 決策紀錄中 2026-10-03 的各列是依 10/3 草稿寫的。定稿多了**路由規則**,輸入也改成**「英文文字與文件」**;這對 API contract 的影響由 A14、A15 追蹤。

## 2026-10-25(週日)團隊會議:結論

在週一客戶會議前舉行;Anmol 缺席。紀錄:[`meetings/team/2026-10-25/notes-zh.md`](../meetings/team/2026-10-25/notes-zh.md)。依這些結論做的客戶頁面是 `meetings/client/2026-10-26/agenda-en.html`(順序:Yudi、Anmol、Karina、Zhexuan)。

| # | 主題 | 項目 | 結論 |
|---|---|---|---|
| 1 | Anmol 的 VPC 報告 | B72、A15、D51 | Anmol 缺席,報告**原樣**給客戶。客戶頁面自己照實寫:在託管模型 API 上測試,還沒部署到 VPC。措辭、本機連結與 §7 的 CMU 那句等 Anmol 回來再處理。待定:報告展示或寄出前,§7 那句要跳過還是刪掉(Mark) |
| 2 | 兩套分級規則 | A19、D49 | 客戶審 **Yudi 的 policy-0.1.3**(22 類,Public 0.8)。這是 Yudi 的提案,他覺得比較準,想聽客戶看法。客戶確認後才合併(B71)。客戶頁面註明模型數字會用確認後的分級表重跑(B69) |
| 3 | Placeholder 格式 | A18 | Zhexuan 把 API v2 **當作提案**展示並詢問客戶(客戶頁面 Q6:存不存原文、看不看得到類別、能否原樣傳遞、對話 ID 與 24 小時)。他的 PR #10 已於 2026-10-26 合併(B73) |
| 4 | 連結打不開 | B72 | Zhexuan 簡介連到的兩份文件在 PR #10(`docs/api/`),已在 main。repo 是私有的,所以客戶頁面只寫 `docs/api/`,不放連結。Anmol 的 24 個連結等他處理 |
| 5 | Karina 的資料集 PR #9 | B46、A16、A19、B74 | Karina **刻意用 policy 0.1.1**,因為 0.1.3 只是 Yudi 的提案:資料集沒有過時,也不用等 Yudi 的分支。客戶若確認 0.1.3,她再重新產生 `service_type` 與 `tier`。她說已複核完,但 PR 裡「Karina check」欄仍是空的、`gt_status` 仍是 draft(B74)。對客戶照她 README 的說法描述。86 個 Low 級片段、出生日期、交易對象與編號隨分級表一起問客戶(Q1)。`NON_PERSON_WORDS`(B75):之後再談 |

## 2026-10-23(週五)團隊會議要談的

今天的會議帶這些。Phase 1 下週一 10/26 開始,同一天也是下次客戶會議。

| 主題 | 項目 | 今天要定的 |
|---|---|---|
| 範圍對照定稿 | A14 路由、A15 文件輸入 | 要做路由和文件輸入,還是向客戶說明範圍收窄。contract 修改的負責人與日期(11/15 凍結前) |
| 評測 | A16 標準答案、B59、B60、B46 | 外部標註資料集和 100 封信怎麼分工;100 封信什麼時候放進 `data/` |
| 模型與分數 | A13、B58、A11、A12 | 誰跑 Gemma 4、何時完成;確認信心分數的分工,`score_method` 歸誰 |
| M2(11/1 到期) | B41 | 偵測與評估的 prompt 和解析器(還是 stub)誰寫;第一次用 Ollama 端到端跑 |
| Mark 對客戶的待辦 | B56、B57、B62、B63 | 各項進度;週一前要寄出哪些 |
| Repo 與流程 | B64、B65、B35 | Zhexuan 的 `docs/api/` 更新;合併前要審查的規則;關掉 PR #3–#5 |
| 週一客戶會議要問的 | D49、D50、D52、E68 | 再問一次分級表審閱、來源標記、VG08 開放;SOW 還沒簽 |

## A. 待決事項

| # | 項目 | 說明 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|---|
| 18 | **API v2 tokenization:要不要採用?** | Zhexuan 10/26 的簡介(`meetings/client/2026-10-26/briefing-encryption-api-*.html`)新增 `/v2/redactions`、`/v2/restorations` 與 `DELETE /v2/groups/{group_id}`:每個對話由客戶提供 `group_id`,每個對話一把隨機金鑰並由主金鑰 KEK 封裝,兩種模式(`mapping` 為預設,原文以 AES-SIV 加密後保存;`aes_siv` 把密文直接放進 token),多個實例共用 Redis,最長 24 小時。這超出 contract 0.4.2,也和 2026-10-03「對照表每次 redaction 各自保存」的決定不同。token 長得像 `[VG:2:…]`,長度隨原文增加,而簡報與 Anmol 的 harness 用的是 `[PERSON_1]`;雲端模型會不會把長 token 原樣傳回還沒測過(簡介自己也這麼說)。簡介依據的是本機 commit `c706bb6`;GitHub 上的 `fix/update-api-infra` 停在 `2977867`,缺關閉對話的端點與 conversation-keys 文件,也還沒開 PR。要在 11/15 contract 凍結前和 A14 一起決定 **10/25 團隊會議:**10/26 當作提案給客戶看,Zhexuan 想聽客戶看法(客戶頁面 Q6)。**10/26:PR #10 已合併**(`ade699b`,squash),含關閉對話端點與 `docs/api/` 的四份文件;沒設 `VG_TOKEN_KEYS` 時 v2 關閉,v1 不變。審查後續見 B73。仍待定:要不要把 v2 設為預設,以及用真實模型測長 token | Zhexuan、Mark | 11/15 前 | [ ] |
| 19 | **統一一套分級政策。** | Yudi 給客戶的分級表(`meetings/client/2026-10-26/tier-table-client-review-en.docx`,policy-0.1.3-provisional)是**4 級、22 類**:High ≥ 0.2、Medium ≥ 0.5(每個請求可調)、Low 除非 3 種以上低級類別同時出現否則保留、Public 除非 ≥ 0.8 否則保留。Anmol 的 harness(10/26 報告 §3.2、§8)用**3 級**:HIGH 0.20 / MEDIUM 0.50 / LOW 0.50,類別是資料集的 18 類加 FACT,分數在 0.35–0.65 一律遮蔽。期中簡報是 3 級。要講定服務、harness 與資料集(PR #9 的 `tier` 取自 `policy.yaml`)用同一套,並說清楚客戶審的是哪一套 **10/25 團隊會議:**10/26 客戶審 Yudi 的 policy-0.1.3。Karina 的資料集在客戶確認前維持 0.1.1;Anmol 的數字用確認後的表重跑(B69) | Yudi、Anmol | 10/26 會議前 | [ ] |
| 14 | **請求層級的路由:做還是不做?** | 定稿把「Tier + routing rules」列為交付物(第 5 頁),服務要「redact and apply routing」、VG08「check release eligibility」(第 33 頁),Phase 2 要「check routing before cloud use」(第 45 頁),dashboard 也統計路由狀態(第 37 頁)。給客戶的 SOW(`Scope of Work -  20261005.docx`)另外寫了「獨立的請求路由政策,決定整個請求留在本地還是可以送出」。但 2026-10-03 的決策紀錄寫不整封擋下(`LOCAL_ONLY`),API contract 0.4.2 拿掉了請求層級的判斷,`service/` 也沒有。要決定路由的意思(服務回傳一個狀態,還是 VG08 依 span 自己判斷)並寫進 contract,或向客戶說明範圍收窄。11/15 contract 凍結前一定要定 | Mark、Zhexuan | 下次客戶會議 | [ ] |
| 15 | **輸入範圍:只有 email,還是英文文字與文件?** | 9/28 對齊「現階段輸入語言與文件限英文」;定稿(第 4、5、45 頁)與 SOW 都寫「English-language text and documents」,email 只是第一個 benchmark 格式。Contract 0.4.2 只接受 email 結構,附件與 OCR 列為不在範圍內。要決定「文件」請求在 API 裡長什麼樣子(純文字加來源標記?),或把說法限縮到 email。10/26:Anmol 的報告已預設「任意企業文件」,並規劃 6 種格式、18 份文件的測試(合約、表格、備忘錄、人資紀錄、日誌、逐字稿);這是計畫,不是決定 | Zhexuan、Mark | M4 前 | [ ] |
| 16 | **評測的標準答案從哪來** | 10/5 對齊:找網路或 Kaggle 上已標註好的資料集當標準答案,起因是 Aarvin 問團隊怎麼信任 LLM 產生的測試案例。要決定它和 100 封信 benchmark 怎麼搭配:外部資料集拿來校正和算 recall,100 封信負責主管信件的情境案例(情境、攻擊、商業機密)?校正(A11)取決於這一點。10/19(Anmol):100 封信分成 60 封開發用、40 封保留測試(需遮的片段分別 591 與 380 個);保留的 40 封只在 pipeline 凍結、D70 的目標談妥後跑一次。10/26:Yudi 用外部已標註資料集 **ai4privacy pii-masking-400k** 的 1,000 筆英文資料評測規則 + Presidio;授權禁止再散布,只能留在本機,不能放進 `data/`。Karina 的 PR #9 加入 100 封信,並附人工複核的 `ground_truth` 欄 | Karina | Phase 1 | [ ] |
| 13 | **用哪個開源模型** | 10/5:初步 benchmark 跑了 Llama 3.1 8B 與 Qwen 2.5 7B;Aarvin 建議試 Gemma,並且現階段只用**一個**模型(決策紀錄 2026-10-05)。**10/19(Anmol,報告第 8–9 頁):**在同樣 15 封開發用信件上,透過託管 API 跑的 Llama 3.3 70B 找到 92.8% 的已標註實體,但仍有 16.2% 的隱私字元沒遮,公開文字被遮了 18.5%;Llama 3.1 8B(77.3%)與 Qwen 3.5 9B(70.7%)是較早在本機 M4 上、用舊版 pipeline 跑的結果。建議:**Llama 3.3 70B** 自架在客戶的私有雲,**Llama 3.1 8B** 用 Ollama 當筆電備案,Gemma 2 27B 為挑戰者(只有 3 封信的試跑)。未決:70B 需要客戶的 GPU(D51)、實測用的是託管 API、`service/config/service.yaml` 仍寫 `llama3:8b`。等同條件重跑(B69)後選定。**10/26(Anmol 的 VPC 報告,`meetings/client/2026-10-26/`):**修掉 harness 的六個缺陷後,在同樣 15 封信上跑了 9 種新設定。洩漏最低的是 **Qwen 3.8 27B + GLiNER**(一張 24–48 GB GPU):隱私字元未遮 7.4%、FACT 子句抓到 90%、每封 2.4 秒,但公開文字被遮 21.7%。GPT-OSS 120B(一張 80 GB GPU)誤遮公開文字最少(5–12%),但洩漏較多(17–27%)。不用 LLM 的規則 + Presidio + GLiNER:洩漏 29.4%、0.11 秒,提議當降級備案。所有結果都是用免費額度的託管 API(Groq、OpenRouter)跑的,不是 VPC;仍然只有 15 封信、涵蓋 15 個領域中的 4 個 | Anmol、Mark | B69 之後 | [ ] |
| 11 | **信心分數歸誰,以及 `score_method` 欄位** | 延續 9/27 延後事項 B。簡報定了方法(模型原始分數,用標註信件分組校正,第 17 頁),但沒定誰做哪一步。尚未確認的分工提案:Anmol 產生原始分數、Yudi 提供校正程序(已在 `service/vg_redactor/privacy/calibration.py`,擬合前是恆等函數)、Karina 決定門檻(門檻是評測的產出)、API 欄位傳的是**校正後**的分數。每個 span 加一個 `score_method` 欄位,不然看到 0.55 的人不知道那是什麼 | Anmol | W9 | [ ] |
| 12 | **模型分數沒有鑑別力時的備案** | 2026-09-14 的篩檢發現 8B 模型自報信心會飽和(91.7% 的回答自報 ≥95%)。10/5 Aarvin 也提出同樣的疑慮。如果第 17 頁的校正分組結果是平的,就沒有東西可以校正。Yudi 的提案已有備案:以共識計分(標出該 span 的偵測器比例、3–5 次重複執行中判為私密的比例)。第一批 baseline 數字出來時決定 | Anmol、Yudi | Phase 1 | [ ] |

## B. 待辦動作

### 客戶會議帶出的事項(9/28、10/5)

| # | 動作 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|
| 56 | **把初步 benchmark 結果與期中簡報寄給客戶**(10/5 的下一步;資料在專案 Drive) | Mark | | [ ] |
| 57 | **一頁的 benchmark 報告**給 Aarvin 與 Alex:列出測過的所有模型,包括 Gemma 與新推出的模型(10/5)。Anmol 10/19 報告第 8–9 頁已涵蓋大部分內容 | Mark | | [ ] |
| 58 | **在現有 benchmark 框架裡跑 Gemma**(10/5)。10/19:Anmol 用 3 封信試跑 Gemma 2 27B(隱私字元未遮 8.2%,同樣三封 70B 為 16.4%);15 封的完整試跑因 API 額度用完而失敗,目前無法排名。完整重跑併入 B69。供 A13 使用 | Mark、Anmol | | [ ] |
| 59 | **找一個已標註好的 PII 資料集**(網路或 Kaggle),當作標準答案的 baseline(10/5)。供 A16 使用 | Karina | | [ ] |
| 60 | **說明產生出來的 100 封信資料集為什麼可信**(10/5,Aarvin 的問題)。供 A16 使用 | Karina | | [ ] |
| 61 | **測試複雜的隱晦資訊**:沒有單一名稱的機密想法(56 個商業機密項目),並為它們寫 system prompt(10/5,Alex 的問題) | Anmol、Karina | Phase 1 | [ ] |
| 62 | **把 API contract 0.4.2 寄給 Alex 與 Aarvin 審閱。**9/28 的下一步是寄出 contract 草稿;0.4.2 現在在 `docs/api/`。和 A14 的答案一起寄 | Mark | A14 之後 | [ ] |
| 63 | **把資訊分類表寄給客戶**,讓他們對照自己的情境檢查(9/28)。和 D49 是同一張表 | Mark | | [ ] |

### 建置(簡報第 44 頁的里程碑)

| # | 動作 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|
| 40 | M1:API contract 0.4.2 與服務骨架。**2026-10-19 完成**(PR #7,晚了八天):contract 與介面文件在 `docs/api/`,服務在 `service/`,43 個測試 | Zhexuan | 2026-10-11 | [x] |
| 41 | **M2:端到端 pipeline 含失效路徑。**隱私研究元件 2026-10-23 合併(PR #8,76 個測試)。仍是 stub 的:切段、偵測與評估的 prompt 及其解析器(模型工作)、restore。Ollama 後端還沒端到端跑過。Anmol 的模型原型(偵測、依情境評估、遮蔽;10/19 報告第 7 頁)目前在服務之外執行,把它接進服務屬於本項 | Zhexuan、Anmol | 2026-11-01 | [ ] |
| 42 | M3:dashboard 與壓測結果。Prometheus + Grafana 與 8 個面板的 dashboard 已在 `service/dashboards/`(PR #7);壓測結果還沒有 | Zhexuan | 2026-11-08 | [ ] |
| 43 | M4:VG08 整合(Phase 2,11/2–11/15);contract 凍結。需要 A14、A15 與 D52 | Zhexuan、Mark | 2026-11-15 | [ ] |
| 44 | M5:程式凍結(軟凍結 11/18) | 全員 | 2026-11-22 | [ ] |
| 45 | M6:期末報告 | Mark | 2026-11-30 | [ ] |
| 46 | **評測資料集放進 repo**(`data/`):100 封虛構信件、999 個標註項目、18 種類型,JSONL 格式如第 41 頁。尚未 commit。內容是虛構的,符合「不放真實資料」的規則。**PR #9(Karina,2026-10-25 開)**把它放進 `data/baseline/baseline_v1.1.jsonl`,附複核工作表與 `score.py`;待審 **10/25 團隊會議:**刻意用 policy 0.1.1,不用等 Yudi 的分支。Karina 說已複核完,PR 裡還看不到(B74) | Karina | | [ ] |
| 47 | **先 baseline,再做消融**(第 19 頁):Rescriber 式 baseline → 加偵測器聯集 → 加名字擴散 → 加重複執行 → 加分級門檻。在一個子集上調,在保留子集上報告。主要指標是各等級的洩漏率;另外追蹤過度遮蔽、校正、每封信秒數。10/19:在 60 封開發用信件上調,在保留的 40 封上報告(A16)。Phase 1 為 10/26–11/8(第 45 頁) | Karina | 2026-11-08 | [ ] |
| 48 | **架構文件 v0.4。**`docs/architecture/` 仍是 v0.3,也就是轉向前的混合架構。v0.4 寫好之前,以簡報(第 13、14、22–33 頁)與 `docs/api/` 為架構依據 | Mark | | [ ] |
| 64 | **更新 `docs/api/`**(Zhexuan 的檔案)。(1)`service-interfaces-v0.4.2-zh.md` 還是動工前的計畫:引用 0.4.1、`development-schedule.md`、`protocols.py`、`pseudonym.py`、`structlog`,這些都不存在,英文版卻稱它為「原版」。(2)兩份都沒提到 `service/vg_redactor/privacy/`(PR #8);英文版還寫「Owners are not confirmed yet」。(3)`redaction-api-report-en-v0.4.2.md` 把語言放在版本前面,和其他檔案不一致。(4)contract 沒有中文版。(5)其中 session 保留的描述寫在 PR #8 之前,PR #8 存的是 HMAC 金鑰而非原始值(Zhexuan 自己 10/19 報告第 5 頁也提到) | Zhexuan | | [ ] |
| 65 | **合併前要審查。**PR #7 由作者自己合併、沒有經過審查,違反 README 的「Nobody merges their own PR」。開啟分支保護(至少一個核准),或再向團隊說明這條規則 | Mark | 下次團隊會議 | [ ] |
| 69 | **同條件模型重跑。**用和 10/19 Llama 3.3 70B 相同的 pipeline 版本與信件,重跑 Llama 3.1 8B、Qwen 與 Gemma 2 27B;目前 8B 與 Qwen 的數字是舊結果。15 封信只涵蓋 15 個業務領域中的 4 個,應擴大到 60 封開發用信件。託管 API 一直因額度用完而失敗:決定用哪家、誰付費。供 A13 使用 **10/25:**客戶頁面承諾用客戶確認的分級表重跑,讓數字能和 D70 的目標比較 | Anmol | Phase 1 | [ ] |
| 71 | **把 10/26 簡介背後的程式放上 GitHub。**(1)Zhexuan:推上 `c706bb6`,並為 `fix/update-api-infra` 開 PR(A18)。(2)Yudi:為 `feat/privacy-detection-fixes`(`d9cdf67`)開 PR;簡介寫「PR #9」,但 #9 已是 Karina 的資料集 PR。(3)Anmol:他的 harness(`benchmarks/2026-10-05-followup/`、prompts、calibration profile v1.4.0)不在任何分支上;報告裡 24 個連結都指向 `file:///Users/anmolsahu2k/…`。**等 10/26 客戶會議之後:**三人在客戶確認後才開 PR 或更新 PR **10/26:**(1)完成,PR #10 已合併為 `ade699b`。(2)(3)仍等客戶 | Zhexuan、Yudi、Anmol | 2026-10-26 之後 | [ ] |
| 72 | **會議前修正要給客戶看的檔案。**Anmol 的報告:把免費託管 API 的結果稱為「VPC 設定」,並把「客戶部署在 VPC」「處理任意企業文件」寫成既定事實(A15、D51 都還沒定);§7 提到透過教授申請的 $50 CMU OpenRouter 額度(D51 說不要向客戶提 CMU 管道);還有本機 `file://` 連結。Zhexuan 的簡介:指向 `docs/api/` 的本機 `file://` 連結;中文版是簡體 **10/25 團隊會議:**Anmol 缺席,報告原樣給;正確說法寫在客戶頁面。Zhexuan 連到的文件已隨 PR #10 進入 main | Anmol、Zhexuan | 2026-10-26 | [ ] |
| 73 | **PR #10 後續**(2026-10-26 審查)。(1)用真實信件示範前要修:`wire.py:11`(`CANDIDATE`,不分大小寫的 `\[VG…`)與 `wire.py:14`(`LEGACY`,任何 `[Word_N]`)會把 `[VGA]`、`[Item_1]`、`[vgl. …]`、`VG:good` 這類一般文字當成 token,`/v2/redactions` 回 422、還原被擋。(2)Redis 掛掉時 `/readyz` 把整個服務報成 degraded,但 v1 不用 Redis。(3)idempotency 指紋是沒加鹽的 SHA-256,改用 HMAC。(4)刪掉用不到的格式 1 程式。(5)過長的 purpose 回 `invalid-token`,而不是長度錯誤 | Zhexuan | (1)真實信件示範前 | [ ] |
| 74 | **把 Karina 的複核推進 PR #9。**她說每一列都看過了,但 PR 裡 `baseline_v1.1_review.xlsx` 的「Karina check」欄是空的(1,054 列),100 封信的 `gt_status` 都還是 `"draft: … pending Karina's review"`。填好欄位、更新 `gt_status`、push 到 `eval/benchmark-100`;之後審查並合併。在那之後才能說資料集經過人工複核 | Karina | | [ ] |
| 75 | **信箱名稱被當成人名。**規則偵測器在 100 封信上的 31 個多遮裡,30 個是「Benefits Center」「SEC Filing Alerts」這類顯示名稱;在 `NON_PERSON_WORDS` 補詞可解決大部分(PR #9 README 第 7 點)。之後再談(10/25) | Yudi | | [ ] |
| 35 | **關掉 Karina 的 PR #3、#4、#5。**為 vertical 交易情境建的;已由 100 封信資料集取代 | Karina | | [ ] |

## D. 等客戶回覆

| # | 項目 | 詢問日期 | 回覆 |
|---|---|---|---|
| 49 | **審閱分級表與機密詞表。**沒有客戶提供的專案代號、交易名稱、主要往來對象清單,`business_confidential` 偵測不到;在那之前 `service/config/context_store.yaml` 是空的。這項與 D50–D52 原本在 10/3 草稿的最後一頁;定稿沒有放這四項請求,10/5 紀錄也沒有回覆,要再問一次。**10/26:分級表已可給客戶審**(`meetings/client/2026-10-26/tier-table-client-review-en.docx`,Yudi)。問題:分級對不對(AMOUNT 為 Medium、ORG 為 Low、DEMOGRAPHIC 為 High)、要不要加類別、每級可接受的洩漏率。先解決 A19 **10/26 要問(客戶頁面 Q1):**0.1.3 的三個改動;AMOUNT、ORG、DEMOGRAPHIC;出生日期是否獨立成一類(Medium 或 High);交易對象放進機密詞表;編號(案件號、病歷號、訂單號)的分級;模型很確定的 Low 項目單獨出現時是否仍保留;新增類別 | 2026-10-05 | |
| 50 | **API 請求能否標示每段文字的來源?**(正文、引用串、主管自己打的字)。不一定受 NDA 限制 | 2026-09-28 | |
| 51 | **本地模型用的 GPU 與沙盒。**2026-09-15 起未決。9/28 部分回覆:在有沙盒之前,先透過網路用雲端託管的開源模型測試,或在本地用 Ollama(例如 Gemma);資源申請先經 Aarvin 與 Alex,再由 Inderpal 核准(決策紀錄 2026-09-28)。Mark 已於 2026-09-27 告訴 Aarvin 團隊只有個人筆電。CMU Public Cloud Services 維持內部備案,不向客戶提 | 2026-09-15 | 部分回覆,2026-09-28 |
| 52 | **開放 VG08 供整合。**Phase 2 於 11/2 開始 | 2026-10-05 | |
| 66 | **Alex 提供服務的初步版本**,用來做比較測試(10/5 的下一步) | 2026-10-05 | |
| 67 | **Alex 與 Aarvin 向團隊確認測試計畫**(兩個 phase;9/28 的下一步) | 2026-09-28 | |
| 53 | 與 CMU 的 NDA 附約進度(9/28 議程 E2) | 2026-09-28 | |
| 55 | 客戶需不需要 restore,還是他們自己的系統處理?每封信延遲目標與每日量(API contract 開放問題 1、2) | 2026-09-27 | |
| 70 | **跑保留的 40 封測試前先定驗收目標:**可接受的隱私文字洩漏率、公開文字過度遮蔽率、每封信秒數與失效時的行為(Anmol,10/19 報告第 9 頁)。與 D55 的延遲問題重疊Yudi 的分級表也逐級問客戶同一件事 | 2026-10-19 | |

## E. Scope of Work

| # | 項目 | 完成 |
|---|---|---|
| 26 | 第 6 節費用歸屬。**2026-10-03 定案,不寫金額:**專案若需要付費資源(GPU 或其他硬體、沙盒運算、模型 API),由客戶贊助或負擔,團隊使用前先與客戶確認。不設 `$[X]` 上限。SOW 不提 CMU 備案 | [x] |
| 68 | **期中給客戶的 SOW 簽了沒**(`docs/sow/Scope of Work -  20261005.docx`)。**截至 2026-10-23 尚未簽署**(Mark)。9/28 議程請客戶在期中簽署;10/5 紀錄沒有提到。它的範圍也和 contract 0.4.2 不同(A14、A15) | [ ] |

## 已結案與取代

2026-10-03 對照期中簡報結案;2026-10-23 再對照定稿與 9/28、10/5 紀錄結案。原文見 git 紀錄。

| # | 原本 | 狀態 |
|---|---|---|
| A17 | 最終交付日期 | **2026-10-23 確定:**期末報告 11/30,與簡報一致。10/5 Gemini 紀錄的「November 13」是轉錄錯誤 |
| B36 | 期中前改好 Scope of Work | 完成:`Scope of Work -  20261005.docx` 已在期中交給客戶。簽署狀態見 E68 |
| B37 | 重設「展示正在跑的東西」的期待 | 結案:期中報告了初步 benchmark 結果(10/5 紀錄) |
| B38 | 三個可能被問的問題先統一答案 | 隨期中結案。分數飽和的問題確實被問到(Aarvin),保留為 A12 |
| B39 | 記錄期中會議 | 完成:Gemini 紀錄在 `meetings/client/2026-10-05/notes-gemini-en.pdf` |
| D54 | 共用 Drive 與聊天工具 | 9/28 已回覆:Urte 開了 Slack workspace(付費方案);Mark 分享了放紀錄與文件的 Drive 連結 |
| A1 | 工具選型:HF transformers、自寫 router、Presidio、雲端 SDK | **已取代。**推論改用 Ollama(決策紀錄 2026-10-03)。Presidio 保留為三個偵測器之一。沒有 router,也沒有雲端呼叫:服務本身不呼叫雲端 |
| A2 | RAG 列為 stretch | 結案。不屬於 redaction 服務 |
| A3 | 機密請求不外送 | **已由 2026-10-03 各列取代:**不整封擋下;受規範的項目換成佔位符,其餘送出(第 16 頁)。定稿的路由又把其中一部分重新打開,見 A14 |
| A4 | 去識別化與還原進 MVP | 延續到簡報:佔位符、對照留本地、restore 是獨立呼叫(第 31 頁) |
| A5 | 模型跑在 GPU 沙盒,Llama 3.1 8B / Qwen3 8B | 沙盒請求移到 D51;模型選擇見 A13 |
| A6 | 雲端供應商 | 結案。服務不呼叫雲端模型 |
| A7 | 期中內容(MMLU/GSM8K 三配置、升級率圖、CLI demo) | 由簡報取代 |
| A8 | 使用情境 | 2026-09-21 完成:horizontal,主管信件的幕僚助理 |
| A9 | 分工 | 2026-09-25 完成;簡報沿用同樣五個領域(第 2 頁) |
| A10 | PR #3–#5 引出的六個敏感度閘門待決點 | 結案。為 vertical 情境寫的;(f) 由各等級洩漏率解決(第 19 頁) |
| B10、B15 | 向客戶走過第十節預設;確認算力 | 未決部分移到 D51 |
| B11 | 架構 v0.3.1 | 由 B48(v0.4)取代 |
| B12 | 沙盒建置 | 等 D51;硬體確定後重新界定 |
| B13、B14 | harness 骨架;MMLU 與 GSM8K 測試集 | 結案。評測改為 100 封信 benchmark |
| B14a | 合成企業資料 | 由 100 封信資料集取代(B46) |
| B33、B34 | Zhexuan 的信心與指標交接 | 併入 A11 |
| C16–C20 | 組員 Data & Architecture 提案的修正 | 結案。該提案描述轉向前的設計,已於 2026-10-23 從 `reference/team/` 移除 |
| D21–D23 | 第十節預設;範例文件;Qwen3 確認 | 結案。轉向前的問題 |
| D24 | 硬體 | 移到 D51 |
| D25 | Aarvin 的 API contract | 改由團隊撰寫(0.4.2,B40) |
| F28–F32 | 依轉向前工作流的研究清單 | 已交付的留在 `docs/research/`;其餘結案 |
| 9/27 團隊第 1–4 項 | 五級拆 id、六個標註欄位、不確定也遮並標記、整封還是分段 | 簡報以不同方式定案(決策紀錄 2026-10-03) |
| 9/27 延後事項 A | 狀態儲存的三個名稱 | 已定:每次 redaction 一份本地對照;context store 只放詞表與允許清單;沒有跨呼叫方的儲存 |

## 決策紀錄

決定了的事寫在這裡,避免之後重新討論。頁碼指 49 頁的定稿簡報。

| 日期 | 決策 | 理由 |
|---|---|---|
| 2026-09-03 | 客戶 kickoff 決議:混合架構且必須有本地模型;以通用 benchmark 評估並須展示與雲端可比的效能;增強本地模型在範圍內;不做 GUI;客戶提供雲端沙盒;初期每週開會 | 9 月 3 日客戶會議紀錄(`meetings/client/2026-09-03/`) |
| 2026-09-07 | 本地優先的混合架構,以信心分數升級、以敏感度把關(架構 v0.1) | 符合客戶提案 |
| 2026-09-08 | 採用組員提案的三配置評測、具名資料集、預設方案取代開放問題、MVP 與 stretch 切分(架構 v0.2) | 更具體,且符合客戶希望團隊給預設的期待 |
| 2026-09-08 | 時程依課程 15 週結構,不變 | W7 期中與假期由課程固定 |
| 2026-09-10 | 不在筆電跑 LLM。模型跑在模擬地端的雲端 GPU 沙盒上,筆電只做開發 | 筆電跑不動 8B 模型的 benchmark;客戶 9 月 3 日承諾提供沙盒;由我們控制的 VM 仍符合「本地」要求 |
| 2026-09-14 | 信心評分 MVP 排除口頭表態信心;訊號優先順序為 token 機率信心與 Semantic Entropy Probe,優先於自我一致性/完整語意熵 | 2026 年一項針對七個 3B–9B 開源模型的篩檢發現口頭表態信心會收斂(91.7% 的回覆自報信心 ≥95%,與答對答錯無關);見 `docs/research/zhexuan/2026-09-15/confidence-harness-design-zh.md` 與 `docs/research/zhexuan/2026-09-13/confidence-scoring-harness-report-en.md` |
| 2026-09-15 | 本地推論與評測 harness 都用 HF transformers(bitsandbytes 4-bit);不用 Ollama | harness 需要每個 token 的 logprobs 與 hidden states 給 Semantic Entropy Probe 用(PR #2);harness 與 router 共用一套堆疊,避免不同量化格式造成門檻值漂移 |
| 2026-09-15 | RAG 知識層列為 stretch goal,不進 MVP | 不在客戶需求與評判標準內;客戶資料尚未提供(A8);檢索接地已排除在信心 harness 外(PR #2)。W7 期中後再考慮 |
| 2026-09-15 | 資料敏感度分級納入 MVP:機密請求不論信心高低都不外送 | SOW 路由需求中 policy 的那一半;客戶核心動機是保護專有資料;router 裡一條規則 |
| 2026-09-15 | 去識別化與還原都進 MVP;還原做成每次請求的佔位符對照表;數值類用佔位符,假值為 stretch | 遮罩是客戶隱私參數的硬需求;沒有還原雲端回答不能用;對照表一天可做完 |
| 2026-09-21 | 金融問答 benchmark 採用 FinQA(MIT);FinanceBench(CC BY-NC)僅作課堂備用 | Karina 的研究(`docs/research/karina/2026-09-20/financial-data-sources-en.md`):對客戶零授權風險,且 FinQA 的標準答案含推理程式,數字與推理都能評分 |
| 2026-09-21 | 先做 horizontal:把脫敏能力做成獨立 HTTP 服務,服務對象是主管的幕僚助理;vertical 交易助理延後至時間允許 | Inderpal 與 Alex 認為兩條同時做的風險是兩邊都做不完,且 horizontal 的適用面更廣;Mark 接受此建議。9/21 客戶會議紀錄 Decisions/Aligned |
| 2026-09-25 | 工作流一對一重新對應到 Aarvin 的五個責任領域:評測與測試資料 Karina · 隱私研究 Yudi · 模型工作 Anmol · 服務工程 Zhexuan · 整合與協調 Mark。Mark 為單一對口窗口 | Aarvin 的 onboarding 信件定義了這五個領域、要求指定一位窗口,並說明角色確認後才會給完整規格。一對一對應是他能據以行動的形式。2026-09-25 團隊會議 |
| 2026-09-27 | 回覆 Aarvin 的硬體問題時只提個人筆電,不提 CMU Public Cloud Services | 與 B15 既有決定一致:CMU 這條路是內部備案,不向客戶提出。也讓沙盒問題(B15,2026-09-15 起未決)留在 Virtual Gold 那一邊 |
| 2026-09-28 | **只做英文。**現階段輸入語言與文件限英文 | 9/28 客戶會議紀錄 Decisions/Aligned |
| 2026-09-28 | **兩個測試階段。**Phase 1 在本地單獨測試 redaction 服務處理文字與文件;Phase 2 把 HTTP 服務和 Aarvin 的 VG08 整合,端到端測實際流程 | 9/28 客戶會議紀錄 Decisions/Aligned(Alex 與 Aarvin) |
| 2026-09-28 | **在有沙盒之前就先測試**,透過網路用雲端託管的開源模型,或用 Ollama 之類的本地工具 | 9/28 客戶會議紀錄;Inderpal、Alex、Aarvin。分工是方向,不是嚴格的邊界(Aarvin) |
| 2026-09-28 | **資源申請流程:**先和 Aarvin、Alex 確認需求,再通知指定的人取得 Inderpal 核准 | 9/28 客戶會議紀錄(Inderpal) |
| 2026-10-03 | **範圍。**本地的遮蔽與還原服務:一個 HTTP 服務,在雲端助理看到主管信件之前,把私密資料換成可還原的佔位符,並在回覆中還原。交付物:服務本身、敏感度分級與決策規則、100 封信評測 benchmark、監控 dashboard。限制:專案硬體、開源模型、不能對外連網、每個請求自動處理、11/30 期末報告前完成。服務本身從不呼叫雲端模型。取代混合路由設計(2026-09-07、2026-09-08)、三配置評測與 FinQA(2026-09-21)。定稿把輸入放寬為英文文字與文件,並加入路由規則(A14、A15) | 期中簡報第 3–5、8 頁;團隊共識,已與教授確認 |
| 2026-10-03 | **「模型判斷,程式決定」。**服務內六步:切段(正文、引用、簽名,附來源標記)→ 候選偵測(規則 + Presidio + 本地模型,依字元位置取聯集)→ 情境評估(模型判斷私密或公開並給原始分數,再校正)→ 程式決策(等級 × 分數對門檻)→ 佔位符(對照留本地)→ restore 為另一次刻意的呼叫。一個本地模型,兩個獨立 prompt:偵測與評估 | 第 13、22–31 頁 |
| 2026-10-03 | **三個等級,起始門檻。**High(身分證號、密碼與金鑰、銀行與卡號、健康、商業機密):分數 ≥ 0.2 即遮蔽。Medium(私人姓名、個人電話、個人 email、住址):≥ 0.5 遮蔽。Low(城市、日期、組織名稱、年齡、性別):單獨出現保留,組合出現遮蔽。等級依 NIST SP 800-122。門檻是起始值,之後調整。9/27 的五級拆 id、「模型能否判斷」欄、`health` 改 `medical`、`quantity` 類別都沒有進這張表。PR #8 在 `service/config/policy.yaml` 0.1.1 加了 `DEMOGRAPHIC`(High)、`NETWORK_ID` 與 `AMOUNT`(Medium),仍屬暫定 | 第 14 頁 |
| 2026-10-03 | **決策結果。**分數達到該等級門檻,或無法分類的 span:遮蔽。分數低於門檻,或單獨出現的 Low 項目:保留。沒有人工審查佇列(`PENDING_REVIEW`),也不整封擋下(`LOCAL_ONLY`):受規範的項目換成佔位符,信件其餘部分送雲端。取代 9/27「不確定也遮、標記 not sure」,並定案 9/27 第 4 項(整封還是分段)。定稿的路由規則又把整封的部分重新打開(A14) | 第 16、29 頁 |
| 2026-10-03 | **失效時保守處理。**模型呼叫失敗或輸出無法解析:保留規則與 Presidio 的候選、全部遮蔽不看門檻、回應標記 `degraded: true`。固定開啟,不是 opt-in。回覆中出現服務沒發過的佔位符時標記出來,不猜。稽核紀錄只記類別、分數、動作與 degraded 旗標,絕不記原文。定案 API contract 開放問題 8 | 第 22、26、30、32 頁 |
| 2026-10-03 | **信心分數。**每個 span 的模型原始分數用標註信件校正:依原始分數分組、算出實際為私密的比例,以該比例作為校正後分數 | 第 17 頁;Xiong et al. 2024 |
| 2026-10-03 | **本地模型透過 Ollama 執行,採用 Rescriber 的開源 prompt。**取代 2026-09-15(transformers、不用 Ollama)。那個決定是因為混合架構的 harness 需要 hidden states 做 Semantic Entropy Probe;redaction 服務的分數來自評估 prompt 加校正,已不需要 hidden states | 第 20 頁 |
| 2026-10-03 | **Context store 只放詞表與允許清單。**沒有持久、跨 session 或跨呼叫方的已知實體儲存。佔位符對照依每次 redaction 存在本地 mapping store。定案 9/27 延後事項 A | 第 23–24、26 頁 |
| 2026-10-03 | **評測。**100 封虛構主管信件,15 個業務領域、9 個產業、4 種主管角色,999 個標註項目、18 種類型。內建案例:情境案例、10 封乾淨信件、轉寄串、5 封攻擊信件、56 個不含單一名稱的商業機密(FACT 標籤)。每封信記:領域、產業、主管角色、任務、tags。每個 span 記:start、end、type、`must_mask`(true 或 false)。模型輸出:每封信一行 JSON,start 與 end 必填,type 與 score 選填。主要指標:各等級洩漏率。另追蹤:過度遮蔽、校正、每封信秒數。消融從 Rescriber 式 baseline 開始。取代 9/27 的三值正確答案與六欄位標註 | 第 19、39–41 頁 |
| 2026-10-03 | **我們的兩項貢獻。**不需要人逐項審查即可運作(Rescriber 要使用者確認每一項遮蔽)。一個標註好的信件 benchmark,加上顯示各部分貢獻的消融實驗 | 第 20 頁 |
| 2026-10-03 | **時程。**Phase 1:服務單獨測試,10 月下旬起。Phase 2:VG08 整合,11/2 起。10/12 那週秋假,不排工作。里程碑:10/11 contract 0.4.2 與服務骨架 · 11/1 端到端 pipeline 含失效路徑 · 11/8 dashboard 與壓測結果 · 11/15 VG08 整合、contract 凍結 · 11/22 程式凍結(軟凍結 11/18)· 11/30 期末報告。Dashboard 用 Prometheus 與 Grafana | 第 35、36、44、45 頁 |
| 2026-10-05 | **兩個 phase 的日期。**Phase 1 為 10/26–11/8:英文文字與文件、遮蔽與還原、benchmark 表現、degraded 備援。Phase 2 為 11/2–11/15:VG08 沙盒、完整流程、送雲端前的路由檢查、contract 凍結 | 定稿第 45 頁 |
| 2026-10-05 | **標準答案採用外部已標註好的資料集**(網路或 Kaggle),與產生出來的 benchmark 並用。兩者怎麼搭配見 A16 | 10/5 客戶會議紀錄 Decisions/Aligned。Aarvin 問產生出來的資料集怎麼信任;Mark 提出 Kaggle 的做法,Aarvin 支持 |
| 2026-10-05 | **現階段只用一個模型。**之後服務改善了,再透過 helper 或 middleware 支援換模型 | 10/5 客戶會議紀錄 Decisions/Aligned(Aarvin) |
| 2026-10-23 | **給客戶的原檔保留原名。**`docs/sow/Scope of Work -  20261005.docx` 與 `meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf` 是客戶實際收到的版本,不改名。10/3 的簡報草稿與 SOW v3 PDF 已移除 | Mark |
| 2026-10-25 | **10/26 客戶會議:**客戶審 Yudi 的 policy-0.1.3(他的提案);API v2 當作 Zhexuan 的提案展示;Anmol 的報告原樣給(他缺席),客戶頁面寫明是在託管 API 上跑、不是 VPC;Karina 的資料集在客戶確認分級表前維持 policy 0.1.1,並照她 README 的說法描述。報告順序:Yudi、Anmol,再來 Karina 與 Zhexuan | 2026-10-25 團隊會議(紀錄在 `meetings/team/2026-10-25/`) |
| 2026-10-26 | **API v2 合併進 main,預設關閉**(PR #10,`ade699b`)。在聽客戶意見前先合併,讓團隊展示同一個版本;要不要設為預設仍是 A18 | v1 不變;v2 需要 `VG_TOKEN_KEYS`;128 個測試通過;審查後續見 B73 |
