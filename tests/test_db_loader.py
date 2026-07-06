import pandas as pd
import pytest
from src.db_loader import compute_user_metrics


def make_daily(records: list) -> pd.DataFrame:
    """建立測試用 daily DataFrame"""
    df = pd.DataFrame(records)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


# ── 基本計算正確性 ────────────────────────────────────────────────────────────

def test_total_stake_and_winnings():
    daily = make_daily([
        {"UserID": 1, "Date": "2005-01-01", "Stake": 100, "Winnings": 40, "Bets": 3, "daily_GGR": 60},
        {"UserID": 1, "Date": "2005-01-02", "Stake": 200, "Winnings": 50, "Bets": 5, "daily_GGR": 150},
    ])
    result = compute_user_metrics(daily)
    row = result[result["UserID"] == 1].iloc[0]

    assert row["total_stake"]    == pytest.approx(300.0)
    assert row["total_winnings"] == pytest.approx(90.0)

def test_net_loss_equals_stake_minus_winnings():
    daily = make_daily([
        {"UserID": 1, "Date": "2005-01-01", "Stake": 100, "Winnings": 40, "Bets": 3, "daily_GGR": 60},
    ])
    result = compute_user_metrics(daily)
    row = result[result["UserID"] == 1].iloc[0]

    assert row["net_loss"] == pytest.approx(row["total_stake"] - row["total_winnings"])

def test_net_loss_negative_when_player_wins():
    # Winnings > Stake → net_loss < 0 → 玩家獲利
    daily = make_daily([
        {"UserID": 1, "Date": "2005-01-01", "Stake": 50, "Winnings": 200, "Bets": 2, "daily_GGR": -150},
    ])
    result = compute_user_metrics(daily)
    assert result[result["UserID"] == 1].iloc[0]["net_loss"] < 0


# ── 活躍天數 ──────────────────────────────────────────────────────────────────

def test_active_days_counts_unique_dates():
    daily = make_daily([
        {"UserID": 1, "Date": "2005-01-01", "Stake": 100, "Winnings": 0, "Bets": 1, "daily_GGR": 100},
        {"UserID": 1, "Date": "2005-01-01", "Stake": 50,  "Winnings": 0, "Bets": 1, "daily_GGR": 50},  # 同一天
        {"UserID": 1, "Date": "2005-01-03", "Stake": 80,  "Winnings": 0, "Bets": 2, "daily_GGR": 80},
    ])
    result = compute_user_metrics(daily)
    # 同一天重複只算 1 天，共 2 個不同日期
    assert result[result["UserID"] == 1].iloc[0]["active_days"] == 2


# ── bet_frequency 邊界值 ──────────────────────────────────────────────────────

def test_bet_frequency_single_day():
    # 只有一天記錄：interval_days=1，active_days=1 → bet_frequency=1.0
    daily = make_daily([
        {"UserID": 1, "Date": "2005-06-01", "Stake": 100, "Winnings": 50, "Bets": 3, "daily_GGR": 50},
    ])
    result = compute_user_metrics(daily)
    assert result[result["UserID"] == 1].iloc[0]["bet_frequency"] == pytest.approx(1.0)

def test_bet_frequency_sparse_player():
    # 5 天間隔內只有 2 天有下注 → bet_frequency = 2/5 = 0.4
    daily = make_daily([
        {"UserID": 1, "Date": "2005-01-01", "Stake": 100, "Winnings": 0, "Bets": 1, "daily_GGR": 100},
        {"UserID": 1, "Date": "2005-01-05", "Stake": 100, "Winnings": 0, "Bets": 1, "daily_GGR": 100},
    ])
    result = compute_user_metrics(daily)
    # interval_days = (Jan5 - Jan1).days + 1 = 5，active_days = 2
    assert result[result["UserID"] == 1].iloc[0]["bet_frequency"] == pytest.approx(0.4)


# ── 多用戶隔離 ────────────────────────────────────────────────────────────────

def test_multiple_users_are_independent():
    daily = make_daily([
        {"UserID": 1, "Date": "2005-01-01", "Stake": 100, "Winnings": 40, "Bets": 3, "daily_GGR": 60},
        {"UserID": 2, "Date": "2005-01-01", "Stake": 500, "Winnings": 100, "Bets": 10, "daily_GGR": 400},
    ])
    result = compute_user_metrics(daily)

    assert result[result["UserID"] == 1].iloc[0]["total_stake"] == pytest.approx(100.0)
    assert result[result["UserID"] == 2].iloc[0]["total_stake"] == pytest.approx(500.0)
