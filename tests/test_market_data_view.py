import pandas as pd

from data.market_data_view import MarketDataView, as_of_reader


def test_market_data_view_filters_date_column():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=5, freq="D"),
            "close": [1, 2, 3, 4, 5],
        }
    )

    view = MarketDataView(df, as_of="2026-01-03")

    assert len(view) == 3
    assert view.latest()["close"] == 3
    assert view.close().iloc[-1] == 3


def test_market_data_view_filters_datetime_index():
    df = pd.DataFrame(
        {"close": [1, 2, 3, 4, 5]},
        index=pd.date_range("2026-01-01", periods=5, freq="D"),
    )

    view = MarketDataView(df, as_of="2026-01-03")

    assert len(view) == 3
    assert view.latest()["close"] == 3
    assert view.ohlcv().index.max() == pd.Timestamp("2026-01-03")


def test_as_of_reader_hides_mutated_future_rows():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=8, freq="D"),
            "close": [10, 11, 12, 13, 14, 1000, 2000, 3000],
        }
    )
    mutated = df.copy()
    mutated.loc[mutated["date"] > pd.Timestamp("2026-01-05"), "close"] *= 100

    original = as_of_reader(lambda: df, as_of="2026-01-05").close()
    protected = as_of_reader(lambda: mutated, as_of="2026-01-05").close()

    pd.testing.assert_series_equal(original, protected)
