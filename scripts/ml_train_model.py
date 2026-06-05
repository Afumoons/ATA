"""Compatibility wrapper for Stage 1 shadow model training.

The implementation lives in ``scripts.ml_train_shadow_model``; this filename
matches the original development plan command.
"""

from autonomous_trading_ai.scripts.ml_train_shadow_model import main


if __name__ == "__main__":
    raise SystemExit(main())
