# 信心評分與評測 Harness — 設計文件

**Capstone · Virtual Gold Inc · 第 3 週 · 信心評分工作項目**

延伸 [architecture-v0.3-zh.md](architecture-v0.3-zh.md) 第五節(信心評分)與第七節(評測設計與資料集),補上 8B 級文獻回顧與可執行的 harness 設計。本文件是下方第六節所列 `feat/harness-*`、`eval/*` 分支的依據。

| 版本 | 日期 | 狀態 | 作者 |
|---|---|---|---|
| v0.1 | 2026-09-14 | 草稿,待團隊審閱 | Zhexuan Ye |
| v0.2 | 2026-09-15 | 依 Mark 的審閱意見修訂:補上 SEP 訊號變體的推論堆疊前提、六指標敘述對齊架構第七節、A/B/C 改稱「訊號變體」、拆出期中 pilot、TruthfulQA 範圍收斂 | Zhexuan Ye |

---

## 一、為什麼要有這份文件

架構 v0.3 第五節列出五種候選信心策略(token 機率、自我一致性、驗證模型、檢索接地度、任務啟發式),並建議 MVP 先做 token 機率加任務啟發式,但沒有引用特定規模下的實證資料。本文件用在我們目標規模(Llama 3.1 8B / Qwen3 8B)附近做過測試的文獻收斂這個建議,並把架構 v0.3 第七節的三配置評測設計,落成一套可執行的 harness。

本文件要回答三個問題:

1. 哪些信心訊號在 8B 規模上有直接(非外推)的實證支持?
2. 每種訊號多花幾次推論,讓 harness 同時回報準確度增益與運算成本?
3. 怎麼從一次採樣就得到架構 v0.3 第七節的三種系統配置,外加每個訊號變體的信心指標,而不是分開跑好幾次評測?

## 二、8B 規模下的信心訊號總覽

| 訊號 | 每題額外本地生成次數 | 額外輔助模型呼叫 | 一次性成本 | 8B 規模實證 |
|---|---|---|---|---|
| Token 機率 / softmax | 0 | 0 | 無 | 直接:小模型 AUROC 0.71–0.87 |
| 口頭表態信心(同一次生成) | 0 | 0 | 無 | 直接:8B 上**已失效**——收斂成近乎恆定的「非常有信心」 |
| 口頭表態信心(追問一次) | 1 | 0 | 無 | 無 8B 直接測試;由能力趨勢推論 |
| Semantic Entropy Probe(SEP) | 推論時 0\* | 0 | 一次性探針訓練 | 最小測試模型:7B(Llama-2-7B、Mistral-7B);無 8B 專屬消融實驗 |
| P(True) / P(IK) | ≥1 | 0 | 無 | 無 8B 測試(只有 800M/3B/12B/52B);規模趨勢顯示 OOD 泛化更差 |
| 自我一致性 | k−1(約 5–10 個樣本即飽和) | 0 | 無 | 無 8B 測試(僅 20B–540B);小模型增益較小 |
| 完整語意熵 | M−1(原論文 M=10) | O(M²) 蘊含檢查 | 無 | 直接:LLaMA-2-Chat 7B/13B,AUROC 0.79 |
| SelfCheckGPT(n-gram / BERTScore) | N−1 | 0(n-gram)/ 輕量(BERTScore) | 無 | 直接:Llama-2-7B/13B 測試 |
| SelfCheckGPT(NLI / prompt-based) | N−1 | N 次呼叫 | 無 | 直接:7B/13B 測試,最佳結果需 GPT-3.5 當裁判 |

完整文獻回顧、逐篇但書與引用出處:`reference/team/confidence_scoring_harness_report_concise_en.md`(Zhexuan Ye,2026-09-13)。

\* **SEP 那一列「推論時 0」有一個沒寫出來的前提:推論堆疊要能吐出 hidden states。**Ollama 和 llama.cpp server 完全不暴露 hidden states;vLLM 有 logprobs,但沒有自訂 hook 就拿不到 hidden states。SEP 直接讀 hidden states(OATML 的 SEP 參考實作也是這樣做),所以訊號變體 B 只有在 harness 直接用 HF transformers 跑模型時才做得出來。架構 v0.3 第九節 / TODO A1 已因為這個原因把本地推論堆疊定為 HF transformers 加 bitsandbytes 4-bit——第三節說明這對排程的影響。

