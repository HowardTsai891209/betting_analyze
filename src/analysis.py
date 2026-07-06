"""
自動化分析腳本
從 MongoDB 讀取資料，執行全部分析並將圖表儲存至 reports/charts/
可直接執行或由 run_all.py 呼叫
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from pymongo import MongoClient, UpdateOne
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
CHARTS_DIR = ROOT / "reports" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")
plt.rcParams["figure.figsize"] = (12, 5)


# ── 資料載入 ──────────────────────────────────────────────────────────────────

def load_data():
    client  = MongoClient(os.getenv("MONGO_URI"))
    db      = client[os.getenv("MONGO_DB")]
    daily   = pd.DataFrame(list(db["daily_bets"].find({}, {"_id": 0})))
    demo    = pd.DataFrame(list(db["demographics"].find({}, {"_id": 0})))
    metrics = pd.DataFrame(list(db["user_metrics"].find({}, {"_id": 0})))
    daily["Date"] = pd.to_datetime(daily["Date"])
    print(f"[載入] daily={len(daily):,}  demo={len(demo):,}  metrics={len(metrics):,}")
    return db, daily, demo, metrics


# ── 圖表儲存工具 ──────────────────────────────────────────────────────────────

def save(fig, filename: str):
    path = CHARTS_DIR / filename
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [圖表] 已儲存：{path.name}")


# ── 1. EDA ───────────────────────────────────────────────────────────────────

def run_eda(metrics: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    axes[0].hist(np.log1p(metrics["total_stake"]), bins=50, color="steelblue", edgecolor="white")
    axes[0].set_title("Total Stake Distribution (log scale)")
    axes[0].set_xlabel("log(1 + Total Stake)  [EUR]")
    axes[0].set_ylabel("Number of Players")

    axes[1].hist(metrics["active_days"], bins=50, color="coral", edgecolor="white")
    axes[1].set_title("Active Days Distribution")
    axes[1].set_xlabel("Active Days  [days]")
    axes[1].set_ylabel("Number of Players")

    axes[2].hist(np.log1p(metrics["avg_daily_stake"]), bins=50, color="seagreen", edgecolor="white")
    axes[2].set_title("Avg Daily Stake Distribution (log scale)")
    axes[2].set_xlabel("log(1 + Avg Daily Stake)  [EUR/day]")
    axes[2].set_ylabel("Number of Players")

    fig.tight_layout()
    save(fig, "01_eda_distributions.png")


# ── 2. 職業套利客 ─────────────────────────────────────────────────────────────

def run_arbitrage(metrics: pd.DataFrame, demo: pd.DataFrame):
    arb = metrics[metrics["net_loss"] < 0].sort_values("net_loss")
    print(f"  長期獲利帳號：{len(arb)} 位（{len(arb)/len(metrics)*100:.1f}%）")

    arb_country = arb.merge(demo[["UserID", "Country"]], on="UserID", how="left")
    country_counts = arb_country["Country"].value_counts().head(15)

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.barplot(x=country_counts.values, y=country_counts.index,
                hue=country_counts.index, palette="Reds_r", legend=False, ax=ax)
    ax.set_title("Professional Arbitrage Players - Geographic Distribution (Top 15)")
    ax.set_xlabel("Number of Players")
    fig.tight_layout()
    save(fig, "02_arbitrage_geo.png")


# ── 3. 凹單行為 ───────────────────────────────────────────────────────────────

def run_loss_chasing(daily: pd.DataFrame):
    ds = daily.sort_values(["UserID", "Date"]).copy()
    ds["is_loss_day"] = ds["daily_GGR"] > 0
    ds["loss_streak"] = (
        ds.groupby("UserID")["is_loss_day"]
        .transform(lambda x: x * (x.groupby((x != x.shift()).cumsum()).cumcount() + 1))
    )
    ds["next_stake"]   = ds.groupby("UserID")["Stake"].shift(-1)
    ds["stake_change"] = ds["next_stake"] - ds["Stake"]

    streak = (
        ds[ds["loss_streak"].isin([1, 2, 3, 4, 5])]
        .groupby("loss_streak")["stake_change"].mean()
        .reset_index()
    )
    streak.columns = ["Consecutive Loss Days", "Avg Stake Change (Next Day)"]

    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=streak, x="Consecutive Loss Days", y="Avg Stake Change (Next Day)",
                hue="Consecutive Loss Days", palette="coolwarm", legend=False, ax=ax)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_title("Avg Stake Change After Consecutive Losses (Loss-Chasing Behavior)")
    ax.set_xlabel("Consecutive Loss Days  [days]")
    ax.set_ylabel("Avg Stake Change - Next Day  [EUR]")
    fig.tight_layout()
    save(fig, "03_loss_chasing.png")


# ── 4. 玩家生命週期 ───────────────────────────────────────────────────────────

def run_lifespan(metrics: pd.DataFrame, demo: pd.DataFrame):
    m = metrics.copy()
    m["first_active"]  = pd.to_datetime(m["first_active"])
    m["last_active"]   = pd.to_datetime(m["last_active"])
    m["lifespan_days"] = (m["last_active"] - m["first_active"]).dt.days

    bins   = [0, 30, 90, 180, 365, 9999]
    labels = ["<=30d", "31-90d", "91-180d", "181-365d", ">365d"]
    m["lifespan_group"] = pd.cut(m["lifespan_days"], bins=bins, labels=labels)
    lifespan_dist = m["lifespan_group"].value_counts().sort_index()

    short_lived    = m[m["lifespan_days"] <= 30]
    short_country  = short_lived.merge(demo[["UserID", "Country"]], on="UserID", how="left")
    top_country    = short_country["Country"].value_counts().head(10)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    lifespan_dist.plot(kind="bar", ax=axes[0], color="steelblue", edgecolor="white")
    axes[0].set_title("Player Lifespan Distribution")
    axes[0].set_xlabel("Active Lifespan  [days]")
    axes[0].set_ylabel("Number of Players")
    axes[0].tick_params(axis="x", rotation=30)

    sns.barplot(x=top_country.values, y=top_country.index,
                hue=top_country.index, palette="Blues_r", legend=False, ax=axes[1])
    axes[1].set_title("Short-Lived Players (<=30d) by Country")
    axes[1].set_xlabel("Number of Players")
    fig.tight_layout()
    save(fig, "04_lifespan.png")


# ── 5. K-Means 分群 ───────────────────────────────────────────────────────────

def run_kmeans(db, metrics: pd.DataFrame):
    features = ["total_stake", "net_loss", "active_days", "avg_daily_stake", "bet_frequency"]
    X = metrics[features].fillna(0)
    X_scaled = StandardScaler().fit_transform(X)

    # Elbow + Silhouette
    inertias, sil_scores = [], []
    for k in range(2, 8):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X_scaled)
        inertias.append(km.inertia_)
        sil_scores.append(silhouette_score(X_scaled, km.labels_))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(range(2, 8), inertias, "o-", color="steelblue")
    axes[0].set_title("Elbow Method")
    axes[0].set_xlabel("Number of Clusters (K)")
    axes[0].set_ylabel("Inertia  [within-cluster sum of squares]")

    axes[1].plot(range(2, 8), sil_scores, "o-", color="coral")
    axes[1].set_title("Silhouette Score")
    axes[1].set_xlabel("Number of Clusters (K)")
    axes[1].set_ylabel("Silhouette Score  [−1 to 1, higher = better]")
    fig.tight_layout()
    save(fig, "05_kmeans_elbow.png")

    # 最終分群 K=4
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    metrics["cluster"] = km.fit_predict(X_scaled)

    fig, ax = plt.subplots(figsize=(10, 6))
    scatter = ax.scatter(
        np.log1p(metrics["total_stake"]), metrics["net_loss"],
        c=metrics["cluster"], cmap="tab10", alpha=0.5, s=20
    )
    fig.colorbar(scatter, ax=ax, label="Cluster ID")
    ax.axhline(0, color="red", linewidth=0.8, linestyle="--", label="Break-even (net_loss = 0)")
    ax.set_title("K-Means Player Segmentation (log total_stake vs net_loss)")
    ax.set_xlabel("log(1 + Total Stake)  [EUR]")
    ax.set_ylabel("Net Loss  [EUR]  (negative = player wins)")
    ax.legend()
    fig.tight_layout()
    save(fig, "06_kmeans_scatter.png")

    # 分群標籤回寫 MongoDB
    updates = [
        UpdateOne({"UserID": int(row.UserID)}, {"$set": {"cluster": int(row.cluster)}})
        for row in metrics[["UserID", "cluster"]].itertuples()
    ]
    db["user_metrics"].bulk_write(updates)
    print(f"  分群標籤已回寫 MongoDB，各群人數：")
    print(f"  {metrics['cluster'].value_counts().sort_index().to_dict()}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def export_stats(metrics: pd.DataFrame, daily: pd.DataFrame, demo: pd.DataFrame):
    """將關鍵分析結果輸出為 JSON，供 report_generator.py 使用"""

    # 套利客
    arb = metrics[metrics["net_loss"] < 0]
    arb_country = arb.merge(demo[["UserID", "Country"]], on="UserID", how="left")
    top_countries = arb_country["Country"].value_counts().head(5).to_dict()

    # 凹單
    ds = daily.sort_values(["UserID", "Date"]).copy()
    ds["is_loss_day"]  = ds["daily_GGR"] > 0
    ds["loss_streak"]  = (
        ds.groupby("UserID")["is_loss_day"]
        .transform(lambda x: x * (x.groupby((x != x.shift()).cumsum()).cumcount() + 1))
    )
    ds["next_stake"]   = ds.groupby("UserID")["Stake"].shift(-1)
    ds["stake_change"] = ds["next_stake"] - ds["Stake"]
    chasing = (
        ds[ds["loss_streak"].isin([1, 2, 3, 4, 5])]
        .groupby("loss_streak")["stake_change"].mean().round(2)
        .to_dict()
    )

    # 生命週期
    m = metrics.copy()
    m["first_active"]  = pd.to_datetime(m["first_active"])
    m["last_active"]   = pd.to_datetime(m["last_active"])
    m["lifespan_days"] = (m["last_active"] - m["first_active"]).dt.days
    bins   = [0, 30, 90, 180, 365, 9999]
    labels = ["<=30d", "31-90d", "91-180d", "181-365d", ">365d"]
    m["lifespan_group"] = pd.cut(m["lifespan_days"], bins=bins, labels=labels)
    lifespan = {str(k): int(v) for k, v in m["lifespan_group"].value_counts().sort_index().items()}

    # 分群摘要
    features = ["total_stake", "net_loss", "active_days", "avg_daily_stake", "bet_frequency"]
    cluster_summary = {}
    if "cluster" in metrics.columns:
        cluster_summary = {
            str(k): {f: round(v, 2) for f, v in row.items()}
            for k, row in metrics.groupby("cluster")[features].mean().to_dict(orient="index").items()
        }

    stats = {
        "arbitrage": {
            "count": len(arb),
            "pct": round(len(arb) / len(metrics) * 100, 1),
            "max_profit": round(float(abs(arb["net_loss"].min())), 2),
            "top_countries": top_countries,
        },
        "loss_chasing": [{"streak_days": int(k), "avg_stake_change": float(v)} for k, v in chasing.items()],
        "lifespan": lifespan,
        "cluster_summary": cluster_summary,
        "charts": [str(p.relative_to(ROOT)) for p in sorted(CHARTS_DIR.glob("*.png"))],
    }

    out = ROOT / "reports" / "analysis_stats.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [統計] 已輸出：{out.name}")


def main():
    print("\n[analysis] 開始執行分析...")
    db, daily, demo, metrics = load_data()

    print("[1/5] EDA")
    run_eda(metrics)

    print("[2/5] 職業套利客")
    run_arbitrage(metrics, demo)

    print("[3/5] 凹單行為")
    run_loss_chasing(daily)

    print("[4/5] 玩家生命週期")
    run_lifespan(metrics, demo)

    print("[5/5] K-Means 分群")
    run_kmeans(db, metrics)

    # 重新載入含 cluster 欄位的 metrics
    _, _, demo2, metrics2 = load_data()
    export_stats(metrics2, daily, demo2)

    print(f"\n[analysis] 完成，圖表輸出至：{CHARTS_DIR}")


if __name__ == "__main__":
    main()
