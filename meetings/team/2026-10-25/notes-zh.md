# 團隊會議,2026-10-25(週日)

在 10/26 客戶會議前舉行。議程:[`agenda-zh.html`](agenda-zh.html)。英文版:[`notes-en.md`](notes-en.md)。

**出席:**Mark、Yudi、Zhexuan、Karina。Anmol 缺席。

## 決定

1. **Anmol 的 VPC 報告原樣給客戶。**Anmol 缺席,沒有人改寫。客戶頁面自己照實寫:是在託管的開源模型 API 上跑的,服務還沒部署到 VPC。措辭、24 個本機 `file://` 連結與 §7 提到 CMU OpenRouter 額度的那句,等 Anmol 處理(TODO B72)。
2. **客戶審 Yudi 的 policy-0.1.3。**22 類:`BANK_ACCOUNT` 改成 `ACCOUNT_NUMBER`、新增 `ADDRESS_PUBLIC`、Public 門檻從 0.5 提高到 0.8。這是 Yudi 的提案,他覺得比較準,想聽客戶的看法。客戶確認後才合併他的分支(B71)。Anmol 的外洩數字是用他自己的 3 級規則量的,所以客戶頁面註明會用確認後的分級表重跑(B69)。
3. **API v2 當作 Zhexuan 的提案展示。**他想聽客戶對兩種模式與 token 格式的看法(客戶頁面 Q6)。他的 PR #10 已於 2026-10-26 審查並合併(見下方)。
4. **打不開的連結。**Zhexuan 簡介連到的兩份文件在 PR #10 裡,現在已在 main 的 `docs/api/`。repo 是私有的,所以客戶頁面只寫資料夾名稱,不放連結。
5. **Karina 的資料集(PR #9)維持 policy 0.1.1。**她刻意用 0.1.1,因為 0.1.3 只是提案。所以資料集沒有過時,也不用等 Yudi 的分支。客戶若確認 0.1.3,她再重新產生 `service_type` 與 `tier`。
   - 她說每一列都複核完了。PR 裡還看不到:「Karina check」欄是空的,100 封信的 `gt_status` 都還是 draft(B74)。
   - 對客戶照她 README 的說法描述資料集。
   - 落在 Low 級的 86 個應遮片段(67 ORG、12 CITY、6 DATE、1 AGE)、出生日期、交易對象與 39 個編號,隨分級表一起問客戶(Q1)。
   - 信箱名稱被當成人名的 `NON_PERSON_WORDS` 修正之後再談(B75)。
6. **明天的順序:**Yudi 先,再來 Anmol,然後 Karina 與 Zhexuan。

## 會後(2026-10-26)

- **PR #10(Zhexuan,API v2)已核准並 squash 合併為 `ade699b`。**在乾淨環境跑過,128 個測試通過、2 個跳過。
  - 安全審查:token 綁定 tenant、類別、對話與金鑰版本;別的 group 無法還原;關閉對話後兩種模式都無法還原;沒有機密寫進 log;沒設 `VG_TOKEN_KEYS` 時 v2 關閉,v1 不變。
  - 後續(B73):`[VGA]`、`[Item_1]` 這類一般的方括號文字會被當成 token 擋下,用真實信件示範前要修;Redis 掛掉時 `/readyz` 連帶把 v1 報成 degraded;idempotency 指紋是沒加鹽的雜湊;用不到的格式 1 程式;過長 purpose 的錯誤代碼不對。
- **客戶頁面** `meetings/client/2026-10-26/agenda-{en,zh}.html`:進度、各工作線的細節、Q1–Q7 與答案欄。

## 待定

- Anmol 報告 §7 提到透過教授申請的 $50 CMU OpenRouter 額度。2026-09-27 的決定是不向客戶提 CMU 管道。由 Mark 決定報告時跳過,或寄出前刪掉那句。
- Karina 把複核推進 PR #9(B74)。在那之前,客戶頁面寫「標註由 LLM 提出,再由人逐筆檢查」。
