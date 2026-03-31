Gold Master smarter intraday engine.

What changed:
- Each strategy can generate its own signal candidate independently.
- The bot does NOT require all strategies to align at the same time.
- Added local candidate scoring and ranking before Claude review.
- Added SMC-inspired structure-break retest.
- Kept breakout continuation, breakout retest, failed-bounce continuation, trend pullback, liquidity reversal, and impulse continuation.
- Added macro veto for only the strongest signals.
- Market-hours aware and quiet on weekends/closed market.

Before use:
1. Rotate any exposed MT5 / Claude / Telegram keys.
2. Copy env_template.txt to .env and fill your fresh keys.
3. Keep AUTO_EXECUTE=false until demo validation looks good.
4. Keep RISK_PER_TRADE=0.005 and MAX_OPEN_TRADES=1.