**沿用該回顧的設計限制:**2026 年一項預註冊的心理計量篩檢,直接測試七個 3B–9B 開源指令模型(含 Llama-3-8B-Instruct、Llama-3.1-8B-Instruct),發現口頭表態信心會收斂——91.7% 的回覆自報信心 ≥95%,與答對答錯無關;其中兩個模型在 500 多次試驗中從未給過低信心評分。架構 v0.3 第五節的五種策略裡沒有一項是口頭表態信心,所以這個發現是替未來的策略選擇加一條限制,不是推翻表裡已經寫的東西。**我們不用口頭表態信心做升級決策。**第五節的五種策略原則上都還是候選;下面第三節說明本文件實際納入 MVP 範圍的是哪三種訊號,以及驗證模型、檢索接地度這兩項為什麼要等。

## 三、Harness 優先實作順序

依 8B 規模的實證強度與邊際成本排序,最貼近架構 v0.3 第九節 MVP 承諾(「自我一致性或 token logprob 作為基準線訊號」):

1. **Token 機率信心(訊號變體 A)**——邊際成本為零,有貼近 8B 規模的直接實證,且不依賴 hidden states。優先實作;這是 W4–W7 期中範圍內唯一的訊號(TODO A7)。
2. **Semantic Entropy Probe(訊號變體 B)**——訓練完成後推論時邊際成本為零,是回顧中成本/準確度組合最佳的訊號。但需要兩樣期中來不及做的東西:一次性的標註校準流程(離線跑一次完整語意熵,產生探針的訓練目標),以及第二節註腳提到的 HF transformers 推論堆疊。第二優先,排進 W9–W11 擴充階段,因為 TODO A1 已經把它需要的堆疊定案。
3. **自我一致性 / 完整語意熵 ensemble(訊號變體 C)**——成本最高但實證最充分的上限參照。第三順位實作,同樣排在 W9–W11,作為「k 倍運算是否值得」的參照基準,而非預設出貨方案。

架構 v0.3 第五節的檢索接地度與驗證模型策略不在本文件範圍內;前者取決於 RAG 決策,已定案為 stretch goal(架構 v0.3 第十一節第 2 項 / 2026-09-15 決策日誌)。任務啟發式(例如「多步推理預設升級」)屬於 router 政策,不是信心訊號——不在本文件範圍是因為這個原因,不是因為本文件的任何發現。它可以疊加在上面任何一個訊號變體之上,屬於未來的 `feat/router-*` 分支,這樣第五節「token 機率加任務啟發式」的 MVP 建議仍然成立。

## 四、Harness 設計:三個訊號變體,一次採樣

先說明用詞:本節與第七節都用到「配置」這個詞,但指的不是同一件事。架構 v0.3 第七節定義的三種**系統配置**是純本地、混合、純雲端。下面的訊號變體 A、B、C 是三種候選的信心**訊號**,只存在於混合配置內部,不會單獨跑。本文件之後一律稱 A/B/C 為「訊號變體」,「配置」保留給第七節的三種。

### 4.1 共用採樣預算

每題只生成一次本地模型的 *k* 個樣本,三個訊號變體都從這批共用樣本衍生,讓 harness 只付一次 k 次生成的成本,而不是 3k 次:

- **訊號變體 A — 零額外開銷。**只用樣本一;信心 = token logprob。零額外成本。W4–W7 期中範圍。
- **訊號變體 B — 低成本探針。**樣本一的 hidden states 過離線訓練好的 SEP。推論成本與 A 相同;額外成本是一次性的探針訓練,以及需要能吐出 hidden states 的推論堆疊(第二節註腳)。W9–W11 擴充階段範圍。
- **訊號變體 C — 採樣 Ensemble。**用全部 k 個樣本;自我一致性同意度,和/或蘊含聚類的語意熵。成本最高、實證最充分的訊號變體,作為上限參照。W9–W11 擴充階段範圍。

每個訊號變體都是混合配置信心訊號的候選實作,對同一組純本地與純雲端基準線做比較(4.3 節說明這兩個基準線怎麼從同一次跑產出)。

### 4.2 每個訊號變體的六個信心指標

這**不是**架構 v0.3 第七節每個系統配置各算一次的六個系統指標(準確率、延遲、每題成本、升級率、PII 洩漏率、Prompt Injection 抵抗力)。這是第七節那句話的信心細節展開:「混合配置另外畫出升級率對正確率曲線、AUROC 與校準誤差」。Harness 仍然會替純本地、混合、純雲端三種系統配置各自記錄第七節的六個系統指標——那張表才是主要結果;以下是把混合配置的信心訊號,展開成每個訊號變體的細節:

1. **系統準確率**——依這個訊號變體的升級決策,經過路由後的端到端正確率。
2. **純本地準確率**——不計升級的正確率,單獨看路由本身的貢獻。
3. **ECE**——信心分數相對本地回答正確與否的校準程度。
4. **AUROC**——信心分數的排序能力。
5. **AURC**(或固定 coverage,例如 80% 下的準確率)——選擇性預測的表現。
6. **升級率與推論成本倍數**——送往雲端的比例,搭配實際的運算倍數(1×、1×+探針、或 k×)。這跟第七節的每題成本是不同的數字:倍數算的是相對本地運算量,每題成本算的是實際花費的美元,含雲端呼叫。兩個都會回報。

