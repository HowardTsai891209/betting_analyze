import pandas as pd
import pytest
from src.cleaner import COUNTRY_MAP, LANGUAGE_MAP, clean_daily


# ── 測試一：國籍 / 語言編碼解碼正確性 ────────────────────────────────────────

def test_country_map_known_codes():
    assert COUNTRY_MAP[276] == "Germany"
    assert COUNTRY_MAP[840] == "USA"
    assert COUNTRY_MAP[792] == "Turkey"

def test_language_map_known_codes():
    assert LANGUAGE_MAP[1] == "English"
    assert LANGUAGE_MAP[2] == "German"
    assert LANGUAGE_MAP[7] == "Turkish"

def test_unknown_country_returns_unknown():
    # 不在對照表的代碼，clean 後應為 "Unknown"
    import pandas as pd
    result = pd.Series([9999]).map(COUNTRY_MAP).fillna("Unknown")
    assert result[0] == "Unknown"


# ── 測試二：GGR 衍生欄位邊界值 ───────────────────────────────────────────────

def make_demo(user_id=1, fstpdate="2005-01-01"):
    """建立最小 demographics DataFrame 供測試使用"""
    return pd.DataFrame({
        "UserID": [user_id],
        "Country": ["Germany"],
        "Language": ["German"],
        "Gender": [1],
        "Fstpdate": pd.to_datetime([fstpdate]),
    })

def make_daily(stake, winnings, bets, date="2005-06-01", user_id=1):
    """建立單筆 daily 記錄"""
    return pd.DataFrame({
        "UserID": [user_id],
        "Date": pd.to_datetime([date]),
        "Stake": [stake],
        "Winnings": [winnings],
        "Bets": [bets],
    })

def test_ggr_positive_means_casino_wins():
    # Stake > Winnings → GGR > 0 → 賭場獲利，玩家虧損
    df = clean_daily(make_daily(stake=100, winnings=40, bets=5), make_demo())
    assert df["daily_GGR"].iloc[0] == pytest.approx(60.0)
    assert df["is_winning_day"].iloc[0] == False

def test_ggr_negative_means_player_wins():
    # Winnings > Stake → GGR < 0 → 玩家獲利
    df = clean_daily(make_daily(stake=50, winnings=200, bets=3), make_demo())
    assert df["daily_GGR"].iloc[0] == pytest.approx(-150.0)
    assert df["is_winning_day"].iloc[0] == True

def test_ggr_zero():
    df = clean_daily(make_daily(stake=100, winnings=100, bets=1), make_demo())
    assert df["daily_GGR"].iloc[0] == pytest.approx(0.0)
    assert df["is_winning_day"].iloc[0] == False


# ── 測試三：促銷金過濾（Fstpdate 邊界） ──────────────────────────────────────

def test_promo_record_before_fstpdate_is_excluded():
    # Date < Fstpdate → 應被過濾掉
    demo = make_demo(fstpdate="2005-03-01")
    daily = make_daily(date="2005-02-15", stake=100, winnings=0, bets=5)
    result = clean_daily(daily, demo)
    assert len(result) == 0

def test_record_on_fstpdate_is_kept():
    # Date == Fstpdate → 應保留（邊界值）
    demo = make_demo(fstpdate="2005-03-01")
    daily = make_daily(date="2005-03-01", stake=100, winnings=0, bets=5)
    result = clean_daily(daily, demo)
    assert len(result) == 1

def test_record_after_fstpdate_is_kept():
    # Date > Fstpdate → 應保留
    demo = make_demo(fstpdate="2005-03-01")
    daily = make_daily(date="2005-06-15", stake=200, winnings=50, bets=10)
    result = clean_daily(daily, demo)
    assert len(result) == 1


# ── 測試四：異常標記 ──────────────────────────────────────────────────────────

def test_negative_winnings_flagged():
    df = clean_daily(make_daily(stake=100, winnings=-50, bets=3), make_demo())
    assert df["is_negative_winnings"].iloc[0] == True

def test_zero_stake_with_bets_flagged():
    df = clean_daily(make_daily(stake=0, winnings=0, bets=5), make_demo())
    assert df["is_zero_stake_with_bets"].iloc[0] == True

def test_normal_record_not_flagged():
    df = clean_daily(make_daily(stake=100, winnings=50, bets=3), make_demo())
    assert df["is_negative_winnings"].iloc[0] == False
    assert df["is_zero_stake_with_bets"].iloc[0] == False
