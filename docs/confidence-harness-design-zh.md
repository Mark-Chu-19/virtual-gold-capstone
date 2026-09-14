# 信心評分與評測 Harness — 設計文件

**Capstone · Virtual Gold Inc · 第 3 週 · 信心評分工作項目**

延伸 [architecture-v0.2-zh.md](architecture-v0.2-zh.md) 第五節(信心評分)與第七節(評測設計與資料集),補上 8B 級文獻回顧與可執行的 harness 設計。本文件是下方第五節所列 `feat/harness-*`、`eval/*` 分支的依據。

| 版本 | 日期 | 狀態 | 作者 |
|---|---|---|---|
| v0.1 | 2026-09-14 | 草稿,待團隊審閱 | Zhexuan Ye |

---

## 一、為什麼要有這份文件

架構 v0.2 第五節列出五種候選信心策略(token 機率、自我一致性、驗證模型、檢索接地度、任務啟發式),並建議 MVP 先做 token 機率加任務啟發式,但沒有引用特定規模下的實證資料。本文件用在我們目標規模(Llama 3.1 8B / Qwen3 8B)附近做過測試的文獻收斂這個建議,並把架構 v0.2 第七節的三配置評測設計,落成一套可執行的 harness。

本文件要回答三個問題:

1. 哪些信心訊號在 8B 規模上有直接(非外推)的實證支持?
2. 每種訊號多花幾次推論,讓 harness 同時回報準確度增益與運算成本?
3. 怎麼一次跑完三種配置、六個指標,而不是分三次獨立評測?

## 二、8B 規模下的信心訊號總覽

| 訊號 | 每題額外本地生成次數 | 額外輔助模型呼叫 | 一次性成本 | 8B 規模實證 |
|---|---|---|---|---|
| Token 機率 / softmax | 0 | 0 | 無 | 直接:小模型 AUROC 0.71–0.87 |
| 口頭表態信心(同一次生成) | 0 | 0 | 無 | 直接:8B 上**已失效**——收斂成近乎恆定的「非常有信心」 |
| 口頭表態信心(追問一次) | 1 | 0 | 無 | 無 8B 直接測試;由能力趨勢推論 |
| Semantic Entropy Probe(SEP) | 推論時 0 | 0 | 一次性探針訓練 | 最小測試模型:7B(Llama-2-7B、Mistral-7B);無 8B 專屬消融實驗 |
| P(True) / P(IK) | ≥1 | 0 | 無 | 無 8B 測試(只有 800M/3B/12B/52B);規模趨勢顯示 OOD 泛化更差 |
| 自我一致性 | k−1(約 5–10 個樣本即飽和) | 0 | 無 | 無 8B 測試(僅 20B–540B);小模型增益較小 |
| 完整語意熵 | M−1(原論文 M=10) | O(M²) 蘊含檢查 | 無 | 直接:LLaMA-2-Chat 7B/13B,AUROC 0.79 |
| SelfCheckGPT(n-gram / BERTScore) | N−1 | 0(n-gram)/ 輕量(BERTScore) | 無 | 直接:Llama-2-7B/13B 測試 |
| SelfCheckGPT(NLI / prompt-based) | N−1 | N 次呼叫 | 無 | 直接:7B/13B 測試,最佳結果需 GPT-3.5 當裁判 |

完整文獻回顧、逐篇但書與引用出處:`reference/team/confidence_scoring_harness_report_concise_en.md`(Zhexuan Ye,2026-09-13)。

**沿用該回顧的設計限制:**2026 年一項預註冊的心理計量篩檢,直接測試七個 3B–9B 開源指令模型(含 Llama-3-8B-Instruct、Llama-3.1-8B-Instruct),發現口頭表態信心會收斂——91.7% 的回覆自報信心 ≥95%,與答對答錯無關;其中兩個模型在 500 多次試驗中從未給過低信心評分。這推翻了架構 v0.2 第五節隱含的假設:模型可以直接「說出」自己的信心。**我們不用口頭表態信心做升級決策。**架構 v0.2 第五節的策略表應理解為:token 機率、自我一致性、檢索接地度是可行候選;驗證模型與任務啟發式兩項不受此結論影響。

