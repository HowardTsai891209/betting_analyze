"""
GenAI 自動化報告層
讀取 analysis.py 產出的 analysis_stats.json，
透過 Ollama 本地 LLM 產出自然語言報告並嵌入圖表
輸出：reports/report_YYYYMMDD.md
"""

import os
import json
import ollama
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT        = Path(__file__).parent.parent
MODEL       = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
STATS_FILE  = ROOT / "reports" / "analysis_stats.json"
REPORTS_DIR = ROOT / "reports"


# ── 資料載入 ──────────────────────────────────────────────────────────────────

def load_stats() -> dict:
    if not STATS_FILE.exists():
        raise FileNotFoundError("找不到 analysis_stats.json，請先執行 analysis.py")
    return json.loads(STATS_FILE.read_text(encoding="utf-8"))


# ── LLM 呼叫 ─────────────────────────────────────────────────────────────────

def ask_llm(prompt: str) -> str:
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return response["message"]["content"].strip()


# ── 各段落 Prompt ─────────────────────────────────────────────────────────────

def gen_cluster_section(cluster_summary: dict) -> str:
    rows = "\n".join([
        f"Cluster {k}: total_stake={v['total_stake']} EUR, net_loss={v['net_loss']} EUR, "
        f"active_days={v['active_days']} days, avg_daily_stake={v['avg_daily_stake']} EUR/day, "
        f"bet_frequency={v['bet_frequency']}"
        for k, v in cluster_summary.items()
    ])
    prompt = f"""You are a data analyst for an online casino.
Below are 4 player behavior clusters from K-Means analysis.
For each cluster, write a 2-3 sentence plain-language summary describing the player type and recommended business strategy.
Output in Traditional Chinese.

{rows}"""
    print("[LLM] 產出分群摘要...")
    return ask_llm(prompt)

def gen_arbitrage_section(arb: dict) -> str:
    prompt = f"""You are a risk analyst for an online casino.
Analysis result: {arb['count']} players ({arb['pct']}%) are long-term profitable (casino loses money to them).
The highest single player profit is {arb['max_profit']} EUR.
Top countries: {arb['top_countries']}.
Write a 3-4 sentence risk assessment paragraph in Traditional Chinese, identifying the key risk and suggesting action."""
    print("[LLM] 產出風控分析...")
    return ask_llm(prompt)

def gen_loss_chasing_section(chasing: list) -> str:
    rows = "\n".join([
        f"After {r['streak_days']} consecutive loss days: avg stake change = {r['avg_stake_change']} EUR"
        for r in chasing
    ])
    prompt = f"""You are a behavioral analyst for an online casino.
Below is data showing how player stakes change after consecutive losing days:

{rows}

Write a 3-4 sentence analysis in Traditional Chinese explaining the loss-chasing pattern and its business risk."""
    print("[LLM] 產出凹單行為分析...")
    return ask_llm(prompt)

def gen_lifespan_section(lifespan: dict) -> str:
    rows = "\n".join([f"{k}: {v} players" for k, v in lifespan.items()])
    prompt = f"""You are a retention analyst for an online casino.
Player lifespan distribution:

{rows}

Write a 3-4 sentence analysis in Traditional Chinese about churn risk and retention strategy recommendations."""
    print("[LLM] 產出生命週期分析...")
    return ask_llm(prompt)

def gen_executive_summary(stats: dict) -> str:
    arb     = stats["arbitrage"]
    chasing = stats["loss_chasing"]
    prompt = f"""You are a senior analyst presenting to the executive team of an online casino.
Key findings:
1. {arb['pct']}% of players are long-term profitable to themselves (risk to casino)
2. Players show clear loss-chasing after 4-5 consecutive losing days (stake increases by ~{chasing[-1]['avg_stake_change']:.0f} EUR on average)
3. 16.2% of players churn within 30 days

Write a concise 4-5 sentence executive summary in Traditional Chinese covering the main business risks and opportunities."""
    print("[LLM] 產出執行摘要...")
    return ask_llm(prompt)


# ── 組合報告（嵌入圖表） ──────────────────────────────────────────────────────

def build_report(sections: dict, stats: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    # 圖表路徑轉 Markdown 相對路徑
    def chart_link(keyword: str) -> str:
        for path in stats.get("charts", []):
            if keyword in path:
                return f"![chart]({path.replace(chr(92), '/')})"
        return ""

    return f"""# bwin 線上賭場玩家行為分析報告（AI 自動產出）

**產出日期**：{today}
**模型**：{MODEL}
**資料來源**：bwin × 哈佛醫學院，2005–2007 年

---

## 執行摘要

{sections['executive']}

---

## 1. 職業套利客風控警示

{sections['arbitrage']}

{chart_link('02_arbitrage')}

---

## 2. 凹單行為分析

{sections['loss_chasing']}

{chart_link('03_loss')}

---

## 3. 玩家生命週期與留存風險

{sections['lifespan']}

{chart_link('04_lifespan')}

---

## 4. K-Means 玩家分群摘要

{sections['clusters']}

{chart_link('06_kmeans_scatter')}

---

## 附錄：分析圖表

{chart_link('01_eda')}
{chart_link('05_kmeans_elbow')}

---

*本報告由 Ollama 本地 LLM（{MODEL}）自動產出，資料不離境，無需外部 API。*
"""


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print(f"[report_generator] 使用模型：{MODEL}")

    stats = load_stats()
    print(f"[載入] analysis_stats.json 讀取成功")

    sections = {
        "executive":    gen_executive_summary(stats),
        "arbitrage":    gen_arbitrage_section(stats["arbitrage"]),
        "loss_chasing": gen_loss_chasing_section(stats["loss_chasing"]),
        "lifespan":     gen_lifespan_section(stats["lifespan"]),
        "clusters":     gen_cluster_section(stats["cluster_summary"]),
    }

    report = build_report(sections, stats)

    out_path = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d')}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[完成] 報告已輸出：{out_path}")


if __name__ == "__main__":
    main()
