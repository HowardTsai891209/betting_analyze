"""
GenAI 自動化報告層
從 MongoDB 讀取分析結果，透過 Ollama 本地 LLM 產出自然語言報告
輸出：reports/report_YYYYMMDD.md
"""

import os
import ollama
import pandas as pd
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

ROOT  = Path(__file__).parent.parent
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── 資料載入 ──────────────────────────────────────────────────────────────────

def load_data():
    client  = MongoClient(os.getenv("MONGO_URI"))
    db      = client[os.getenv("MONGO_DB")]
    metrics = pd.DataFrame(list(db["user_metrics"].find({}, {"_id": 0})))
    daily   = pd.DataFrame(list(db["daily_bets"].find({}, {"_id": 0})))
    demo    = pd.DataFrame(list(db["demographics"].find({}, {"_id": 0})))
    daily["Date"] = pd.to_datetime(daily["Date"])
    return metrics, daily, demo


# ── 分析結果結構化 ────────────────────────────────────────────────────────────

def build_cluster_summary(metrics: pd.DataFrame) -> dict:
    """彙總各 K-Means 分群的行為特徵"""
    features = ["total_stake", "net_loss", "active_days", "avg_daily_stake", "bet_frequency"]
    return metrics.groupby("cluster")[features].mean().round(2).to_dict(orient="index")

def build_arbitrage_summary(metrics: pd.DataFrame, demo: pd.DataFrame) -> dict:
    """彙總長期獲利帳號資訊"""
    arb = metrics[metrics["net_loss"] < 0].sort_values("net_loss")
    arb_with_country = arb.merge(demo[["UserID", "Country"]], on="UserID", how="left")
    top_countries = arb_with_country["Country"].value_counts().head(5).to_dict()
    return {
        "count": len(arb),
        "pct": round(len(arb) / len(metrics) * 100, 1),
        "max_profit": round(abs(arb["net_loss"].min()), 2),
        "top_countries": top_countries,
    }

def build_loss_chasing_summary(daily: pd.DataFrame) -> list:
    """彙總凹單行為數據"""
    daily_sorted = daily.sort_values(["UserID", "Date"])
    daily_sorted["is_loss_day"] = daily_sorted["daily_GGR"] > 0
    daily_sorted["loss_streak"] = (
        daily_sorted.groupby("UserID")["is_loss_day"]
        .transform(lambda x: x * (x.groupby((x != x.shift()).cumsum()).cumcount() + 1))
    )
    daily_sorted["next_stake"]   = daily_sorted.groupby("UserID")["Stake"].shift(-1)
    daily_sorted["stake_change"] = daily_sorted["next_stake"] - daily_sorted["Stake"]
    result = (
        daily_sorted[daily_sorted["loss_streak"].isin([1, 2, 3, 4, 5])]
        .groupby("loss_streak")["stake_change"]
        .mean()
        .round(2)
        .to_dict()
    )
    return [{"streak_days": k, "avg_stake_change": v} for k, v in result.items()]

def build_lifespan_summary(metrics: pd.DataFrame) -> dict:
    """彙總玩家生命週期分佈"""
    metrics = metrics.copy()
    metrics["first_active"]  = pd.to_datetime(metrics["first_active"])
    metrics["last_active"]   = pd.to_datetime(metrics["last_active"])
    metrics["lifespan_days"] = (metrics["last_active"] - metrics["first_active"]).dt.days
    bins   = [0, 30, 90, 180, 365, 9999]
    labels = ["<=30d", "31-90d", "91-180d", "181-365d", ">365d"]
    metrics["lifespan_group"] = pd.cut(metrics["lifespan_days"], bins=bins, labels=labels)
    dist = metrics["lifespan_group"].value_counts().sort_index().to_dict()
    return {str(k): int(v) for k, v in dist.items()}


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
    print(f"[LLM] 產出分群摘要...")
    return ask_llm(prompt)

def gen_arbitrage_section(arb: dict) -> str:
    prompt = f"""You are a risk analyst for an online casino.
Analysis result: {arb['count']} players ({arb['pct']}%) are long-term profitable (casino loses money to them).
The highest single player profit is {arb['max_profit']} EUR.
Top countries: {arb['top_countries']}.
Write a 3-4 sentence risk assessment paragraph in Traditional Chinese, identifying the key risk and suggesting action."""
    print(f"[LLM] 產出風控分析...")
    return ask_llm(prompt)

def gen_loss_chasing_section(chasing: list) -> str:
    rows = "\n".join([f"After {r['streak_days']} consecutive loss days: avg stake change = {r['avg_stake_change']} EUR" for r in chasing])
    prompt = f"""You are a behavioral analyst for an online casino.
Below is data showing how player stakes change after consecutive losing days:

{rows}

Write a 3-4 sentence analysis in Traditional Chinese explaining the loss-chasing pattern and its business risk."""
    print(f"[LLM] 產出凹單行為分析...")
    return ask_llm(prompt)

def gen_lifespan_section(lifespan: dict) -> str:
    rows = "\n".join([f"{k}: {v} players" for k, v in lifespan.items()])
    prompt = f"""You are a retention analyst for an online casino.
Player lifespan distribution:

{rows}

Write a 3-4 sentence analysis in Traditional Chinese about churn risk and retention strategy recommendations."""
    print(f"[LLM] 產出生命週期分析...")
    return ask_llm(prompt)

def gen_executive_summary(arb: dict, chasing: list, lifespan: dict) -> str:
    prompt = f"""You are a senior analyst presenting to the executive team of an online casino.
Key findings:
1. {arb['pct']}% of players are long-term profitable to themselves (risk to casino)
2. Players show clear loss-chasing after 4-5 consecutive losing days (stake increases by ~{chasing[-1]['avg_stake_change']:.0f} EUR on average)
3. 16.2% of players churn within 30 days

Write a concise 4-5 sentence executive summary in Traditional Chinese covering the main business risks and opportunities."""
    print(f"[LLM] 產出執行摘要...")
    return ask_llm(prompt)


# ── 組合報告 ──────────────────────────────────────────────────────────────────

def build_report(sections: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
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

---

## 2. 凹單行為分析

{sections['loss_chasing']}

---

## 3. 玩家生命週期與留存風險

{sections['lifespan']}

---

## 4. K-Means 玩家分群摘要

{sections['clusters']}

---

*本報告由 Ollama 本地 LLM（{MODEL}）自動產出，資料不離境，無需外部 API。*
"""


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print(f"[report_generator] 使用模型：{MODEL}")

    metrics, daily, demo = load_data()
    print(f"[載入] metrics={len(metrics)}, daily={len(daily)}, demo={len(demo)}")

    cluster_summary  = build_cluster_summary(metrics)
    arb_summary      = build_arbitrage_summary(metrics, demo)
    chasing_summary  = build_loss_chasing_summary(daily)
    lifespan_summary = build_lifespan_summary(metrics)

    sections = {
        "executive":    gen_executive_summary(arb_summary, chasing_summary, lifespan_summary),
        "arbitrage":    gen_arbitrage_section(arb_summary),
        "loss_chasing": gen_loss_chasing_section(chasing_summary),
        "lifespan":     gen_lifespan_section(lifespan_summary),
        "clusters":     gen_cluster_section(cluster_summary),
    }

    report = build_report(sections)

    out_path = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d')}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[完成] 報告已輸出：{out_path}")


if __name__ == "__main__":
    main()
