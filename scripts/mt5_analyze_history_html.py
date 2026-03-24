from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup
import pandas as pd


@dataclass
class TradeRow:
    open_time: str
    position: int
    symbol: str
    side: str
    volume: float
    open_price: float
    sl: Optional[float]
    tp: Optional[float]
    close_time: str
    close_price: float
    commission: float
    swap: float
    profit: float
    strategy_tag: str  # hidden cell content; empty -> likely manual


def parse_html_report(path: Path) -> List[TradeRow]:
    # Read raw bytes to avoid mangling UTF-16/Unicode exports
    data = path.read_bytes()
    soup = BeautifulSoup(data, "lxml")

    # Find the main table (there is usually a single big table)
    table = soup.find("table")
    if table is None:
        raise RuntimeError("No <table> found in HTML report (after bytes parse)")

    rows: List[TradeRow] = []
    in_positions_section = False

    for tr in table.find_all("tr"):
        # Detect the header row for Positions
        ths = tr.find_all("th")
        if ths:
            header_text = " ".join(t.get_text(strip=True) for t in ths)
            if "Positions" in header_text:
                in_positions_section = True
                continue

            # Skip the column header row; data rows follow
            if in_positions_section and "Time" in header_text and "Symbol" in header_text:
                continue

        if not in_positions_section:
            continue

        tds = tr.find_all("td")
        if not tds:
            continue

        text_cells = [td.get_text(strip=True) for td in tds]
        if len(text_cells) < 14:
            # Data rows should have 14 cells: time, position, symbol, type, comment/tag,
            # volume, open, sl, tp, close_time, close_price, commission, swap, profit.
            continue

        time_str = text_cells[0]
        pos_str = text_cells[1]
        sym_str = text_cells[2]

        if not re.match(r"^\d{4}\.\d{2}\.\d{2}", time_str):
            # Probably summary/footer row
            continue
        if not pos_str.isdigit():
            continue

        position = int(pos_str)
        symbol = sym_str

        side = text_cells[3].lower()
        strategy_tag = text_cells[4]  # this holds comment/strategy tag or ''

        try:
            volume = float(text_cells[5])
            open_price = float(text_cells[6])
            sl_val = text_cells[7]
            tp_val = text_cells[8]
            close_time = text_cells[9]
            close_price = float(text_cells[10])
            commission = float(text_cells[11])
            swap = float(text_cells[12])
            profit = float(text_cells[13])
            sl = float(sl_val) if sl_val else None
            tp = float(tp_val) if tp_val else None
        except Exception:
            # If parsing fails for a row, skip it
            continue

        rows.append(
            TradeRow(
                open_time=time_str,
                position=position,
                symbol=symbol,
                side=side,
                volume=volume,
                open_price=open_price,
                sl=sl,
                tp=tp,
                close_time=close_time,
                close_price=close_price,
                commission=commission,
                swap=swap,
                profit=profit,
                strategy_tag=strategy_tag,
            )
        )

    return rows


def to_dataframe(rows: List[TradeRow]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in rows])


def main() -> None:
    report_path = Path("mt5_report/ReportHistory-415292731.html")
    print("Report path:", report_path, "exists=", report_path.exists())

    rows = parse_html_report(report_path)
    print("Parsed rows:", len(rows))

    if not rows:
        print("No trade rows parsed — parser likely needs adjustment.")
        return

    df = to_dataframe(rows)
    print("DataFrame head:\n", df.head(10).to_string())

    # Classify auto vs manual based on strategy_tag presence
    df["is_auto"] = df["strategy_tag"].astype(str).str.len() > 0
    auto = df[df["is_auto"]].copy()
    manual = df[~df["is_auto"]].copy()

    print("\nCounts: total", len(df), "manual", len(manual), "auto", len(auto))

    def _pnl_summary(name: str, subset: pd.DataFrame) -> None:
        if subset.empty:
            print(f"\n=== {name} ===\n(no trades)")
            return
        win_rate = float((subset["profit"] > 0).mean())
        print(f"\n=== {name} ===")
        print("Count:", len(subset))
        print("Net Profit:", subset["profit"].sum())
        print("Win rate:", win_rate)
        if "symbol" in subset.columns:
            print("Per-symbol PnL:")
            print(subset.groupby("symbol")["profit"].sum().sort_values(ascending=False))

    _pnl_summary("ALL TRADES", df)
    _pnl_summary("AUTO TRADES (strategy_tag non-empty)", auto)
    _pnl_summary("MANUAL TRADES (strategy_tag empty)", manual)

    # Per-strategy breakdown for auto trades
    if not auto.empty:
        print("\n=== AUTO TRADES PER STRATEGY TAG ===")
        strat_summary = auto.groupby("strategy_tag")["profit"].agg(["count", "sum", "mean"])
        strat_summary["win_rate"] = auto.groupby("strategy_tag")["profit"].apply(lambda s: (s > 0).mean())
        print(strat_summary.sort_values("sum", ascending=False))


if __name__ == "__main__":
    main()