採樣迴圈本身會記錄每題的 wall-clock 延遲與雲端 token 數(換算成美元),所以第七節的延遲與每題成本這兩個指標,直接從同一次跑就能算出來,不用另外跑一次。PII 洩漏率與 prompt injection 抵抗力則由安全工作流在 W9–W11,從同一批日誌算出來。

最終結果是兩層表:架構 v0.3 第七節的 3 種配置 × 6 個系統指標作為主表,混合配置那一列的信心訊號再展開成 3 個訊號變體 × 6 個信心指標,如上。

第 6 項指標是多數路由文獻沒有回報的數字(見文獻回顧第二節):已發表的研究大多只報告路由帶來的節省,很少單獨核算信心估計器本身的成本。這個 harness 同時回報兩邊。

### 4.3 一次採樣的執行流程

雲端模型每題都無條件呼叫一次,並快取答案——不是等某個訊號變體觸發升級才呼叫。這不會多花錢:純雲端配置本來就需要每題都送雲端一次,所以把這次呼叫的結果快取重複使用,比分開跑「純雲端另外跑一次」更省;而且這樣一來,架構 v0.3 第七節的三種系統配置就能從同一次跑產出:

```
for each query in eval_set:
    samples[1..k] = local_model.generate(query, n=k, temperature=T)   # 唯一的共用本地成本
    cloud_answer = cloud_model.generate(query)                        # 唯一的共用雲端成本,每題都呼叫並快取

    conf_A = token_logprob_score(samples[1])
    escalate_A = conf_A < threshold_A

    conf_B = semantic_entropy_probe(hidden_states(samples[1]))        # 離線訓練一次;W9-W11
    escalate_B = conf_B < threshold_B

    conf_C = self_consistency_agreement(samples[1..k])                # 和/或 semantic_entropy(samples);W9-W11
    escalate_C = conf_C < threshold_C

    record("純本地", correctness(samples[1], gold))
    record("純雲端", correctness(cloud_answer, gold))

    for variant in [A, B, C]:
        final_answer[variant] = cloud_answer if escalate[variant] else samples[1]  # C 用多數決
        record("混合", variant, correctness(final_answer[variant], gold),
               correctness(samples[1] or majority, gold), conf[variant], escalate[variant])

# 迴圈結束後:
#   每種系統配置(純本地 / 混合 / 純雲端):準確率、延遲、每題成本、升級率
#     (架構 v0.3 第七節的六項,扣掉 PII 洩漏率與 prompt injection 抵抗力,
#      這兩項由安全工作流在 W9-W11 從同一批日誌補上)
#   每個混合配置下的訊號變體(A / B / C):準確率、純本地準確率、ECE、AUROC、
#     AURC@80% coverage、升級率與成本倍數(4.2 節)
```

成本是從日誌算出來的——每個訊號變體的升級旗標乘上雲端 token 數——而不是每個訊號變體各自呼叫雲端,因為不管有幾個訊號變體會觸發升級,每題實際只呼叫雲端一次。

`threshold_A/B/C` 各自在獨立的 held-out dev split 上校準,與第五節的 benchmark 測試集分開;基礎 8B 模型換掉時必須重新校準。期中(第三、六節)只校準 `threshold_A`;`threshold_B` 與 `threshold_C` 等訊號變體 B、C 在 W9–W11 出現後再校準。

## 五、`correctness(...)` 用的資料集

架構 v0.3 第七節已列出 MMLU、GSM8K、TruthfulQA/HaluEval,以下是各資料集的評分細節:

| Benchmark | 格式 | 評分方式 | 但書 |
|---|---|---|---|
| MMLU | 四選一,57 個學科 | 準確率,5-shot | 文獻記載約 6.5% 標籤錯誤率(Virology 學科最高達 57%)——這是 ECE/AURC 能達到的下限,不應把非零 ECE 直接解讀為模型不佳,要先對照這個下限。 |
| GSM8K | 自由文字數學應用題 | 對 `####` 後的最終數字做精確比對 | — |
| TruthfulQA | MVP 只做選擇題(MC1/MC2 用 logprob 算,跟訊號變體 A 同一套機制) | 用 logprob 算,不需要外部裁判 | 自由生成那個分割需要微調過的 GPT-judge/GPT-info 分類器——是 OpenAI 在一個已經停止服務的底模上做的微調。雲端供應商(TODO A6)還沒定案;如果最後選 Anthropic,harness 的評分邏輯就不該綁死 OpenAI。自由生成評分延後到 A6 定案後再做,真要做就用 HF 上的開源裁判模型。 |
| HaluEval | QA / 對話 / 摘要 + 一般問答 | 二元 Yes/No 幻覺判斷,對照標籤 | 最直接對應 ECE/AUROC/AURC 需要的二元對錯標籤;四者中對 harness 最友善。 |

