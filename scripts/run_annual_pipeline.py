"""
年度資料流入模擬
用法：python scripts/run_annual_pipeline.py <year>
範例：python scripts/run_annual_pipeline.py 2005

模擬真實環境中每年定期新增一批資料的情境：
1. 呼叫 cleaner.py 清理該年 CSV
2. 增量寫入 MongoDB / MySQL（保留歷年資料）
3. 印出當前累積統計
"""

import sys
import subprocess
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.db_loader import (
    get_mongo_db, get_mysql_engine,
    load_demographics, insert_incremental
)

VALID_YEARS = [2005, 2006, 2007]


def run_cleaner(year: int) -> Path:
    """呼叫 cleaner.py 清理該年原始 CSV"""
    raw_path     = ROOT / "data" / "raw"     / f"daily_{year}.csv"
    cleaned_path = ROOT / "data" / "done"    / f"daily_{year}_cleaned.csv"

    if not raw_path.exists():
        raise FileNotFoundError(f"找不到原始資料：{raw_path}")

    print(f"[Step 1] 清理 {year} 年資料...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "cleaner.py"), str(raw_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"cleaner.py 執行失敗")

    print(result.stdout.strip())
    return cleaned_path


def print_stats(db, year: int):
    """印出當前 MongoDB 累積統計"""
    total_daily = db["daily_bets"].count_documents({})
    total_users = db["user_metrics"].count_documents({})
    arb_count   = db["user_metrics"].count_documents({"net_loss": {"$lt": 0}})
    print(f"\n{'─'*45}")
    print(f"  {year} 年資料流入完成，當前累積狀態：")
    print(f"  日記錄總筆數  : {total_daily:,}")
    print(f"  用戶總數      : {total_users:,}")
    print(f"  長期獲利帳號  : {arb_count} 位（{arb_count/total_users*100:.1f}%）")
    print(f"{'─'*45}\n")


def main():
    if len(sys.argv) < 2:
        print("用法：python scripts/run_annual_pipeline.py <year>")
        print(f"可用年份：{VALID_YEARS}")
        sys.exit(1)

    year = int(sys.argv[1])
    if year not in VALID_YEARS:
        print(f"錯誤：年份必須是 {VALID_YEARS} 其中一個")
        sys.exit(1)

    print(f"\n{'='*45}")
    print(f"  年度 Pipeline 啟動：{year} 年")
    print(f"{'='*45}\n")

    # Step 1：清理
    cleaned_path = run_cleaner(year)

    # Step 2：載入清理後資料
    print(f"[Step 2] 載入清理後資料...")
    daily_new = pd.read_csv(cleaned_path)
    daily_new["Date"] = pd.to_datetime(daily_new["Date"])
    print(f"  {len(daily_new):,} 筆")

    # Step 3：增量寫入 MongoDB / MySQL
    print(f"[Step 3] 增量寫入資料庫...")
    db     = get_mongo_db()
    engine = get_mysql_engine()
    demo   = load_demographics()
    insert_incremental(db, engine, daily_new, demo, year)

    # Step 4：印出累積統計
    print_stats(db, year)


if __name__ == "__main__":
    main()
