"""
Step 1: Convert raw TXT files to CSV
Step 2: Split daily data by year to simulate annual data ingestion
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_MASTER = ROOT / "data" / "master"

TXT_DEMOGRAPHICS = ROOT / "data" / "RawDataSet1_DemographicsCasinoTXT.txt"
TXT_DAILY = ROOT / "data" / "RawDataSet2_DailyAggregCasinoTXT.txt"


def convert_demographics():
    df = pd.read_csv(TXT_DEMOGRAPHICS, sep="\t")
    out = DATA_MASTER / "demographics.csv"
    df.to_csv(out, index=False)
    print(f"[OK] demographics.csv → {out}  ({len(df)} rows)")


def convert_and_split_daily():
    df = pd.read_csv(TXT_DAILY, sep="\t")
    df["Date"] = pd.to_datetime(df["Date"])
    df["Year"] = df["Date"].dt.year

    # Save full file temporarily (not needed after split, but useful for debug)
    all_out = DATA_RAW / "daily_all.csv"
    df.drop(columns="Year").to_csv(all_out, index=False)
    print(f"[OK] daily_all.csv → {all_out}  ({len(df)} rows)")

    for year, group in df.groupby("Year"):
        out = DATA_RAW / f"daily_{year}.csv"
        group.drop(columns="Year").to_csv(out, index=False)
        print(f"[OK] daily_{year}.csv → {out}  ({len(group)} rows)")


if __name__ == "__main__":
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DATA_MASTER.mkdir(parents=True, exist_ok=True)

    convert_demographics()
    convert_and_split_daily()
