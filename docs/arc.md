【版本控制】Git

全專案以 Git 管理，分支策略：main / dev / feature/*
每層腳本（Shell / Python / Notebook）獨立提交，合併前須通過 pytest 單元測試。

【資料模擬層】TXT 轉 CSV + 拆分腳本（單次執行）

Step 1 — 格式轉換：
將兩份原始 TXT 檔轉為 CSV 格式：
- RawDataSet1_DemographicsCasinoTXT.txt → demographics.csv（常駐 /data/master/）
- RawDataSet2_DailyAggregCasinoTXT.txt  → daily_all.csv（暫存，供下一步使用）

Step 2 — 依年份拆分：
將 daily_all.csv 依 Date 欄位拆分為三個年度檔案，放置於 /data/raw/，
模擬真實環境中每年定期新增一批資料的情境：
- daily_2005.csv
- daily_2006.csv
- daily_2007.csv

【資料搬運層】Shell Script 自動化排程

以 cron 定時掃描 /data/raw/ 目錄，偵測到新年度 CSV 後自動搬移至 /data/processing/，
呼叫 Python 清理腳本，並將每次執行的成功或失敗狀態寫入 Log 檔（/logs/pipeline.log），確保數據流向可追蹤。

【資料處理層】Python (Pandas) 清理與轉置 + pytest 單元測試（同一 branch）

接收 Shell Script 傳入的檔案路徑，對原始資料進行清洗：
- Demographics：Country / Language 數字編碼 → 對照表解碼為實際國名與語言名稱
- DailyAggregation：標記 Winnings < 0 的異常記錄（後端對帳修正）、
  標記 Stake = 0 但 Bets > 0 的資料品質問題
- 計算衍生欄位：daily_GGR = Stake - Winnings、is_winning_day（GGR < 0 代表玩家贏錢）
- 促銷金過濾：JOIN Demographics 取得每位用戶的 Fstpdate（首次真實入金日），
  排除 Date < Fstpdate 的記錄，確保分析對象是「用自己的錢下注」的真實行為，
  而非系統贈送紅利期間的非代表性數據
- JOIN Demographics 主檔，補齊每筆日記錄的用戶人口屬性

pytest 單元測試覆蓋：
- 編碼解碼正確性（Country / Language 對照表）
- GGR 衍生欄位計算邊界值
- 促銷金過濾條件（Fstpdate 邊界）

輸出至 /data/done/：
- 原始 CSV 歸檔（e.g. daily_2005.csv）
- 清理後快照（e.g. daily_2005_cleaned.csv）

【資料儲存層】MongoDB (NoSQL) + MySQL (關聯式) 雙軌

MongoDB — 以 Python pymongo Bulk Insert，分三個 Collection：
- demographics：清理後的用戶主檔（含解碼後國籍、語言）
- daily_bets：清理後的逐日投注記錄（含衍生欄位與異常標記）
- user_metrics：由 Python 彙總的每位用戶行為指標（供 ML 與視覺化使用）

MySQL — 以 Python SQLAlchemy 寫入關聯式彙總表：
- summary_by_user：每位用戶的總投注額、總 GGR、活躍天數、分群標籤
- summary_by_country：依國籍彙總的投注規模與風險指標
（供 SQL 查詢驗證與報表使用，展示 NoSQL 與 RDBMS 並存的資料架構能力）

【分析層】Jupyter Notebook

直連 MongoDB，依序執行：
1. EDA：用戶分佈、投注規模、活躍天數基本統計
2. 職業套利客識別：net_loss 排名、地理分佈
3. 凹單行為分析：連輸後 Stake 變化的時序統計
4. 玩家生命週期分析：活躍壽命與流失輪廓
5. K-Means 分群：行為特徵向量聚類，輸出玩家分群標籤

【GenAI 自動化報告層】Ollama（本地 LLM）

以 Ollama 在本機運行開源模型（如 Llama 3 / Gemma 3），透過 Python ollama 套件呼叫，
將 Jupyter 分析結果結構化後送入 LLM，自動產出自然語言報告：
- K-Means 各分群的人話摘要（例：「此群玩家傾向於連輸後加倍投注，具高流失風險」）
- 異常用戶的風控說明段落
- 整體週期報告（Markdown 格式輸出，可直接嵌入內部系統）

資料不離境，無需外部 API，適合企業內部資料保護需求。

【視覺化層】Jupyter Notebook 內嵌圖表（Matplotlib / Seaborn）

分析結果以圖表呈現於 Notebook 中，涵蓋：
職業套利客地理分佈、玩家生命週期漏斗、凹單行為趨勢、K-Means 分群散佈圖。
