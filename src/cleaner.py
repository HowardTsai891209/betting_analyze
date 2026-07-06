"""
資料清理腳本
由 pipeline.sh 呼叫，接收單一年度 CSV 路徑作為參數
輸出清理後的快照至 data/done/
"""

import sys
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_MASTER = ROOT / "data" / "master"
DATA_DONE = ROOT / "data" / "done"

# ── 國籍對照表（來源：codebook Appendix 1） ──────────────────────────────────
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

# ── 語言對照表（來源：codebook Appendix 2） ──────────────────────────────────
LANGUAGE_MAP = {
    1: "English", 2: "German", 3: "Italian", 4: "Spanish",
    5: "Swedish", 6: "French", 7: "Turkish", 8: "Greek",
    9: "Polish", 10: "Norwegian", 11: "Danish", 12: "Catalan",
    13: "Czech", 14: "Hungarian", 15: "Dutch", 16: "Portuguese",
    17: "Russian", 18: "Slovenian", 19: "Croatian", 20: "Slovak",
    21: "Simple Chinese", 22: "Traditional Chinese",
}


def load_demographics() -> pd.DataFrame:
    """讀取用戶主檔，解碼國籍與語言，回傳供 JOIN 使用"""
    df = pd.read_csv(DATA_MASTER / "demographics.csv")
    df["Country"] = df["Country"].map(COUNTRY_MAP).fillna("Unknown")
    df["Language"] = df["Language"].map(LANGUAGE_MAP).fillna("Unknown")
    df["Fstpdate"] = pd.to_datetime(df["Fstpdate"])
    return df


def clean_daily(df: pd.DataFrame, demo: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])

    # 標記異常：Winnings 負值（後端對帳修正）
    df["is_negative_winnings"] = df["Winnings"] < 0

    # 標記異常：Stake = 0 但 Bets > 0（資料品質問題）
    df["is_zero_stake_with_bets"] = (df["Stake"] == 0) & (df["Bets"] > 0)

    # 衍生欄位：每日 GGR（賭場毛利）= Stake - Winnings
    df["daily_GGR"] = df["Stake"] - df["Winnings"]

    # 衍生欄位：玩家是否當日獲利（GGR < 0 代表玩家贏錢）
    df["is_winning_day"] = df["daily_GGR"] < 0

    # 促銷金過濾：排除 Date < Fstpdate 的記錄（用促銷金下注，非真實行為）
    fstpdate_map = demo.set_index("UserID")["Fstpdate"]
    df["Fstpdate"] = df["UserID"].map(fstpdate_map)
    before_filter = len(df)
    df = df[df["Date"] >= df["Fstpdate"]].copy()
    print(f"  促銷金過濾：移除 {before_filter - len(df)} 筆記錄")

    # JOIN Demographics：補齊用戶人口屬性
    demo_cols = demo[["UserID", "Country", "Language", "Gender"]]
    df = df.merge(demo_cols, on="UserID", how="left")

    df.drop(columns=["Fstpdate"], inplace=True)
    return df


def main(file_path: str):
    path = Path(file_path)
    filename = path.stem  # e.g. "daily_2005"

    print(f"[cleaner] 處理：{path.name}")

    DATA_DONE.mkdir(parents=True, exist_ok=True)

    demo = load_demographics()

    # 清理
    df_raw = pd.read_csv(path)
    cleaned = clean_daily(df_raw, demo)

    # 原始檔歸檔至 data/done/
    archive_path = DATA_DONE / path.name
    import shutil
    shutil.copy(path, archive_path)
    print(f"  原始檔歸檔 → {archive_path}")

    # 清理後快照輸出
    cleaned_path = DATA_DONE / f"{filename}_cleaned.csv"
    cleaned.to_csv(cleaned_path, index=False)
    print(f"  清理完成 → {cleaned_path}  ({len(cleaned)} 筆)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python cleaner.py <csv_path>")
        sys.exit(1)
    main(sys.argv[1])
