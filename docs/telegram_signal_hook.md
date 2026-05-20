# Telegram Signal Hook — Shadow Mode

Purpose: read external Telegram mentor signals from `https://t.me/japsku`, parse changing XAUUSD buy/sell formats, and produce an auditable trade plan before any live execution is enabled.

## Current Afu Rules

- Symbol: canonical `XAUUSD` only; broker suffix resolution should happen inside ATA execution.
- Direction: detect `buy/long` or `sell/short`.
- Risk: `1%` per trade.
- SL:
  - Use explicit SL when present.
  - If missing, default to `500 pips` = `5.00` XAU price units (`pip_size=0.01`).
  - If a signal says `BUY 4500` and no SL, planned SL is `4495`.
  - If execution fills worse, the invalidation SL remains based on the signal/default reference, not widened just because spread/slippage is bad.
- TP:
  - If TP exists, full-close at TP1.
  - If TP is missing, plan `trailing_stop` with `500 pips` distance.
- Do not skip solely on parser confidence.
- No max-exposure gate at this parser layer.
- No spread/slippage skip at this parser layer.

## Safety State

`telegram_signal_listener.py` is currently **shadow only**:

- reads Telegram messages
- parses into `ExternalTradePlan`
- appends JSONL audit rows
- does **not** call MT5/order execution

Live execution still needs a separate bridge that supports absolute SL/TP and trailing-stop management. This is deliberate because ATA's existing `execute_trade()` is pips-from-current-price based, while Afu's rule requires preserving the signal invalidation price even if fill price is worse.

## Run

Install Telethon if needed:

```powershell
python -m pip install telethon
```

Set Telegram API credentials from <https://my.telegram.org/apps>:

```powershell
$env:TELEGRAM_API_ID="..."
$env:TELEGRAM_API_HASH="..."
```

Start shadow listener:

```powershell
python -m autonomous_trading_ai.scripts.telegram_signal_listener --channel japsku --history 20
```

Audit file:

```text
autonomous_trading_ai/execution/external_signal_audit.jsonl
```

## Next Build Step

Before live mode, implement and test:

1. MT5 market order function with absolute `stop_loss_price` and optional absolute `take_profit_price`.
2. Trailing-stop manager for no-TP signals.
3. Duplicate signal store keyed by `signal_id` / Telegram message id.
4. Live kill-switch env/file flag.
5. Shadow review on at least 10-20 real messages from the mentor channel.
