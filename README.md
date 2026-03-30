Gold Master upgraded intraday engine.

Highlights:
- market-hours aware (no weekend / closed-market scanning or commentary)
- session-aware commentary
- new M5 bar gating to avoid repeated LLM calls on the same structure
- local rejection cooldown
- multi-pattern intraday engine for gold:
  - breakout continuation
  - breakout retest
  - failed-bounce continuation
  - trend pullback
  - liquidity reversal
  - impulse continuation (blocked in sideways regimes)

Before use:
1. Rotate any exposed MT5 / Claude / Telegram keys.
2. Copy env_template.txt to .env and fill your fresh keys.
3. Keep AUTO_EXECUTE=false until demo validation looks good.
4. Keep RISK_PER_TRADE=0.005 and MAX_OPEN_TRADES=1.
