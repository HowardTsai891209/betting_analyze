"""
雙軌資料儲存
MongoDB  — demographics / daily_bets / user_metrics（原始與行為指標）
MySQL    — summary_by_user / summary_by_country（彙總報表）
"""

import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import create_engine, text

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DONE = ROOT / "data" / "done"
DATA_MASTER = ROOT / "data" / "master"


# ── 連線 ─────────────────────────────────────────────────────────────────────

def get_mongo_db():
    client = MongoClient(os.getenv("MONGO_URI"))
    return client[os.getenv("MONGO_DB")]

def get_mysql_engine():
    user = os.getenv("MYSQL_USER")
    pw   = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST")
    port = os.getenv("MYSQL_PORT", 3306)
    db   = os.getenv("MYSQL_DB")
    return create_engine(f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}")


# ── 資料準備 ──────────────────────────────────────────────────────────────────

def load_all_cleaned() -> pd.DataFrame:
    """讀取 data/done/ 底下所有年度清理檔，合併為單一 DataFrame"""
    files = sorted(DATA_DONE.glob("daily_*_cleaned.csv"))
    if not files:
        raise FileNotFoundError("找不到清理後的 CSV，請先執行 cleaner.py")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"])
    print(f"[載入] 日記錄共 {len(df)} 筆，來源：{[f.name for f in files]}")
    return df

def load_demographics() -> pd.DataFrame:
    df = pd.read_csv(DATA_MASTER / "demographics.csv")
    for col in ["RegDate", "Fstcadate", "Fstpdate"]:
        df[col] = pd.to_datetime(df[col])
    return df

def compute_user_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    """彙總每位用戶的行為指標，供 ML 與視覺化使用"""
    grp = daily.groupby("UserID")
    metrics = pd.DataFrame({
        "total_stake":     grp["Stake"].sum(),
        "total_winnings":  grp["Winnings"].sum(),
        "total_GGR":       grp["daily_GGR"].sum(),
        "net_loss":        grp["Stake"].sum() - grp["Winnings"].sum(),
        "active_days":     grp["Date"].nunique(),
        "total_bets":      grp["Bets"].sum(),
        "avg_daily_stake": grp["Stake"].mean(),
        "first_active":    grp["Date"].min(),
        "last_active":     grp["Date"].max(),
    }).reset_index()

    # 投注密度：活躍天數 / 總間隔天數
    metrics["interval_days"] = (
        (metrics["last_active"] - metrics["first_active"]).dt.days + 1
    )
    metrics["bet_frequency"] = (
        metrics["active_days"] / metrics["interval_days"]
    ).round(4)

    return metrics


# ── MongoDB 寫入 ──────────────────────────────────────────────────────────────

def insert_mongo(db, daily: pd.DataFrame, demo: pd.DataFrame, metrics: pd.DataFrame):
    # 日期欄位轉為 Python datetime（MongoDB 才能正確儲存）
    daily_copy = daily.copy()
    daily_copy["Date"] = daily_copy["Date"].dt.to_pydatetime()

    demo_copy = demo.copy()
    for col in ["RegDate", "Fstcadate", "Fstpdate"]:
        demo_copy[col] = demo_copy[col].dt.to_pydatetime()

    metrics_copy = metrics.copy()
    metrics_copy["first_active"] = metrics_copy["first_active"].dt.to_pydatetime()
    metrics_copy["last_active"]  = metrics_copy["last_active"].dt.to_pydatetime()

    for name, df in [
        ("demographics", demo_copy),
        ("daily_bets",   daily_copy),
        ("user_metrics", metrics_copy),
    ]:
        col = db[name]
        col.drop()  # 重新寫入前清空，避免重複
        records = df.to_dict("records")
        col.insert_many(records)
        print(f"[MongoDB] {name}: 寫入 {len(records)} 筆")


# ── MySQL 寫入 ────────────────────────────────────────────────────────────────

def insert_mysql(engine, metrics: pd.DataFrame, daily: pd.DataFrame):
    # summary_by_user：每位用戶彙總
    summary_user = metrics[[
        "UserID", "total_stake", "total_GGR", "net_loss",
        "active_days", "avg_daily_stake", "bet_frequency"
    ]].copy()
    summary_user["cluster_label"] = None  # K-Means 分群後填入

    summary_user.to_sql(
        "summary_by_user", engine,
        if_exists="replace", index=False
    )
    print(f"[MySQL] summary_by_user: 寫入 {len(summary_user)} 筆")

    # summary_by_country：依國籍彙總
    summary_country = (
        daily.groupby("Country")
        .agg(
            user_count   =("UserID",    "nunique"),
            total_stake  =("Stake",     "sum"),
            total_GGR    =("daily_GGR", "sum"),
            avg_net_loss =("daily_GGR", "mean"),
        )
        .reset_index()
    )

    summary_country.to_sql(
        "summary_by_country", engine,
        if_exists="replace", index=False
    )
    print(f"[MySQL] summary_by_country: 寫入 {len(summary_country)} 筆")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    daily   = load_all_cleaned()
    demo    = load_demographics()
    metrics = compute_user_metrics(daily)

    print("\n── MongoDB ──")
    db = get_mongo_db()
    insert_mongo(db, daily, demo, metrics)

    print("\n── MySQL ──")
    engine = get_mysql_engine()
    insert_mysql(engine, metrics, daily)

    print("\n完成")


if __name__ == "__main__":
    main()
