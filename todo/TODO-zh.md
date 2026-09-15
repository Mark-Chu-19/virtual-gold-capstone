# 團隊代辦事項

所有待決事項與待辦動作集中在這裡。決定會影響架構的,同一個 PR 一併更新 `docs/`。
**負責人**與**期限**在團隊會議上填。英文版:[`TODO.md`](TODO.md)。

## A. 本週(第 3 週)要做的決策

| # | 項目 | 說明 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|---|
| 1 | **工具選型**(除雲端 SDK 外已定案) | 客戶要的是路由機制與信心評分,沒有指定任何工具(9 月 3 日會議紀錄;SOW 第 2 節)。各元件與選擇,2026-09-15 定案:**本地推論:**HF transformers,T4 上 8B 4-bit(bitsandbytes);harness 需要每個 token 的 logprobs 與 hidden states 給 Semantic Entropy Probe 用(PR #2),Ollama、llama.cpp server、vLLM 都不暴露。**Router:**自己寫的 Python 模組(信心分數加敏感度規則),本地直接呼叫 transformers。**PII 閘道:**Presidio。**雲端呼叫:**A6 選定供應商的官方 SDK。不用:Ollama(沒有 hidden states);LiteLLM(包在 OpenAI 風格 API 外的 HTTP 轉接層,transformers 在程式內跑沒有東西可接;它的 hook 是呼叫前路由,不是依信心路由)。RouteLLM 是路由策略(任務複雜度分類),不是工具;架構第五節的 task heuristics 與第九節的 stretch goal 已涵蓋。 | Mark | W4 | [x] |
| 2 | **RAG 知識層** | **2026-09-15 已決定:不進 MVP,列為 stretch goal。**客戶沒有要求知識庫(9 月 3 日會議紀錄、SOW);檢索接地驗證在 SOW 只是可選的信心策略之一,PR #2 也已把它排除在 harness 外。使用情境定案、客戶提供資料(A8)之前沒有文件可以 index。W7 期中後視客戶資料與時間再考慮;F32 的研究(一頁摘要)照做,把選項留著。 | Mark | — | [x] |
| 3 | **資料敏感度分級是否納入 MVP** | 「機密永不外送」規則。路由層多一條規則,成本低,建議納入。 | | | [ ] |
| 4 | **去識別化與還原管線放 MVP 還是 stretch** | 還原這一步組員版沒有。數值類用佔位符還是假值一起定。 | | | [ ] |
| 5 | **本地模型與沙盒** | **2026-09-10 已決定:不在筆電跑 LLM。**模型跑在模擬地端的 GPU 沙盒上,筆電只做開發。待確認:客戶 9 月 3 日承諾的沙盒(供應商、GPU、連線方式、何時可用、費用誰出)、雲端 API 額度、量化位元。CMU 雲端(B15)為備案。 | Mark | W4 | [ ] |
| 6 | **雲端供應商:OpenAI 或 Anthropic** | 比較企業資料保留條款與價格。 | | | [ ] |
| 7 | **W7 期中要展示什麼** | 建議至少:純本地 vs 混合在 MMLU 子集與 GSM8K 上的準確率與升級率。 | | | [ ] |
| 8 | **使用情境 / 產業** | 客戶 9 月 3 日說可聚焦特定產業(例如金融或房地產),且定了情境才會提供資料。建議預設:金融服務類中小企業的文件工作流(問答、摘要、資訊擷取)。向客戶確認。 | | W4 | [ ] |
| 9 | **分工與研究** | 五條工作流,五人各認領一條:路由與整合、模型與推論、信心評分與評測 harness、安全與去識別化、RAG 與合成資料。每條工作流除了建置,還要先做該領域的應用論文與工具研究,清單見 F 區。文件與簡報各人寫自己那塊,Mark 彙整。 | | W4 | [ ] |

## B. 待辦動作

| # | 動作 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|
| 10 | 把架構文件第十節的預設方案送客戶確認;客戶不反對即照預設進行 | | | [ ] |
| 11 | A1 到 A4 決定、客戶回覆 B10 之後,架構文件升版 v0.3 | | | [ ] |
| 12 | 在 GPU 沙盒裝好兩個模型,推論堆疊依 A1 決定(預設 HF transformers,因為 harness 需要 logprobs 與 hidden states);筆電只放 client 程式與一個小型開發用模型 | | W4 | [ ] |
| 13 | 搭起評測 harness 骨架(三配置、六指標、日誌) | | W4 | [ ] |
| 14 | 準備 MMLU 子集與 GSM8K 測試集;生成第一批合成企業問題 | | W5 | [ ] |
| 15 | **向客戶確認算力與額度,CMU 雲端為備案。**問客戶:(a) 9 月 3 日承諾的雲端沙盒:供應商、GPU、連線方式、何時可用、費用誰出;(b) 雲端模型 API 額度或金鑰(OpenAI 或 Anthropic)與預算上限;(c) 沙盒能否同時承載模擬地端的 VM 與雲端呼叫。任一項沒有,就向 CMU Public Cloud Services 申請 GPU 主機:送諮詢表單並附 Randy 為教職員聯絡人,再寄信給 Randall Trzeciak 說明理由與成本估算(T4 等級 VM、100 GB、100 美元上限),副本 Randy。第 4 週要能用。 | Mark | W4 | [ ] |

## C. 組員 Data & Architecture 提案待修正

檔案:`reference/team/Virtual_Gold_Data_Architecture_Proposal_1.docx`

| # | 修正 | 完成 |
|---|---|---|
| 16 | 「Llama 3.3 8B」改為 Llama 3.1 8B(Llama 3.3 只有 70B) | [ ] |
| 17 | 「Qwen3 7B」改為 Qwen3 8B(7B 是 Qwen2.5) | [ ] |
| 18 | 圖:「高信心直接回覆」的箭頭不應經過 PII 遮罩閘道 | [ ] |
| 19 | 模型數據改引 Meta 與 Qwen 官方 model card,框架改引 NIST AI RMF 原文,不引部落格 | [ ] |
| 20 | 時程對齊課程:W7 期中、W8 秋假、W14 感恩節 | [ ] |

## D. 等客戶回覆

| # | 項目 | 詢問日期 | 回覆 |
|---|---|---|---|
| 21 | 確認或修改第十節的八項預設方案 | | |
| 22 | 提案中提到的「企業與小企業資料」有沒有範例文件或格式 | | |
| 23 | 國際開源模型(Qwen3)可否納入評估 | | |

## E. Scope of Work 簽署前的修改

原稿:`docs/Scope of Work.docx`(日期 2026 年 9 月 15 日)。**修改版:`docs/Scope of Work v2.docx`,改動處為紅字。**其餘內容與架構文件一致。

| # | 修改 | 完成 |
|---|---|---|
| 24 | 第 6 節假設第 3 條:「開發與實驗主要在學生筆電、桌機或其他核准的沙盒環境進行」改為「開發與實驗主要在客戶提供的雲端沙盒環境進行,該環境設定為模擬企業地端部署;學生筆電只用於開發」。SOW 中不提 CMU 資源。 | [x] |
| 25 | 第 6 節新增依賴:「客戶將提供雲端沙盒環境供測試使用,如 2026 年 9 月 3 日會議所討論」。 | [x] |
| 26 | 第 6 節費用歸屬:v2 已寫入紅字段落,寫明由客戶負擔,金額留 $[X] 佔位;B15 有答案後填入金額並刪掉「待客戶確認」字樣。SOW 中不提 CMU 備案。 | [ ] |
| 27 | 第 5 節 Phase 1 末尾加上「並開始早期原型驗證架構假設」(Alex 於 9 月 3 日提出)。 | [x] |

## F. 研究清單(按分工)

每條工作流第 4 週的研究交付:一頁摘要,說明「這個工具或方法能不能用在我們的架構、怎麼用、限制是什麼」,附來源連結。先讀官方文件與論文摘要,不用逐字讀完。

| # | 工作流 | 負責人 | 要研究的東西 | 要回答的問題 |
|---|---|---|---|---|
| 28 | 路由與整合 | | LiteLLM 官方文件:custom callbacks、pre-call hooks、guardrails、fallback 設定。RouteLLM 論文(Ong et al. 2024, arXiv:2406.18665)。RouterBench(Hu et al. 2024, arXiv:2403.12031)。FrugalGPT 的 LLM cascade(Chen et al. 2023, arXiv:2305.05176)。Hybrid LLM 的品質感知路由(Ding et al. 2024, arXiv:2404.14618)。AutoMix 的自我驗證路由(Madaan et al. 2023, arXiv:2310.12963)。 | LiteLLM 能不能掛自訂路由政策與去識別化鉤子,還是只當轉接頭?RouteLLM 是「看問題」的事前路由,和「看回答」的事後信心評分要怎麼在 harness 裡分開比較?FrugalGPT 的 cascade 和我們的設計差在哪? |
| 29 | 模型與推論 | | Ollama 的 API 是否回傳 logprobs,目前狀態與 issue。llama.cpp server 模式的 logprobs 支援。vLLM 的硬體需求。GGUF 量化等級(Q4_K_M、Q8_0)對準確率與速度的影響。Llama 3.1 8B 與 Qwen3 8B 的官方 model card、授權條款。 | 要拿 logprobs 該用 Ollama、llama.cpp 還是 vLLM?T4 上 8B 4-bit 的每秒 token 數大約多少?Qwen3 的授權對企業使用有沒有限制? |
| 30 | 信心評分與評測 harness | | 自我一致性(Wang et al. 2022, arXiv:2203.11171)。語意熵(Kuhn et al. 2023, arXiv:2302.09664;Farquhar et al. 2024, Nature)。模型自知(Kadavath et al. 2022, arXiv:2207.05221)。SelfCheckGPT(Manakul et al. 2023, arXiv:2303.08896)。口頭信心的可靠度(Xiong et al. 2023, arXiv:2306.13063)。校準指標:ECE、AUROC、升級率對正確率曲線。MMLU、GSM8K、TruthfulQA、HaluEval 的資料格式與評分方式。 | 哪些信心訊號在 8B 模型上實際有效?每種訊號多花多少推論次數?harness 要怎麼設計才能一次跑三配置並輸出六指標? |
| 31 | 安全與去識別化 | | Presidio 的 recognizers、自訂實體、evaluation 模組。隱私意識委派 PAPILLON(Siyan et al. 2024, arXiv:2410.17127)。OWASP Top 10 for LLM Applications。間接 prompt injection(Greshake et al. 2023, arXiv:2302.12173)。NIST AI RMF 1.0 與 Generative AI Profile(NIST AI 600-1)。 | Presidio 對合成企業文件的漏檢率大概多少?佔位符送雲端再還原,有沒有現成做法或論文?我們的風險評估要對到 NIST 的哪些條目? |
| 32 | RAG 與合成資料 | | Chroma、pgvector 的取捨。切塊策略與 embedding 模型選擇(本地可跑的,例如 bge、nomic-embed)。檢索接地度與忠實度評估(例如 RAGAS 的 faithfulness)。用客服工單與 B2B 資料集當種子生成合成企業文件與問答的方法。 | 最簡版 RAG 一天內做得完的範圍是什麼?接地度分數怎麼算才能當信心訊號?合成資料要生多少、怎麼標敏感等級? |

## 決策紀錄

決定了的事寫在這裡,避免之後重新討論。

| 日期 | 決策 | 理由 |
|---|---|---|
| 2026-09-03 | 客戶 kickoff 決議:混合架構且必須有本地模型;以通用 benchmark 評估並須展示與雲端可比的效能;增強本地模型在範圍內;不做 GUI;客戶提供雲端沙盒;初期每週開會 | 9 月 3 日客戶會議紀錄(reference/team/Meeting Notes/2026-09-03) |
| 2026-09-07 | 本地優先的混合架構,以信心分數升級、以敏感度把關(架構 v0.1) | 符合客戶提案 |
| 2026-09-08 | 採用組員提案的三配置評測、具名資料集、預設方案取代開放問題、MVP 與 stretch 切分(架構 v0.2) | 更具體,且符合客戶希望團隊給預設的期待 |
| 2026-09-08 | 時程依課程 15 週結構,不變 | W7 期中與假期由課程固定 |
| 2026-09-10 | 不在筆電跑 LLM。模型跑在模擬地端的雲端 GPU 沙盒上,筆電只做開發 | 筆電跑不動 8B 模型的 benchmark;客戶 9 月 3 日承諾提供沙盒;由我們控制的 VM 仍符合「本地」要求 |
| 2026-09-15 | 本地推論與評測 harness 都用 HF transformers(bitsandbytes 4-bit);不用 Ollama | harness 需要每個 token 的 logprobs 與 hidden states 給 Semantic Entropy Probe 用(PR #2);harness 與 router 共用一套堆疊,避免不同量化格式造成門檻值漂移 |
| 2026-09-15 | RAG 知識層列為 stretch goal,不進 MVP | 不在客戶需求與評判標準內;客戶資料尚未提供(A8);檢索接地已排除在信心 harness 外(PR #2)。W7 期中後再考慮 |
