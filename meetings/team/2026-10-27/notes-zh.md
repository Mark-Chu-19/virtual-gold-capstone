# 團隊會議,2026-10-27(週二)

在 10/26 客戶會議之後舉行。議程:[`agenda-zh.html`](agenda-zh.html)。英文版:[`notes-en.md`](notes-en.md)。客戶會議來源:[`notes-gemini-en.pdf`](../../client/2026-10-26/notes-gemini-en.pdf)。

## 10/26 客戶的決定

- **分級表核准**(Aarvin:嚴重程度表達正確,沒有阻礙)。Mark 說商業類別偏弱,請組員在 Slack 提議。
- **還原設計要改。**不由客戶產生請求 ID。改由伺服器在遮蔽時產生識別碼,和遮蔽後的文字一起回傳,客戶還原時再送回來。遮蔽只服務主要使用者(Inderpal)。
- **還原用加密**,每個對話與請求一把金鑰。
- **預計 Nov 2(週一)接上他們的 agent**,接著測試。
- **只用一個本地模型,不在執行時切換**(Aarvin)。
- 沒有答案的:Q1 細節(出生日期、交易對象、編號、Low 單獨出現時保留)、Q2 外洩目標、Q3 服務跑在哪裡、Q4 文件與路由、Q5 placeholder 細節、Q6 SOW 簽署。

Gemini 紀錄有錯(測試集數量、86 個 Low 項目、66% 是誰的規則、Qwen 的大小、金鑰的運作方式)。議程裡列了更正,Slack 摘要請照更正後的寫。

## 決定

1. **還原設計。**
   - 由伺服器產生識別碼。Zhexuan 說 v2 的修改週五(10/30)前做得完。
   - 名稱:**Session Hash ID**。
   - **每個請求一把**,由伺服器建立(選項 B)。
   - 目前用 **`mapping`** 模式。
   - Anmol 盡快把流程圖寄給 Aarvin。
   - 待確認:「每個請求一把」和名稱裡的「Session」方向不一致;agent 的回覆如果混了前幾輪的 placeholder,還原時要帶好幾個 ID。由 Anmol 和 Zhexuan 自己對齊,之後再確認。
2. **整合。****Nov 2(週一)只做合約測試,完整整合延後一週到 Nov 9**(選項 C)。
   - 原型的 prompt 搬進服務、服務架在哪裡,都要看 Anmol 向 CMU 申請的運算資源何時到位。
   - 資源到位後,Anmol 測幾個不同的模型,選最好的。
3. **分級表。**
   - Yudi 開了 **PR #11**(只改分級表),2026-10-28 審查後 squash 合併為 `6b1f3c7`,**main 現在是 policy 0.1.3**:22 類與 tier 和 `tier-table-client-review-en.docx` 一致。含 Presidio 130 個測試通過。
   - 8 項偵測修正留在 `feat/privacy-detection-fixes`,在 60 封開發信上逐項驗證後再合併。這個分支可以乾淨地合到 main 上(137 個測試通過)。
   - 兩個都給 Anmol 對接測試:main 當基準版,分支當修正版。
4. **Karina 的資料集(PR #9)改成 0.1.3。**2026-10-28 已在 PR #9 留言:
   - 11 個 `BANK_ACCOUNT` 改成 `ACCOUNT_NUMBER`。
   - 雇主的帳單地址改成 `ADDRESS_PUBLIC`。另外兩個辦公室地址要不要改,由 Karina 判斷。
   - README 從 0.1.1 改成 0.1.3。
   - 39 個 `ID_NUMBER` 和 1 個 `URL` 不用改。0.1.3 沒有它們的類別,`in_policy: false` / `tier: high` 正好和服務處理未知類別的方式一致。
   - 她的複核還沒推上來(B74)。
5. **Q1 的預設值**(出生日期、交易對象、編號、Low 單獨出現)沒有討論,Nov 2 再問客戶。

## 待辦

| 誰 | 做什麼 | 期限 |
|---|---|---|
| Zhexuan | v2 改成伺服器產生 Session Hash ID,每個請求一個,`mapping` 模式 | 10/30(週五) |
| Anmol | 流程圖寄給 Aarvin;寄出前先和 Zhexuan 對齊每個請求還是每個對話 | 盡快 |
| Anmol | CMU 資源;到位後把 prompt 搬進服務、部署、選模型 | 資源到位後 |
| Zhexuan | Nov 2 的合約測試 | 11/2(週一) |
| Karina | 依 PR #9 的留言改成 0.1.3;推上複核(B74);評分 60 封開發信 | |
| Yudi | 在 60 封開發信上驗證 8 項修正,再為 `feat/privacy-detection-fixes` 開 PR | |
| Mark | Slack 摘要(含 Gemini 的更正)與修訂後的時程;Nov 2 要問的問題,含 Q1 | |

## 待定

- 每個請求還是每個對話,以及 Session Hash ID 這個名稱合不合適(Anmol、Zhexuan)。
- CMU 資源沒有到位日期,所以 Nov 9 也不確定。Nov 2 的合約測試不需要 GPU,不必等資源。
- 選定模型沒有期限;Aarvin 要只用一個。
- CMU 在 10/26 已經在客戶面前提到。2026-09-27「不向客戶提 CMU 管道」的決定沒有正式重新討論。
