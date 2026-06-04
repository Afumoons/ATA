import pandas as pd

from autonomous_trading_ai.ml.labels import (
    add_direction_label,
    add_future_return_labels,
    add_tp_sl_first_touch_labels,
    drop_unlabelable_tail,
)


def _frame():
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=6, freq="15min", tz="UTC"),
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 110, 106],
            "low": [99, 100, 101, 102, 98, 104],
            "close": [100, 102, 101, 105, 104, 108],
            "atr": [2, 2, 2, 2, 2, 2],
        }
    )


def test_future_return_labels_use_future_close_and_mark_tail_unlabeled():
    labeled = add_future_return_labels(_frame(), horizons=(2,))

    assert labeled.loc[0, "future_return_2"] == 0.5
    assert labeled.loc[3, "future_return_2"] == 1.5
    assert pd.isna(labeled.loc[4, "future_return_2"])
    assert pd.isna(labeled.loc[5, "future_return_2"])


def test_direction_label_uses_atr_normalized_threshold():
    labeled = add_future_return_labels(_frame(), horizons=(1,))
    labeled = add_direction_label(labeled, horizon=1, neutral_threshold_atr=0.4)

    assert labeled.loc[0, "direction_label"] == "buy"
    assert labeled.loc[1, "direction_label"] == "sell"
    assert labeled.loc[2, "direction_label"] == "buy"
    assert pd.isna(labeled.loc[5, "direction_label"])


def test_tp_sl_first_touch_marks_same_bar_ambiguity():
    df = pd.DataFrame(
        {
            "open": [100, 100, 100],
            "high": [100, 103, 100],
            "low": [100, 97, 100],
            "close": [100, 100, 100],
            "atr": [2, 2, 2],
        }
    )
    labeled = add_tp_sl_first_touch_labels(df, tp_atr_mult=1.0, sl_atr_mult=1.0, max_lookahead_bars=1)

    assert labeled.loc[0, "tp_sl_label"] == "ambiguous"
    assert bool(labeled.loc[0, "ambiguous_same_bar"]) is True


def test_drop_unlabelable_tail_removes_rows_without_future_window():
    labeled = add_future_return_labels(_frame(), horizons=(2,))
    trimmed = drop_unlabelable_tail(labeled, max_lookahead_bars=2)

    assert len(trimmed) == 4
    assert trimmed["future_return_2"].notna().all()