## 三、Harness 優先實作順序

依 8B 規模的實證強度與邊際成本排序,最貼近架構 v0.2 第九節 MVP 承諾(「自我一致性或 token logprob 作為基準線訊號」):

1. **Token 機率信心**——邊際成本為零,有貼近 8B 規模的直接實證。優先實作。
2. **Semantic Entropy Probe**——訓練完成後推論時邊際成本為零,是回顧中成本/準確度組合最佳的訊號,但需要一次性的標註校準流程(離線跑一次完整語意熵,產生探針的訓練目標)。第二優先。
3. **自我一致性 / 完整語意熵 ensemble**——成本最高但實證最充分的上限參照。第三順位實作,作為「k 倍運算是否值得」的參照基準,而非預設出貨方案。

架構 v0.2 第五節的檢索接地度與驗證模型策略不在本文件範圍內;兩者取決於架構 v0.2 第十一節第 2 項尚未拍板的 RAG 決策。

## 四、Harness 設計:三種配置,一次採樣

### 4.1 共用採樣預算

每題只生成一次本地模型的 *k* 個樣本,三種配置都從這批共用樣本衍生,讓 harness 只付一次 k 次生成的成本,而不是 3k 次:

- **配置 A — 零額外開銷。**只用樣本一;信心 = token logprob。零額外成本。
- **配置 B — 低成本探針。**樣本一的 hidden states 過離線訓練好的 SEP。推論成本與 A 相同;唯一的額外成本是一次性的探針訓練。
- **配置 C — 採樣 Ensemble。**用全部 k 個樣本;自我一致性同意度,和/或蘊含聚類的語意熵。成本最高、實證最充分的配置,作為上限參照。

這三種配置對應到架構 v0.2 第七節「純本地 / 混合 / 純雲端」三配置評測中「混合」配置的三種候選信心訊號實作,各自對同一組純本地與純雲端基準線做比較。

### 4.2 每種配置六個指標(3×6 結果表)

對應架構 v0.2 第七節的指標清單,把信心相關指標(ECE、AUROC、校準誤差)明確拆到每個配置分別計算,而不是只對「混合」配置算一次:

1. **系統準確率**——經過路由後的端到端正確率。
2. **純本地準確率**——不計升級的正確率,單獨看路由本身的貢獻。
3. **ECE**——信心分數相對本地回答正確與否的校準程度。
4. **AUROC**——信心分數的排序能力。
5. **AURC**(或固定 coverage,例如 80% 下的準確率)——選擇性預測的表現。
6. **升級率與推論成本倍數**——送往雲端的比例,搭配實際的運算倍數(1×、1×+探針、或 k×)。

第 6 項指標是多數路由文獻沒有回報的數字(見文獻回顧第二節):已發表的研究大多只報告路由帶來的節省,很少單獨核算信心估計器本身的成本。這個 harness 同時回報兩邊。

### 4.3 一次採樣的執行流程

```
for each query in eval_set:
    samples[1..k] = local_model.generate(query, n=k, temperature=T)   # 唯一的共用成本

    conf_A = token_logprob_score(samples[1])
    escalate_A = conf_A < threshold_A

    conf_B = semantic_entropy_probe(hidden_states(samples[1]))        # 離線訓練一次
    escalate_B = conf_B < threshold_B

    conf_C = self_consistency_agreement(samples[1..k])                # 和/或 semantic_entropy(samples)
    escalate_C = conf_C < threshold_C

    if escalate_A or escalate_B or escalate_C:
        cloud_answer = cloud_model.generate(query)                    # 每題最多呼叫一次

    for cfg in [A, B, C]:
        final_answer[cfg] = cloud_answer if escalate[cfg] else samples[1]  # C 用多數決
        record(cfg, correctness(final_answer[cfg], gold),
               correctness(samples[1] or majority, gold), conf[cfg], escalate[cfg])

# 迴圈結束後,依配置分別輸出:
#   準確率、純本地準確率、ECE、AUROC、AURC@80% coverage、升級率與成本倍數
```

