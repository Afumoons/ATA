from __future__ import annotations

import pandas as pd
from pathlib import Path

path = Path("mt5_report/ReportHistory-415292731.xlsx")
print("Exists:", path.exists())

xls = pd.ExcelFile(path)
print("Sheets:", xls.sheet_names)

df = xls.parse(xls.sheet_names[0])

# Second header row (index 5) contains the trade table columns
header_row = 5
headers = list(df.iloc[header_row])
print("Detected headers:", headers)

trades = df.iloc[header_row + 1 :].copy()
trades.columns = headers

# Drop rows without a position id
trades = trades[trades["Position"].notna()]
print("Shape after header parse:", trades.shape)
print(trades.head(5).to_string())

# Normalize Comment and split manual vs auto
# In this export there is no explicit Comment column, so for now we
# treat ALL rows as "auto/system" as we cannot distinguish reliably.
# You mentioned: "semua trade tanpa komen adalah trade manual" — if you
# can export a report variant that includes the Comment column, we can
# split properly. For now we analyse the whole history.

# Convert numeric columns
for col in ["Profit", "Volume", "Commission", "Swap"]:
    if col in trades.columns:
        trades[col] = pd.to_numeric(trades[col], errors="coerce")

print("\n=== TOTAL PnL (ALL TRADES) ===")
print("Net Profit:", trades["Profit"].sum())
print("Win rate:", float((trades["Profit"] > 0).mean()))

if "Symbol" in trades.columns:
    print("\n=== Per-symbol PnL (ALL) ===")
    print(trades.groupby("Symbol")["Profit"].sum().sort_values(ascending=False))

    print("\n=== Per-symbol stats (ALL) ===")
    grouped = trades.groupby("Symbol")
    summary = grouped["Profit"].agg(["count", "sum", "mean"])
    summary["win_rate"] = grouped["Profit"].apply(lambda s: (s > 0).mean())
    print(summary.sort_values("sum", ascending=False))