## 六、實作路線圖

建議的分支順序(命名規則見 repo 根目錄 `README.md`),依審閱意見指出的期中/擴充分界拆開:

| 分支 | 範圍 | 依賴 | 階段 |
|---|---|---|---|
| `docs/confidence-harness-design` | 本文件 | — | — |
| `feat/harness-sampling-core` | 建在 HF transformers 上的共用 k-sample 迴圈(TODO A1)、無條件呼叫並快取的雲端呼叫、query/result 資料結構、升級觸發 | 本文件 | W4–W7 |
| `eval/benchmark-loaders` | MMLU / GSM8K / TruthfulQA(MC)/ HaluEval 的資料載入與 `correctness(...)` 評分 | 本文件 | W4–W7 |
| `eval/calibration-metrics` | ECE、AUROC、AURC、升級率與成本倍數,用合成資料做單元測試 | 本文件 | W4–W7 |
| `feat/signal-token-logprob` | 訊號變體 A | `feat/harness-sampling-core` | W4–W7 |
| `feat/harness-threshold-calibration` | 在獨立 held-out dev split 上校準當下已存在的訊號變體門檻,產出升級率對正確率曲線。只要有一個訊號變體就能開始,不必等三個都到齊——期中這次只校準 `threshold_A` | 至少一個訊號變體分支 | W4–W7(訊號變體 A),W9–W11 延伸(B、C) |
| `eval/midpoint-pilot` | 第一次真實跑出的結果:只用訊號變體 A,在 MMLU 子集 + GSM8K 上跑架構 v0.3 第七節的三種系統配置,產出準確率/升級率/每題成本/延遲(TODO A7) | sampling-core、benchmark-loaders、calibration-metrics、signal-token-logprob、threshold-calibration(A) | W4–W7 |
| `feat/signal-sep-probe` | 訊號變體 B:離線探針訓練 + 推論時對 hidden states 打分(需要 `feat/harness-sampling-core` 的 transformers 堆疊,見第二節註腳) | `feat/harness-sampling-core` | W9–W11 |
| `feat/signal-sampling-ensemble` | 訊號變體 C:自我一致性(可選加語意熵聚類) | `feat/harness-sampling-core` | W9–W11 |
| `eval/full-run` | 三個訊號變體齊全後的完整 3 配置 × 6 指標結果表;PII 洩漏率與 prompt injection 抵抗力由安全工作流補上 | signal-sep-probe、signal-sampling-ensemble、threshold-calibration(B、C) | W9–W11 |

## 七、待留意的風險

- **MMLU 標籤雜訊**限制了 ECE/AURC 能達到的下限,與模型品質無關(第五節)。
- **門檻校準是模型專屬的**,不是「8B 參數」這個規模的固定屬性——基礎模型一換就要重新校準。
- **文獻的成本核算缺口**:多數路由論文只報告節省,不單獨核算信心估計器本身的成本。第 4.2 節的第 6 項指標就是為了補上我們這批結果的這塊缺口。
- **沒有精準落在 8B 的直接實證**:自我一致性、P(True)/P(IK)、完整語意熵都沒有精準在 8B 測試過(最接近的測試點:語意熵在 7B/13B、P(True)/P(IK) 在 3B/12B、自我一致性在 20B 以上)。訊號變體 C 的數字僅供參考,不是規模對齊的 ground truth。

本文件原本替訊號變體 B 帶著的推論堆疊風險(SEP 需要 hidden states;Ollama/llama.cpp/vLLM 都拿不到)現在已經解決,不算未決:TODO A1 與 2026-09-15 的決策日誌,就是因為 harness 需要才把推論堆疊定為 HF transformers 加 bitsandbytes 4-bit。

## 八、與待決事項的關係

本文件對訊號變體 B / 推論堆疊的分析,直接促成了 TODO A1「推論堆疊要能暴露 logprobs 與 hidden states」這條硬性要求,以及後續選 HF transformers 而不用 Ollama 的決定(2026-09-15 決策日誌)——見 `todo/TODO-zh.md`。另外還有一條更早的補充值得留在決策日誌:排除口頭表態信心是基於實證,不是漏掉沒考慮(2026-09-14 決策日誌)。

---

*信心評分與評測 Harness — 設計文件 v0.2 · Capstone for Virtual Gold Inc · 2026-09-15*
