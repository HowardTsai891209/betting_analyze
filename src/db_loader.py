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

COUNTRY_MAP = {
    4: "Afghanistan", 8: "Albania", 10: "Antarctica", 12: "Algeria",
    20: "Andorra", 24: "Angola", 32: "Argentina", 36: "Australia",
    40: "Austria", 56: "Belgium", 76: "Brazil", 100: "Bulgaria",
    124: "Canada", 144: "Sri Lanka", 152: "Chile", 156: "China",
    158: "Taiwan", 191: "Croatia", 196: "Cyprus", 203: "Czech Republic",
    208: "Denmark", 246: "Finland", 250: "France", 276: "Germany",
    300: "Greece", 348: "Hungary", 356: "India", 372: "Ireland",
    376: "Israel", 380: "Italy", 392: "Japan", 410: "Korea (South)",
    440: "Lithuania", 442: "Luxembourg", 484: "Mexico", 528: "Holland",
    554: "New Zealand", 578: "Norway", 616: "Poland", 620: "Portugal",
    642: "Romania", 643: "Russian Federation", 702: "Singapore",
    703: "Slovakia", 705: "Slovenia", 710: "South Africa", 724: "Spain",
    752: "Sweden", 756: "Switzerland", 792: "Turkey", 804: "Ukraine",
    826: "United Kingdom", 840: "USA", 891: "Serbia and Montenegro",
    1000: "Undefined",
}

LANGUAGE_MAP = {
    1: "English", 2: "German", 3: "Italian", 4: "Spanish",
    5: "Swedish", 6: "French", 7: "Turkish", 8: "Greek",
    9: "Polish", 10: "Norwegian", 11: "Danish", 12: "Catalan",
    13: "Czech", 14: "Hungarian", 15: "Dutch", 16: "Portuguese",
    17: "Russian", 18: "Slovenian", 19: "Croatian", 20: "Slovak",
    21: "Simple Chinese", 22: "Traditional Chinese",
}


def load_demographics() -> pd.DataFrame:
    df = pd.read_csv(DATA_MASTER / "demographics.csv")
    df["Country"]  = df["Country"].map(COUNTRY_MAP).fillna("Unknown")
    df["Language"] = df["Language"].map(LANGUAGE_MAP).fillna("Unknown")
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


# ── 增量寫入（年度模擬用） ────────────────────────────────────────────────────

def insert_incremental(db, engine, daily_new: pd.DataFrame, demo: pd.DataFrame, year: int):
    """
    增量模式：只插入新年度資料，不清空舊資料
    - daily_bets：先刪除該年舊記錄再插入（idempotent，可重跑）
    - demographics：只插入不存在的用戶（upsert by UserID）
    - user_metrics：從 MongoDB 全量 daily_bets 重新計算
    - MySQL 彙總表：從最新 user_metrics 重新計算
    """
    from pymongo import UpdateOne

    # 1. daily_bets：刪除該年舊記錄，插入新記錄
    start = pd.Timestamp(f"{year}-01-01")
    end   = pd.Timestamp(f"{year}-12-31 23:59:59")
    deleted = db["daily_bets"].delete_many({"Date": {"$gte": start, "$lte": end}}).deleted_count
    if deleted:
        print(f"[MongoDB] daily_bets: 清除 {year} 年舊記錄 {deleted} 筆")

    daily_copy = daily_new.copy()
    daily_copy["Date"] = daily_copy["Date"].dt.to_pydatetime()
    db["daily_bets"].insert_many(daily_copy.to_dict("records"))
    print(f"[MongoDB] daily_bets: 新增 {year} 年 {len(daily_copy)} 筆，累計 {db['daily_bets'].count_documents({})} 筆")

    # 2. demographics：只插入不存在的用戶
    demo_copy = demo.copy()
    for col in ["RegDate", "Fstcadate", "Fstpdate"]:
        demo_copy[col] = demo_copy[col].dt.to_pydatetime()

    existing_ids = set(db["demographics"].distinct("UserID"))
    new_users = demo_copy[~demo_copy["UserID"].isin(existing_ids)]
    if len(new_users):
        db["demographics"].insert_many(new_users.to_dict("records"))
    print(f"[MongoDB] demographics: 新增 {len(new_users)} 筆，累計 {db['demographics'].count_documents({})} 筆")

    # 3. user_metrics：從 MongoDB 全量 daily_bets 重新計算（含歷年累積）
    all_daily = pd.DataFrame(list(db["daily_bets"].find({}, {"_id": 0})))
    all_daily["Date"] = pd.to_datetime(all_daily["Date"])
    metrics = compute_user_metrics(all_daily)

    metrics_copy = metrics.copy()
    metrics_copy["first_active"] = metrics_copy["first_active"].dt.to_pydatetime()
    metrics_copy["last_active"]  = metrics_copy["last_active"].dt.to_pydatetime()
    db["user_metrics"].drop()
    db["user_metrics"].insert_many(metrics_copy.to_dict("records"))
    print(f"[MongoDB] user_metrics: 重新計算，共 {len(metrics)} 筆")

    # 4. MySQL：從最新 user_metrics 重新計算
    insert_mysql(engine, metrics, all_daily)


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
