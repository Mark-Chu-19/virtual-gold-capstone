---
title: 信心評分與評測 Harness — 研究報告(精簡版)
subtitle: Virtual Gold Inc. Capstone(安全混合式 AI 助理)— 信心評分與模型路由工作包
date: 2026 年 9 月 13 日
author: Zhexuan Ye(CMU MISM Capstone 團隊)
translation: 中文翻譯,原文為 `confidence-scoring-harness-report-en.md`;引用數字與結論以英文原稿為準
---

# 信心評分與評測 Harness

## 哪些不確定性訊號在 8B 級本地模型上有效、各要多少成本、以及如何做 benchmark

---

## 0. 範圍

贊助方(Virtual Gold Inc.)的專案說明描述了一個混合式助理:在本地執行開源 LLM,並在「需要更高信心或推理能力時」升級到雲端模型,但沒有指定方法或 harness 設計。本報告為信心評分工作包回答三個問題:

1. 哪些信心訊號在 8B 模型上真的有效?
2. 每種訊號各多花多少次推論?
3. Harness 要怎麼一次跑完三種配置並輸出六個指標?

---

## 1. 信心訊號總覽

### 1.1 單次推論、近乎零成本的訊號(全部與模型規模相關,模型越大越可靠)

**Token 機率 / softmax 信心。** 模型在生成答案 token 時本來就算出的對數機率,是既有生成呼叫的副產品,所以免費。一項 2025 年的醫學問答研究發現,token 機率優於口頭表態信心(AUROC 0.71–0.87 對 0.51–0.70),在測試的全部 9 個模型上 Brier 分數都勝出,但誤報率並非全面領先(兩個 Gemma 模型沒有改善,一個明顯更差)。校準程度直接隨模型規模變化:Phi-3-Mini 的 ACE 超過 40%,中型模型(Phi-3-Medium、Llama 3.1-8B)約 20–25%,GPT-4o 級模型低於 10%([PMC12396779](https://pmc.ncbi.nlm.nih.gov/articles/PMC12396779/))。**限制:需要能取得 logprob**(GPT 系列、Llama、Phi、Gemma 可以;Claude 與 Gemini 的 API 不提供)。模型越小,可靠度越低。

**口頭表態信心(單一提示)。** 模型自己說出一個數值或類別的信心,若附在同一次生成裡則免費。Xiong et al.(2023)發現核心問題在可靠度而不是成本:模型系統性地過度自信,沒有任何提示或彙整技巧能穩定修正。他們測試的模型從 GPT-3(175B)、Vicuna(13B)到 LLaMA-2(70B)、GPT-3.5、GPT-4;較弱或 RLHF 較少的模型(例如 GPT-3)校準差得多(ECE 高達 52.0,AUROC 接近隨機)。沒有測 8B 模型,所以無法直接量化 8B 的問題,但「能力越弱,口頭信心越差」的趨勢讓人合理預期問題在 8B 會持續或更糟,待直接證據確認([arXiv:2306.13063](https://arxiv.org/abs/2306.13063))。

**P(True) / P(IK) 自我評估(Kadavath et al. 2022)。** P(True):生成候選答案後,請模型估計它正確的機率。P(IK):不給候選答案,問模型「知不知道」這題。兩者都需要至少一次額外的 forward pass;讓模型先看幾個自己的樣本再判斷會更好,但又引入多樣本成本。論文只測了 **800M / 3B / 12B / 52B** 的模型,沒有 8B,發現 P(IK) 的 AUROC 與校準都隨規模改善,意味著小模型對新任務的泛化較差。8B 落在 3B 與 12B 兩個測試點之間,所以這是方向性的支持,不是 8B 泛化變差的直接證據([arXiv:2207.05221](https://arxiv.org/abs/2207.05221))。

### 1.2 學習型、單次推論的訊號(訓練一次,推論免費)

**語意熵探針(Semantic Entropy Probes,SEP)。** 完整語意熵每題要採樣多次生成(5–10 倍成本)。SEP 繞過這點:一個小型線性探針,在模型自身的 hidden states 上離線訓練一次,預測「昂貴的語意熵分數會是多少」。不需要人工標註的正確性,因為訓練目標來自在校準集上跑一次語意熵。部署時只需要單次生成的 hidden states。SEP 在分布外(OOD)的泛化優於以準確率訓練的探針(分布內則後者較好),但無法完全達到完整語意熵的絕對表現。測過最小的模型:**Llama-2-7B 與 Mistral-7B**,是本次回顧的訊號中最接近我們 8B 目標的,但仍是外推,不是 8B 的直接量測([arXiv:2406.15927](https://arxiv.org/abs/2406.15927);[程式碼](https://github.com/OATML/semantic-entropy-probes))。

### 1.3 多樣本、以一致性為基礎的訊號

**自我一致性(Wang et al. 2022)。** 在非零溫度下採樣 *k* 條推理路徑,多數決的一致程度同時當作信心。原論文用 k=40(消融了 1/5/10/20/40);多數任務在 k≈5–10 就飽和。測試模型:**UL2-20B、LaMDA-137B、GPT-3-175B、PaLM-540B**,沒有接近 8B 的。在 GSM8K 上,最小的模型(UL2-20B)獲益最少(+3.2 分,4.1%→7.3%),LaMDA-137B 與 GPT-3 則 +9–23 分。論文自己的解釋是算術與推理能力只在足夠規模才「湧現」,這對 8B 是關鍵警訊:低於湧現門檻,獲益可能有限。成本:**k−1 次額外本地生成**,不需要輔助模型([arXiv:2203.11171](https://arxiv.org/abs/2203.11171))。

**語意熵(Kuhn et al. 2023;Farquhar et al. 2024,*Nature*)。** 把 M 個採樣生成依語意(雙向蘊涵)分群,在群上而不是 token 上算熵(主分析用 M=10)。在我們的目標規模有直接驗證:**LLaMA-2-Chat 7B/13B/70B、Falcon-Instruct 7B/40B、Mistral-Instruct 7B**。30 個任務–模型組合的 AUROC 為 0.790,優於樸素熵(0.691)與 P(True)(0.698)。成本:**M−1 次生成加 O(M²) 次成對蘊涵檢查**(NLI 模型或便宜的 LLM 呼叫);離散變體不需要精確 logprob,黑盒 API 也能用([Nature](https://www.nature.com/articles/s41586-024-07421-0))。

**SelfCheckGPT(Manakul et al. 2023)。** 黑盒方法:抽 N 個樣本,檢查主回答的每一句是否被樣本支持,後端五選一(BERTScore、選擇題/問答一致性、n-gram 統計、NLI、或 LLM 提示)。最佳結果(AUC-PR 93.42)用 GPT-3.5 當提示式評審;公開 repo 也回報提示變體在 **Llama-2-7B/13B-chat 與 Mistral-7B-Instruct** 上的結果(AUC-PR 89–92,低於 GPT-3.5)。成本隨 N 增加;NLI 與提示變體多 N 次輔助模型呼叫;BERTScore 仍需要一個較輕的輔助模型(RoBERTa-Large);只有 **n-gram 變體真正不需要第二個模型**,純粹對已生成的 N 個樣本做統計,是搭配本地 8B 模型最便宜的選項([arXiv:2303.08896](https://arxiv.org/abs/2303.08896);[程式碼](https://github.com/potsawee/selfcheckgpt))。

---

## 2. 校準與評測指標

**ECE** 依信心把預測分箱,比較每箱的平均自報信心與實際準確率:ECE = Σ(|B_m|/n)·|acc(B_m) − conf(B_m)|。量的是校準偏差的大小,不是排序能力。

**AUROC** 把正確與否當二元標籤、信心當分類器分數,量的是與校準無關的區辨力。這是文獻中標準的正面對決指標(例如語意熵 0.790 對樸素熵 0.691)。

**風險–涵蓋曲線 / AURC。** 依信心排序預測;在涵蓋率 κ=k/n 時,計算保留的前 k 筆的錯誤率。AURC 把整條曲線積分成一個數字(越低越好),獎勵正確的*排序*,即使絕對值沒有校準。

**升級率對準確率曲線。** 風險–涵蓋在系統層級的對應物:掃描升級門檻,畫出「送到雲端模型的查詢比例」對「端到端準確率或成本」。一篇 cascade 綜述引用一個框架用這種方式達到「GPT-4 品質的 97.25%,成本的 24.18%」([arXiv:2603.04445](https://arxiv.org/html/2603.04445v1))。該綜述大多只回報路由帶來的成本*節省*,幾乎沒有分開計算信心估計器本身*增加*的成本,這正是 RQ2 要補的缺口。

---

## 3. RQ1 與 RQ2:8B 上什麼有效、成本多少

### 3.1 口頭表態信心:在 8B 不只是弱,是壞掉

一項 2026 年預先註冊的心理計量篩檢直接測試了 **3B–9B 開源指令模型**:Meta-Llama-3-8B-Instruct、Meta-Llama-3.1-8B-Instruct、DeepSeek-R1-Distill-Llama-8B、Mistral-7B、Qwen2.5-3B/7B、Gemma-2-9B。口頭表態信心會**飽和**:七個模型中,91.7% 的回覆自報信心平均 ≥95%,有兩個模型在 500 多次試驗中從未給過低信心評分,與答對答錯無關。作者稱這是「效度失效,而不是校準問題」:一個塌縮到天花板的分布幾乎不帶資訊。他們的結論:任何用小型開源模型的口頭信心做路由決策的混合系統「都建立在退化的訊號上」([arXiv:2604.22215](https://arxiv.org/html/2604.22215))。

### 3.2 8B 上什麼有效

- **Token 機率信心**:免費;即使在小規模也能有意義地區分對錯(AUROC 0.71–0.87),比口頭信心近乎隨機的表現好很多。
- **語意熵**:在 7B/13B 有直接驗證(AUROC 0.79),同規模下優於樸素熵與 P(True)。
- **語意熵探針**:沒有找到針對尺寸的消融,但繼承語意熵的訊號並幾乎去掉全部邊際成本;測過最小的模型是 7B。是成本與準確率組合最強的,應最先做原型。

自我一致性與 P(True) 在小規模仍優於貪婪解碼,但兩篇論文都指出低於「湧現」門檻或面對新任務時獲益減少。SelfCheckGPT 較便宜的 n-gram / BERTScore 變體比依賴強評審模型的提示式變體更適合全本地的管線。

### 3.3 推論成本表

| 訊號 | 每題額外本地生成次數 | 額外輔助模型呼叫 | 一次性成本 | 8B 規模的證據 |
|---|---|---|---|---|
| Token 機率 / softmax | **0** | 0 | 無 | 直接:小模型 AUROC 0.71–0.87 |
| 口頭表態信心(同一次生成) | 0 | 0 | 無 | 直接:在 8B **壞掉**(飽和) |
| 口頭表態信心(追問) | 1 | 0 | 無 | 沒測 8B;由能力趨勢推論 |
| 語意熵探針 | 推論時 0 | 0 | 探針訓練一次 | 測過最小 7B;沒有 8B 專屬消融 |
| P(True) / P(IK) | ≥1(加樣本條件則更多) | 0 | 無 | 沒測 8B(僅 800M/3B/12B/52B);規模趨勢顯示 OOD 泛化較差 |
| 自我一致性 | k−1(論文 k=40;約 5–10 飽和) | 0 | 無 | 沒測 8B(20B–540B);小模型獲益較少 |
| 完整語意熵 | M−1(論文 M=10) | O(M²) 次蘊涵檢查 | 無 | 直接:7B/13B,AUROC 0.79 |
| SelfCheckGPT(n-gram / BERTScore) | N−1(論文約 20) | 0(n-gram)/ 輕量(BERTScore) | 無 | 直接:在 Llama-2-7B/13B 測過 |
| SelfCheckGPT(NLI / 提示式) | N−1 | N 次呼叫 | 無 | 直接:7B/13B 測過,最佳結果需要 GPT-3.5 評審 |

**結論:** token 機率信心與語意熵探針是這裡唯二「每題邊際成本近乎零」*且*「在接近 8B 的規模有真實(非純外推)證據」的訊號。多樣本方法能換到可量測的 AUROC 與準確率提升,但成本是單次推論的 5–40 倍,考量贊助方對本地算力成本效率的目標,預算要據此安排。

---

## 4. RQ3:一次跑完三種配置、六個指標的 Harness

### 4.1 設計:共用採樣預算

每題**只生成一次**本地模型的 *k* 個樣本,再從同一批樣本導出三種配置:

- **配置 A — 零額外開銷。** 只用樣本 #1;信心 = token logprob。沒有額外成本。
- **配置 B — 便宜探針。** 樣本 #1 的 hidden states 過一個離線訓練好的 SEP 式探針。推論成本與 A 相同;唯一增加的是一次性的探針訓練。
- **配置 C — 採樣集成。** 用全部 k 個樣本;自我一致性和/或以蘊涵分群的語意熵。昂貴、驗證最充分的配置,也是「k 倍算力值不值得」的上限參考。

A 與 B 重用 C 的樣本 #1,所以 harness 為 k 次生成付費**一次**,不是 3k 次。每題最多一次雲端呼叫(只要任一配置升級),三種配置共用,但各自記帳以維持指標獨立。

### 4.2 每種配置六個指標(3×6 = 18 格結果表)

1. **系統準確率**:路由後的端到端正確率。
2. **純本地準確率**:忽略升級的正確率,用來分離路由的貢獻。
3. **ECE**:信心分數對本地回答正確與否的校準程度。
4. **AUROC**:信心分數的排序能力。
5. **AURC**(或固定涵蓋率下的準確率,例如 80%):選擇性預測的表現。
6. **升級率與推論成本倍數**:送到雲端的比例,搭配實際的算力倍數(1×、1×+探針、或 k×),這是文獻漏掉的那個數字。

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
        cloud_answer = cloud_model.generate(query)                    # 每題最多一次

    for cfg in [A, B, C]:
        final_answer[cfg] = cloud_answer if escalate[cfg] else samples[1]  # C 也可用多數決
        record(cfg, correctness(final_answer[cfg], gold),
               correctness(samples[1] or majority, gold), conf[cfg], escalate[cfg])

# 迴圈結束後,依配置分別輸出:
#   準確率、純本地準確率、ECE、AUROC、AURC@80% coverage、升級率與成本倍數
```

`threshold_A/B/C` 在獨立的 dev split 上各自校準;產出的升級率對準確率曲線本身就是有用的結果,回報的操作點可以對齊贊助方的升級預算(例如「≤20% 的查詢離開本地沙盒」)。

### 4.4 `correctness(...)` 用的 benchmark

| Benchmark | 格式 | 規模 | 評分方式 |
|---|---|---|---|
| **MMLU** | 四選一,57 個科目 | 15,908 題 | 準確率,標準 5-shot。文獻記錄的標籤錯誤率 6.5%(病毒學高達 57%)為可達到的 ECE/AURC 設下實質下限。 |
| **GSM8K** | 自由作答的數學應用題 | 8,792 題(7,473/1,319 切分) | `####` 之後的最終數字精確比對。 |
| **TruthfulQA** | 選擇題加自由生成,約 38 個類別 | 約 817 題 | MC1/MC2 用 logprob 評分;自由生成由微調的 GPT-judge/GPT-info 分類器評分(與人工一致率約 90–95%)。 |
| **HaluEval** | 問答/對話/摘要加一般查詢 | 35,000 題 | 對標籤的二元是/否幻覺判斷;人工一致性 κ=0.811。 |

HaluEval 的是/否格式最直接對應 ECE/AUROC/AURC 需要的二元「正確/錯誤」標籤,而且直接量測幻覺而不是任務準確率,可說是四者中最適合這個 harness 的。

---

## 5. 建議與待留意的風險

**原型順序:** 先做配置 A 對 B(token logprob 對 SEP),兩者每題都近乎免費,B 只需要一組有標籤的校準集。考量贊助方的成本效率目標,配置 C 當昂貴的上限參考,不當預設設計。

**不要建立在口頭表態信心上。** 把它當設計限制:多個 8B 級模型會塌縮成近乎常數的「非常有信心」回覆,所以在自己的模型與提示上獨立驗證之前,口頭信心不該用來把關升級。

**MMLU 標籤品質的但書。** 約 6.5% 的標籤錯誤率限制了 ECE/AURC 能低到哪裡,與模型品質無關,值得標明,免得非零的 ECE 被誤讀成模型的缺陷。

**補上文獻的成本核算缺口。** 已發表的路由與 cascade 研究回報路由帶來的節省,卻很少回報計算信心訊號本身增加的成本。指標 6(4.2 節)的設計就是要把帳本兩邊都列出來。

**門檻校準需要自己的 held-out split**,與 4.4 節的 benchmark 測試集分開調,而且基礎 8B 模型一換就要重新驗證。校準行為是模型與微調特定的,不是「8B 參數」的固定性質。

**關於規模證據的說明:** 本次回顧的訊號中,只有語意熵(Farquhar et al.)與 SelfCheckGPT 直接在接近目標的 7B 級模型上測過;Kadavath(P(True)/P(IK))、Xiong(口頭信心)與自我一致性(Wang et al.)的論文都沒有測 8B 級模型,所以它們與規模相關的主張在此是由相鄰尺寸外推,不是 8B 的直接量測,前文已逐一標明。

---

## 參考文獻

1. Wang, X. et al. (2022). *Self-Consistency Improves Chain of Thought Reasoning in Language Models.* [arXiv:2203.11171](https://arxiv.org/abs/2203.11171)
2. Kuhn, L., Gal, Y., Farquhar, S. (2023). *Semantic Uncertainty.* [arXiv:2302.09664](https://arxiv.org/abs/2302.09664)
3. Farquhar, S., Kossen, J., Kuhn, L., Gal, Y. (2024). *Detecting hallucinations in large language models using semantic entropy.* Nature. [連結](https://www.nature.com/articles/s41586-024-07421-0)
4. Kossen, J. et al. (2024). *Semantic Entropy Probes.* [arXiv:2406.15927](https://arxiv.org/abs/2406.15927);[程式碼](https://github.com/OATML/semantic-entropy-probes)
5. Kadavath, S. et al. (2022). *Language Models (Mostly) Know What They Know.* [arXiv:2207.05221](https://arxiv.org/abs/2207.05221)
6. Manakul, P., Liusie, A., Gales, M. (2023). *SelfCheckGPT.* [arXiv:2303.08896](https://arxiv.org/abs/2303.08896);[程式碼](https://github.com/potsawee/selfcheckgpt)
7. Xiong, M. et al. (2023). *Can LLMs Express Their Uncertainty?* [arXiv:2306.13063](https://arxiv.org/abs/2306.13063)
8. Anonymous (2026). *Verbal Confidence Saturation in 3–9B Open-Weight Instruction-Tuned LLMs.* [arXiv:2604.22215](https://arxiv.org/html/2604.22215)
9. (2025). *Token Probabilities to Mitigate LLM Overconfidence in Answering Medical Questions.* PMC. [連結](https://pmc.ncbi.nlm.nih.gov/articles/PMC12396779/)
10. *Mind the Confidence Gap.* [arXiv:2502.11028](https://arxiv.org/html/2502.11028v2)
11. *Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey.* [arXiv:2603.04445](https://arxiv.org/html/2603.04445v1)
12. *Leveraging Uncertainty Estimation for Efficient LLM Routing.* [arXiv:2502.11021](https://arxiv.org/html/2502.11021v1)
13. Expected Calibration Error. [Towards Data Science](https://towardsdatascience.com/expected-calibration-error-ece-a-step-by-step-visual-explanation-with-python-code-c3e9aa12937d/)
14. AURC 定義。[Torch-Uncertainty 文件](https://torch-uncertainty.github.io/generated/torch_uncertainty.metrics.classification.AURC.html);Traub, J. et al. [arXiv:2410.15361](https://arxiv.org/abs/2410.15361)
15. Hendrycks, D. et al. (2020). *MMLU.* [Wikipedia](https://en.wikipedia.org/wiki/MMLU)
16. Cobbe, K. et al. (2021). *GSM8K.* [HuggingFace](https://huggingface.co/datasets/openai/gsm8k)
17. Lin, S., Hilton, J., Evans, O. (2022). *TruthfulQA.* [arXiv:2109.07958](https://arxiv.org/abs/2109.07958)
18. Li, J. et al. (2023). *HaluEval.* [arXiv:2305.11747](https://arxiv.org/html/2305.11747v3)

*依 Virtual Gold Inc. capstone 提案與信心評分研究簡報整理;以上來源均經即時搜尋與一手來源核對。*
