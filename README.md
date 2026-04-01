Gold Master multi-symbol intraday engine.

Tracked symbols by default:
- XAUUSD
- EURUSD
- USDJPY

Core design:
- local MT5 engine scans every minute
- one strategy can produce a trade candidate on its own
- candidates are scored locally first
- only the best few are reviewed by Claude
- market-hours aware
- weekend / closed-market aware
- rejection cooldown to reduce API waste

Strategies included:
- breakout continuation
- breakout retest
- structure break retest (SMC-style)
- failed-bounce continuation
- trend pullback
- liquidity reversal
- impulse continuation

Recommended safe startup:
- AUTO_EXECUTE=false
- RISK_PER_TRADE=0.005
- MAX_OPEN_TRADES=1
- MAX_REVIEWS_PER_CYCLE=4
- LOCAL_REVIEW_MIN_SCORE=68

Important:
- Rotate any credentials that were previously shared.
- No strategy can honestly guarantee daily signals or profits.
- This version is designed to broaden coverage and reduce wasted API calls.
