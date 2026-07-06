"""
全流程自動化腳本
準備好 data/ 底下的原始 TXT 檔後執行此腳本，自動完成：
  1. TXT 轉 CSV、依年份拆分
  2. 清除舊資料庫資料
  3. 逐年模擬資料流入（2005 → 2006 → 2007）
  4. 自動化分析 + 圖表輸出（reports/charts/）
  5. GenAI 自動報告產出（reports/report_YYYYMMDD.md）
"""

import sys
import subprocess
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
import os

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

YEARS = [2005, 2006, 2007]


def run(cmd: list, label: str):
    """執行子程序，失敗時中止"""
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"\n[ERROR] {label} 失敗，流程中止")
        sys.exit(1)


def reset_mongodb():
    """清除 MongoDB 舊資料，確保從零開始"""
    print(f"\n{'='*50}")
    print(f"  重置 MongoDB")
    print(f"{'='*50}")
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB")]
    for col in ["daily_bets", "demographics", "user_metrics"]:
        db[col].drop()
        print(f"  已清除 {col}")


def main():
    print("\n" + "★" * 50)
    print("  全流程自動化 Pipeline 啟動")
    print("★" * 50)

    # Step 1：TXT 轉 CSV + 年份拆分
    run(
        [sys.executable, str(ROOT / "src" / "simulate_data.py")],
        "Step 1｜TXT 轉 CSV + 年份拆分"
    )

    # Step 2：重置 MongoDB
    reset_mongodb()

    # Step 3：逐年模擬資料流入
    for year in YEARS:
        run(
            [sys.executable, str(ROOT / "scripts" / "run_annual_pipeline.py"), str(year)],
            f"Step 3｜{year} 年資料流入"
        )

    # Step 4：自動化分析 + 圖表輸出
    run(
        [sys.executable, str(ROOT / "src" / "analysis.py")],
        "Step 4｜自動化分析 + 圖表輸出"
    )

    # Step 5：GenAI 自動報告
    run(
        [sys.executable, str(ROOT / "src" / "report_generator.py")],
        "Step 5｜GenAI 自動報告產出"
    )

    print("\n" + "=" * 50)
    print("  全流程完成")
    print(f"  報告輸出至：reports/")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
