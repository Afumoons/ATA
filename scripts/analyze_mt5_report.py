from __future__ import annotations

import re
from pathlib import Path
from bs4 import BeautifulSoup  # type: ignore

BASE_DIR = Path(__file__).resolve().parents[1]
REPORT_PATH = BASE_DIR / "mt5_report" / "ReportHistory-415292731.html"


def parse_report(path: Path):
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    rows = []
    # Positions table: has header with "Positions" and columns Time / Position / Symbol / Type / Volume / Price / S/L / T/P / Time / Price / Commission / Swap / Profit
    # We'll look for all TR under that table where the first TD looks like a datetime.
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        time_text = tds[0].get_text(strip=True)
        if not re.match(r"^20\d{2}\.\d{2}\.\d{2}", time_text):
            continue
        # Extract fields according to MT5 HTML layout
        # Some reports have a hidden TD for comment spanning 8 cols; detect via class="hidden" or plain.
        pos_id = tds[1].get_text(strip=True)
        symbol = tds[2].get_text(strip=True)
        type_ = tds[3].get_text(strip=True)

        # detect if there is a hidden/comment cell
        # In the snippet, there is a TD with class="hidden" and colspan=8 before volume.
        # We search onwards for the first TD that parses as float -> volume.
        volume = None
        price_open = None
        sl = None
        tp = None
        time_close = None
        price_close = None
        commission = None
        swap = None
        profit = None
        comment = None

        # Collect raw texts after type cell
        tail_cells = tds[4:]
        texts = [c.get_text(strip=True) for c in tail_cells]

        # MT5 sometimes has comment in the first of these cells and then volume; comment is non-numeric and not '.'
        idx = 0
        if idx < len(texts) and not re.match(r"^[0-9.+-]", texts[idx] or "") and texts[idx] != "":
            comment = texts[idx]
            idx += 1

        def parse_float(s: str | None):
            if not s:
                return None
            try:
                return float(s)
            except Exception:
                return None

        if idx < len(texts):
            volume = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            price_open = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            sl = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            tp = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            time_close = texts[idx]; idx += 1
        if idx < len(texts):
            price_close = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            commission = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            swap = parse_float(texts[idx]); idx += 1
        if idx < len(texts):
            profit = parse_float(texts[idx]); idx += 1

        rows.append({
            "time_open": time_text,
            "pos_id": pos_id,
            "symbol": symbol,
            "type": type_,
            "comment": comment,
            "volume": volume,
            "price_open": price_open,
            "sl": sl,
            "tp": tp,
            "time_close": time_close,
            "price_close": price_close,
            "commission": commission,
            "swap": swap,
            "profit": profit,
        })

    return rows


def summarize(rows):
    from collections import defaultdict

    def classify_comment(c: str | None) -> str:
        if not c:
            return "manual"
        c = c.lower()
        if "clio-bridge" in c:
            return "clio_bridge"
        if "clio-auto-manual" in c:
            return "clio_auto_manual"
        return "other"

    stats = defaultdict(lambda: {"count": 0, "profit_sum": 0.0, "wins": 0, "losses": 0, "win_amt": 0.0, "loss_amt": 0.0})
    for r in rows:
        p = r.get("profit")
        if p is None:
            continue
        group = classify_comment(r.get("comment"))
        key = (group, r.get("symbol"))
        s = stats[key]
        s["count"] += 1
        s["profit_sum"] += p
        if p > 0:
            s["wins"] += 1
            s["win_amt"] += p
        elif p < 0:
            s["losses"] += 1
            s["loss_amt"] += p

    print("Total closed trades parsed:", sum(s["count"] for s in stats.values()))
    print()
    for (group, symbol), s in sorted(stats.items()):
        cnt = s["count"]
        if cnt == 0:
            continue
        wr = s["wins"] / cnt * 100.0
        avg = s["profit_sum"] / cnt
        print(f"Group={group:15s} Symbol={symbol:8s} Trades={cnt:3d} Win%={wr:5.1f} AvgPnL={avg:7.2f} TotalPnL={s['profit_sum']:8.2f}")

    # Show top 10 winning and losing trades overall
    rows_with_p = [r for r in rows if isinstance(r.get("profit"), (int, float))]
    rows_with_p.sort(key=lambda r: r["profit"], reverse=True)
    print("\nTop 10 winners:")
    for r in rows_with_p[:10]:
        print(r["time_open"], r["symbol"], r["type"], r.get("profit"), r.get("comment"))
    print("\nTop 10 losers:")
    rows_with_p.sort(key=lambda r: r["profit"])
    for r in rows_with_p[:10]:
        print(r["time_open"], r["symbol"], r["type"], r.get("profit"), r.get("comment"))


if __name__ == "main":
    pass

if __name__ == "__main__":
    rows = parse_report(REPORT_PATH)
    summarize(rows)