`threshold_A/B/C` 各自在獨立的 held-out dev split 上校準,與第五節的 benchmark 測試集分開;基礎 8B 模型換掉時必須重新校準。

## 五、`correctness(...)` 用的資料集

架構 v0.2 第七節已列出 MMLU、GSM8K、TruthfulQA/HaluEval,以下是各資料集的評分細節:

| Benchmark | 格式 | 評分方式 | 但書 |
|---|---|---|---|
| MMLU | 四選一,57 個學科 | 準確率,5-shot | 文獻記載約 6.5% 標籤錯誤率(Virology 學科最高達 57%)——這是 ECE/AURC 能達到的下限,不應把非零 ECE 直接解讀為模型不佳,要先對照這個下限。 |
| GSM8K | 自由文字數學應用題 | 對 `####` 後的最終數字做精確比對 | — |
| TruthfulQA | 選擇題 + 自由生成 | 選擇題用 logprob 算 MC1/MC2;自由生成用微調過的 GPT-judge/GPT-info 分類器評分 | — |
| HaluEval | QA / 對話 / 摘要 + 一般問答 | 二元 Yes/No 幻覺判斷,對照標籤 | 最直接對應 ECE/AUROC/AURC 需要的二元對錯標籤;四者中對 harness 最友善。 |

## 六、實作路線圖

建議的分支順序(命名規則見 repo 根目錄 `README.md`):

| 分支 | 範圍 | 依賴 |
|---|---|---|
| `docs/confidence-harness-design` | 本文件 | — |
| `feat/harness-sampling-core` | 共用的 k-sample 迴圈、query/result 資料結構、升級觸發、雲端呼叫的樁函式 | 本文件 |
| `eval/benchmark-loaders` | MMLU / GSM8K / TruthfulQA / HaluEval 的資料載入與 `correctness(...)` 評分 | 本文件 |
| `eval/calibration-metrics` | ECE、AUROC、AURC、升級率與成本倍數,用合成資料做單元測試 | 本文件 |
| `feat/signal-token-logprob` | 配置 A | `feat/harness-sampling-core` |
| `feat/signal-sep-probe` | 配置 B:離線探針訓練 + 推論時打分 | `feat/harness-sampling-core` |
| `feat/signal-sampling-ensemble` | 配置 C:自我一致性(可選加語意熵聚類) | `feat/harness-sampling-core` |
| `feat/harness-threshold-calibration` | 在獨立 held-out dev split 上校準 `threshold_A/B/C`,產出升級率對正確率曲線 | 上述訊號分支 |
| `eval/*-pilot-run` | 第一次真實跑出 3×6 結果表 | 校準分支 |

## 七、待留意的風險

- **MMLU 標籤雜訊**限制了 ECE/AURC 能達到的下限,與模型品質無關(第五節)。
- **門檻校準是模型專屬的**,不是「8B 參數」這個規模的固定屬性——基礎模型一換就要重新校準(架構 v0.2 第十一節第 5 項仍待定)。
- **文獻的成本核算缺口**:多數路由論文只報告節省,不單獨核算信心估計器本身的成本。第 4.2 節的第 6 項指標就是為了補上我們這批結果的這塊缺口。
- **沒有精準落在 8B 的直接實證**:自我一致性、P(True)/P(IK)、完整語意熵都沒有精準在 8B 測試過(最接近的測試點:語意熵在 7B/13B、P(True)/P(IK) 在 3B/12B、自我一致性在 20B 以上)。配置 C 的數字僅供參考,不是規模對齊的 ground truth。

## 八、與待決事項的關係

本文件不需要更動架構 v0.2 第十一節的任何待決事項,但值得在決策日誌補一條:排除口頭表態信心是基於實證,不是漏掉沒考慮。見 `todo/TODO-zh.md` 決策日誌。

---

*信心評分與評測 Harness — 設計文件 v0.1 · Capstone for Virtual Gold Inc · 2026-09-14*
