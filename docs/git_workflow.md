# Git 工作流程（單人模擬團隊）

## 團隊實際怎麼用 Git

最常見的是 GitHub Flow：

```
main              ← 永遠是可上線的乾淨版本
  └─ feature/xxx  ← 開新功能
  └─ fix/xxx      ← 修 bug
```

流程：開 branch → 寫 code → 開 Pull Request → 隊友 code review → merge 回 main

---

## 本專案 Branch 規劃

對應 arc.md 每一層各開一個 feature branch，完成後 merge 回 main：

```bash
feature/data-simulation   # TXT→CSV 拆分腳本
feature/shell-pipeline    # Shell Script 自動化排程
feature/python-cleaner    # Pandas 清理與轉置
feature/pytest            # 單元測試
feature/mongodb-mysql     # 雙軌資料儲存
feature/jupyter-analysis  # EDA + K-Means
feature/ollama-report     # GenAI 自動化報告
```

---

## 操作步驟

### 初始化

```bash
git init
git add .
git commit -m "init: project structure"
git branch -M main
git remote add origin <你的 GitHub repo URL>
git push -u origin main
```

### 每層的開發流程

```bash
# 1. 從 main 開新 branch
git checkout -b feature/python-cleaner

# 2. 寫 code，分段 commit
git add src/cleaner.py
git commit -m "feat: decode Country/Language numeric codes to labels"

git add src/cleaner.py
git commit -m "feat: flag Winnings < 0 and Stake=0 anomaly records"

git add src/cleaner.py
git commit -m "feat: filter promo period records before Fstpdate"

# 3. push 到 GitHub
git push origin feature/python-cleaner

# 4. GitHub 上開 Pull Request → 自己 review → merge

# 5. merge 回 main（本機同步）
git checkout main
git pull origin main

# 6. 刪掉已合併的 branch（保持整潔）
git branch -d feature/python-cleaner
```

### --no-ff 的重要性

merge 時加 `--no-ff`，保留 merge commit，讓 git log 圖有分支痕跡：

```bash
git merge --no-ff feature/python-cleaner
```

不加的話會 fast-forward，歷史變成一條直線，看不出有用過 branch。

---

## GitHub Issues 接 Branch

在 GitHub 上先開 Issue，branch 名帶 issue 編號：

```bash
# GitHub Issue #5: 實作 Ollama 自動報告層
git checkout -b feature/5-ollama-report
```

這是團隊慣例，讓 branch 和需求可以對應追蹤。

---

## Commit Message 格式（Conventional Commits）

```
type: 簡短描述（英文）
```

| type | 用途 |
|------|------|
| feat | 新功能 |
| fix | 修 bug |
| test | 加測試 |
| refactor | 重構（不改行為） |
| docs | 文件 |
| chore | 雜項（設定檔、依賴） |

本專案範例：

```bash
git commit -m "feat: add Ollama report generator for K-Means cluster summary"
git commit -m "feat: bulk insert cleaned data to MongoDB and MySQL"
git commit -m "fix: exclude promo period records before Fstpdate"
git commit -m "test: add pytest for GGR boundary cases"
git commit -m "test: add pytest for Country/Language decode correctness"
git commit -m "chore: add requirements.txt and .gitignore"
```

---

## Tag 標記版本

```bash
git tag -a v1.0.0 -m "Pipeline complete: ingest + clean + MongoDB/MySQL"
git tag -a v1.1.0 -m "Add Jupyter EDA and K-Means clustering"
git tag -a v1.2.0 -m "Add Ollama GenAI report layer"

git push origin --tags
```

---

## .gitignore 記得加

```
/data/
/logs/
__pycache__/
*.pyc
.env
```

data 資料夾不要 commit（原始資料通常不進版控）。

---

## 面試展示重點

打開 GitHub repo，能看到：

- **Network graph**：有分支、有 merge，不是一條直線
- **Pull Request 列表**：每層一個 PR，有標題有描述
- **Commit 歷史**：Conventional Commits 格式，一眼看出做了什麼
- **Issues**：對應每個功能，展示需求追蹤習慣
- **Tags**：版本里程碑清楚
