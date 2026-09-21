# 團隊代辦事項

所有待決事項與待辦動作集中在這裡。決定會影響架構的,同一個 PR 一併更新 `docs/`。
**負責人**與**期限**在團隊會議上填。英文版:[`TODO.md`](TODO.md)。

會議時間(美東,皆每週):客戶 週一 18:00–19:00 · 教授 週二 17:00–18:20 · 團隊 週五 15:30–16:30。

## A. 決策(A1 到 A4 已於 2026-09-15 定案;A8 待客戶確認;A9 負責人 2026-09-18 已定)

| # | 項目 | 說明 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|---|
| 1 | **工具選型**(除雲端 SDK 外已定案) | 客戶要的是路由機制與信心評分,沒有指定任何工具(9 月 3 日會議紀錄;SOW 第 2 節)。各元件與選擇,2026-09-15 定案:**本地推論:**HF transformers,T4 上 8B 4-bit(bitsandbytes);harness 需要每個 token 的 logprobs 與 hidden states 給 Semantic Entropy Probe 用(PR #2),Ollama、llama.cpp server、vLLM 都不暴露。**Router:**自己寫的 Python 模組(信心分數加敏感度規則),本地直接呼叫 transformers。**PII 閘道:**Presidio。**雲端呼叫:**A6 選定供應商的官方 SDK。不用:Ollama(沒有 hidden states);LiteLLM(包在 OpenAI 風格 API 外的 HTTP 轉接層,transformers 在程式內跑沒有東西可接;它的 hook 是呼叫前路由,不是依信心路由)。RouteLLM 是路由策略(任務複雜度分類),不是工具;架構第五節的 task heuristics 與第九節的 stretch goal 已涵蓋。 | Mark | W4 | [x] |
| 2 | **RAG 知識層** | **2026-09-15 已決定:不進 MVP,列為 stretch goal。**客戶沒有要求知識庫(9 月 3 日會議紀錄、SOW);檢索接地驗證在 SOW 只是可選的信心策略之一,PR #2 也已把它排除在 harness 外。使用情境定案、客戶提供資料(A8)之前沒有文件可以 index。W7 期中後視客戶資料與時間再考慮;F32 的研究(一頁摘要)照做,把選項留著。 | Mark | — | [x] |
| 3 | **資料敏感度分級** | **2026-09-15 已決定:納入 MVP。**「機密永不外送」規則就是 SOW「confidence-based or policy-based request routing」裡 policy 那一半,直接落實客戶的核心需求(保護專有資料,9 月 3 日)。在自寫的 router(A1)裡加一條規則:標記為機密的請求不論信心高低都留在本地。分級先用架構第十節的預設(public / internal / confidential),客戶回覆 B10 後再調。 | Mark | — | [x] |
| 4 | **去識別化與還原管線** | **2026-09-15 已決定:兩段都進 MVP,做最簡版。**去識別化(送雲端前用 Presidio 遮罩)是客戶隱私參數的硬需求。還原做成每次請求一張對照表:出去時記「佔位符對應原值」,回來時字串替換;沒有這步雲端回答裡仍是佔位符,CLI demo 不能用。數值類:MVP 用佔位符,格式保留的假值維持 stretch goal(架構第十節預設)。 | Mark | — | [x] |
| 5 | **本地模型與沙盒** | **2026-09-10 已決定:不在筆電跑 LLM。**模型跑在模擬地端的 GPU 沙盒上,筆電只做開發。模型:Llama 3.1 8B 為主、Qwen3 8B 為輔。推論:HF transformers 加 bitsandbytes 4-bit(A1),量化方式已定,GGUF 等級不再適用。待確認:沙盒本身與雲端額度,統一記在 **B15**(這裡不重複)。向客戶問沙盒規格時可說明:T4(16 GB)跑得動 8B 加 hidden states 輸出,但 k 次採樣集成(PR #2 Config C)記憶體會吃緊;A10G 等級(24 GB)可以從容跑(架構第十節)。 | Mark | W4 | [ ] |
| 6 | **雲端供應商:OpenAI 或 Anthropic** | **2026-09-15 定規則:跟著 B15 走。**客戶提供哪家的額度或企業帳號就用哪家;客戶沒有偏好時預設 Anthropic。客戶沒有指定供應商(9 月 3 日會議紀錄、SOW);兩家都有企業版不拿資料訓練的承諾,價格同一級,而且 harness 在雲端那側只需要一個 `generate(query)` 呼叫(信心分數算的是本地模型,雲端 API 沒有 logprobs 無妨;TruthfulQA 只用 MC1/MC2 評分,PR #2)。B15 有答案時這條隨之定案。 | Mark | W4 | [ ] |
| 7 | **W7 期中要展示什麼** | **2026-09-15 定案。**(1)三配置 local-only / hybrid / cloud-only 在 MMLU 子集與 GSM8K 上(金融資料集:FinQA 樣本,2026-09-21 決定):準確率、升級率、每題成本、延遲(PII 洩漏率與 prompt injection 抵抗力 W9 到 W11 再做)。每題都送雲端一次並快取,cloud-only 從同一次跑就出來(PR #2)。(2)信心訊號只用 token logprob(PR #2 variant A);SEP 與採樣集成 W9 到 W11。(3)一張圖:升級率對準確率曲線,直接回答「升級多少才夠」。(4)CLI demo:一個含 PII 的請求走完遮罩、升級、還原(A3、A4)。投影片 W6 完成。 | Mark | W6 | [ ] |
| 8 | **使用情境 / 產業** | **2026-09-18 團隊提案(尚未定案):**對客戶的「垂直還是橫向」回答「兩個都要」,以 Inderpal 提的金融交易助理為垂直(公開申報文件與市場資料可上雲;持倉與策略留本地),淨化閘道為橫向能力。實例見 `meetings/team/2026-09-18/`。**2026-09-21 客戶會議上確認**;客戶可能選垂直、橫向或兩者。Karina 的合成資料(PR #3–#5)建立在此提案上,客戶改方向則跟著調整。客戶確認後才進決策紀錄。 | Mark | 2026-09-21 | [ ] |
| 9 | **分工與研究** | **2026-09-15 團隊會議上認領負責人。**五條工作流,一人一條,範圍依 A1 到 A8 更新:(1)**路由與整合**:自寫 Python router(信心門檻加「機密留本地」規則,A3)、雲端 SDK 呼叫(A6)、CLI 進入點。(2)**模型與推論**:HF transformers 加 bitsandbytes 4-bit 跑 Llama 3.1 8B 與 Qwen3 8B、沙盒建置(B12)、沙盒 GPU 上的吞吐量與記憶體。(3)**信心評分與評測 harness**:負責人 Zhexuan Ye(研究報告與設計文件已交,PR #2);採樣核心、benchmark 載入、指標、期中 pilot。(4)**安全與去識別化**:Presidio 閘道、還原對照表(A4)、W9 到 W11 的 PII 洩漏率與 prompt injection 評測。(5)**合成資料(RAG 延至 stretch,A2)**:demo 與 B14 用的合成企業問題與文件、F32 一頁摘要;W7 前負擔最輕,此人同時支援(3)或期中投影片。每條工作流先做 F 區的一頁研究摘要。文件與簡報各人寫自己那塊,Mark 彙整。 | Mark | — | [x] |

## B. 待辦動作

| # | 動作 | 負責人 | 期限 | 完成 |
|---|---|---|---|---|
| 10 | **2026-09-15 客戶會議上當面走過架構文件第十節的預設方案**,不另外寄。要問三項:雲端供應商(A6:客戶提供哪家額度就用哪家,否則 Anthropic)、費用誰出(B15)、使用情境 / 產業(A8)。其餘七項告知即可:敏感度三級、自動升級並記錄、Qwen3 為輔並做供應鏈檢查、T4 等級沙盒跑 8B 4-bit(現改用 HF transformers)、數值用佔位符、NIST AI RMF、公開資料集加合成資料。客戶不反對即照預設進行;會後把回覆填進 D21 到 D23,並納入 v0.3(B11)。 | Mark | 2026-09-15 | [ ] |
| 11 | **架構文件 v0.3 已於 2026-09-15 發布**(檔名改為 `architecture-v0.3-*`):第三、四節 RAG 標為 stretch,第七節期中目標,第九節時程與 MVP 清單,第十節雲端供應商列,第十一、十二節重寫,標題與頁尾。**v0.3.1 待 PR #2 merge 後補:**第五節加口頭表態信心的排除與訊號優先順序(token logprob → SEP → 採樣集成);第七節加信心指標子表。四種格式一起改。 | Mark | PR #2 之後 | [ ] |
| 12 | **沙盒建置**(等 B15)。裝 Python、PyTorch 加 CUDA、transformers、bitsandbytes、accelerate;下載 Llama 3.1 8B(先在 Hugging Face 接受 Meta 授權)與 Qwen3 8B。驗收:一個 smoke test,載入 8B 4-bit,跑一次 `generate` 回傳文字、每個 token 的 logprobs 與 hidden states,並記錄 token/s 與 GPU 記憶體峰值;這個測試就是 harness 採樣核心的第一步,交給工作流(3)。筆電只放 client 程式與一個小型開發用模型(Qwen3 0.6B 或 Llama 3.2 1B),讓程式在本機跑通再上沙盒。| Anmol | W4 | [ ] |
| 13 | **搭起評測 harness 骨架**,依 PR #2。跑架構第七節的三配置(local-only / hybrid / cloud-only),記錄其六個系統指標(準確率、延遲、每題成本、升級率、PII 洩漏率、prompt injection 抵抗力),並為每種信心訊號變體記錄信心子表(ECE、AUROC、AURC、升級率對準確率)。每題送雲端一次並快取,cloud-only 從同一次跑產出。W4 交付三個分支:`feat/harness-sampling-core`(共用 k 次採樣迴圈,建在 B12 的 smoke test 上)、`eval/benchmark-loaders`(先做 MMLU 子集與 GSM8K,對接 B14)、`eval/calibration-metrics`(用合成資料做單元測試;不需要 GPU,筆電可先做)。訊號變體 A 與期中 pilot 在 W5 到 W6。 | Zhexuan | W4 | [ ] |
| 14 | **Benchmark 測試集**(與 B13 的 loaders 是同一件事)。MMLU:每科固定題數(例如 20 × 57 約 1,140 題)、固定 random seed,另切一個 dev split 給門檻校準用(PR #2:門檻不在 test set 上調)。GSM8K:官方 test split(1,319 題),dev 從 train 切。 | Zhexuan | W4 | [ ] |
| 14a | **合成企業資料**(工作流 5)。兩批:(i)期中 CLI demo 用的含 PII 請求十幾條(A7),W5 要有,PR #4 已草擬(開著,形式討論中);(ii)W9 到 W11 的 PII 洩漏率與 prompt injection 測試用的企業文件:W5 先定格式與生成 prompt,W9 前生足量。產業背景依 A8。客戶給的範例(D22)只當格式樣板,不進資料集;全程不用真實資料(架構第十節)。 | Karina | W5 | [ ] |
| 15 | **2026-09-15 客戶會議上確認算力與額度。**要問:(a)9 月 3 日承諾的雲端沙盒:供應商、GPU(T4 16 GB 可用;A10G 24 GB 可讓 k 次採樣的信心集成從容跑,A5)、SSH 之類的直接存取(模型用 transformers 在機器上跑,不是透過 API)、費用誰出;(b)雲端模型 API 額度或金鑰與預算上限,以及是否已有 OpenAI 或 Anthropic 企業帳號(A6 跟著走);(c)沙盒何時可用、能否用到學期末。**僅供內部的備案,會議上不主動提**(SOW v2 與架構第十節已不提):向 CMU Public Cloud Services 申請 GPU 主機:送諮詢表單並附 Randy 為教職員聯絡人,再寄信給 Randall Trzeciak 說明理由與成本估算(T4 等級 VM、100 GB、100 美元上限),副本 Randy。第 4 週要能用。 | Mark | 2026-09-15 | [ ] |

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
| 21 | 確認或修改架構第十節的十項預設方案(會議上當面走過,B10) | 2026-09-15 | |
| 22 | 提案中提到的「企業與小企業資料」,依 A8 選定的產業,有沒有範例文件或格式。只要格式與範例,不要真實資料(B14a) | 2026-09-15 | |
| 23 | 確認 Qwen3 8B 為輔並做供應鏈檢查(架構第十節第 4 項)。客戶 9 月 3 日已說國際模型安全審查較嚴,並要求架構模組化方便換模型;這是確認,不是新問題 | 2026-09-15 | |

## E. Scope of Work 簽署前

`docs/sow/Scope of Work v2.docx`(改動處為紅字)除費用金額外已完成。已完成的修改(沙盒假設、沙盒依賴、Phase 1 原型句)留在 git 紀錄,不再列在這裡。

| # | 修改 | 完成 |
|---|---|---|
| 26 | 第 6 節費用歸屬:紅字段落寫明由客戶負擔,金額留 $[X] 佔位。2026-09-15 會議上問到金額(B15)後填入、刪掉「待客戶確認」字樣,再簽署。SOW 中不提 CMU 備案。 | [ ] |

## F. 研究清單(按分工)

每條工作流第 4 週的研究交付:一頁摘要,說明「這個工具或方法能不能用在我們的架構、怎麼用、限制是什麼」,附來源連結。先讀官方文件與論文摘要,不用逐字讀完。

| # | 工作流 | 負責人 | 要研究的東西 | 要回答的問題 |
|---|---|---|---|---|
| 28 | 路由與整合 | Mark | 門檻式升級與 cascade 規則:FrugalGPT(Chen et al. 2023, arXiv:2305.05176)、Hybrid LLM 的品質感知路由(Ding et al. 2024, arXiv:2404.14618)、AutoMix 的自我驗證路由(Madaan et al. 2023, arXiv:2310.12963)。僅供 stretch 對照:RouteLLM(Ong et al. 2024, arXiv:2406.18665)、RouterBench(Hu et al. 2024, arXiv:2403.12031)。LiteLLM 已拿掉(A1)。 | cascade 論文怎麼設定與調整升級規則,哪些可以搬到我們信心分數的單一門檻上?「機密留本地」規則(A3)怎麼和信心門檻疊在同一個 router 裡?一個本地呼叫 transformers、雲端呼叫 SDK 的最簡 Python router 長什麼樣? |
| 29 | 模型與推論 | Anmol | T4 上的 HF transformers 加 bitsandbytes:Llama 3.1 8B 與 Qwen3 8B 的 4-bit 對 8-bit 準確率與速度;`generate` 開 `output_scores` 與 `output_hidden_states`(harness 需要的,PR #2);多樣本生成(`num_return_sequences=k`)的記憶體與吞吐量;accelerate 的 device-map 選項。兩個模型的官方 model card 與授權條款。 | T4 上一個 8B 模型 4-bit 的 token/s 與記憶體峰值,單樣本與 k=5 各多少?8-bit 加 hidden states 輸出放得下嗎?SEP 論文用哪一層的 hidden state?Qwen3 的授權對企業使用有沒有限制? |
| 30 | 信心評分與評測 harness | Zhexuan | **2026-09-13/14 已交付:**文獻回顧(`docs/research/confidence-scoring-harness-report-en.md`,中文譯本 `-zh.md`)與設計文件(`docs/research/confidence-harness-design-zh.md`,2026-09-21 已 merge)。涵蓋自我一致性、語意熵與 SEP、Kadavath et al.、SelfCheckGPT、Xiong et al.、校準指標,以及 MMLU、GSM8K、TruthfulQA、HaluEval 的評分方式。 | 已回答:哪些訊號在 8B 有效(token logprob 與 SEP;口頭表態信心排除)、每種多花多少成本、harness 怎麼一次產出架構第七節的三配置與六個系統指標加信心子表。 |
| 31 | 安全與去識別化 | Yudi | **2026-09-19 已交付:**`docs/research/security-deidentification-report-en.docx`(17 篇文獻:敏感 ≠ PII、雙分數政策取代二元閘門、三種淨化策略、四層分級、多輪洩漏測試);客戶簡報在 `meetings/client/2026-09-21/`。原清單:Presidio 的 recognizers、自訂實體、evaluation 模組。隱私意識委派 PAPILLON(Siyan et al. 2024, arXiv:2410.17127)。OWASP Top 10 for LLM Applications。間接 prompt injection(Greshake et al. 2023, arXiv:2302.12173)。NIST AI RMF 1.0 與 Generative AI Profile(NIST AI 600-1)。還原:每次請求的佔位符對照表(A4),現有工具(例如 Presidio anonymizer 的 operators)怎麼處理反向那步。 | Presidio 對合成企業文件的漏檢率大概多少?雲端回覆後把佔位符換回原值最簡單可靠的做法是什麼,哪裡會壞(佔位符被改寫或換句)?我們的風險評估要對到 NIST 的哪些條目? |
| 32 | 合成資料(RAG 為 stretch) | Karina | **2026-09-20 已交付:**`docs/research/financial-data-sources-en.md`(採用 FinQA,決策紀錄 2026-09-21)。其餘:用 LLM 生成合成企業文件與問答的方法,以客服工單與 B2B 資料集為種子(架構第七節);怎麼刻意植入 PII 與敏感等級標籤,讓安全測試有 ground truth(B14a)。Stretch,只做一頁:Chroma 對 pgvector、切塊、本地可跑的 embedding 模型(bge、nomic-embed)、RAGAS faithfulness 當接地訊號(A2)。 | demo 與 W9 到 W11 的安全測試各需要多少合成資料,敏感等級怎麼標?什麼 prompt 與檢查能讓生成的 PII 逼真但是假的?Stretch:一天內做得完的最簡 RAG 範圍是什麼? |

## 決策紀錄

決定了的事寫在這裡,避免之後重新討論。

| 日期 | 決策 | 理由 |
|---|---|---|
| 2026-09-03 | 客戶 kickoff 決議:混合架構且必須有本地模型;以通用 benchmark 評估並須展示與雲端可比的效能;增強本地模型在範圍內;不做 GUI;客戶提供雲端沙盒;初期每週開會 | 9 月 3 日客戶會議紀錄(`meetings/client/2026-09-03/`) |
| 2026-09-07 | 本地優先的混合架構,以信心分數升級、以敏感度把關(架構 v0.1) | 符合客戶提案 |
| 2026-09-08 | 採用組員提案的三配置評測、具名資料集、預設方案取代開放問題、MVP 與 stretch 切分(架構 v0.2) | 更具體,且符合客戶希望團隊給預設的期待 |
| 2026-09-08 | 時程依課程 15 週結構,不變 | W7 期中與假期由課程固定 |
| 2026-09-10 | 不在筆電跑 LLM。模型跑在模擬地端的雲端 GPU 沙盒上,筆電只做開發 | 筆電跑不動 8B 模型的 benchmark;客戶 9 月 3 日承諾提供沙盒;由我們控制的 VM 仍符合「本地」要求 |
| 2026-09-14 | 信心評分 MVP 排除口頭表態信心;訊號優先順序為 token 機率信心與 Semantic Entropy Probe,優先於自我一致性/完整語意熵 | 2026 年一項針對七個 3B–9B 開源模型的篩檢發現口頭表態信心會收斂(91.7% 的回覆自報信心 ≥95%,與答對答錯無關);見 `docs/research/confidence-harness-design-zh.md` 與 `docs/research/confidence-scoring-harness-report-en.md` |
| 2026-09-15 | 本地推論與評測 harness 都用 HF transformers(bitsandbytes 4-bit);不用 Ollama | harness 需要每個 token 的 logprobs 與 hidden states 給 Semantic Entropy Probe 用(PR #2);harness 與 router 共用一套堆疊,避免不同量化格式造成門檻值漂移 |
| 2026-09-15 | RAG 知識層列為 stretch goal,不進 MVP | 不在客戶需求與評判標準內;客戶資料尚未提供(A8);檢索接地已排除在信心 harness 外(PR #2)。W7 期中後再考慮 |
| 2026-09-15 | 資料敏感度分級納入 MVP:機密請求不論信心高低都不外送 | SOW 路由需求中 policy 的那一半;客戶核心動機是保護專有資料;router 裡一條規則 |
| 2026-09-15 | 去識別化與還原都進 MVP;還原做成每次請求的佔位符對照表;數值類用佔位符,假值為 stretch | 遮罩是客戶隱私參數的硬需求;沒有還原雲端回答不能用;對照表一天可做完 |
| 2026-09-21 | 金融問答 benchmark 採用 FinQA(MIT);FinanceBench(CC BY-NC)僅作課堂備用 | Karina 的研究(`docs/research/financial-data-sources-en.md`):對客戶零授權風險,且 FinQA 的標準答案含推理程式,數字與推理都能評分 |
