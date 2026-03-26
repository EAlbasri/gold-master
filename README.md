# Gold Master Intraday Upgrade

This version widens the trading engine beyond sweep-reversal entries.

Included setup families:
- breakout continuation
- breakout retest
- trend pullback
- liquidity reversal
- failed-bounce continuation
- impulse continuation

Cost controls:
- only reviews the best 2 candidates per scan
- only asks Claude on a new M5 bar by default
- rejection cooldown prevents repeated review of the same bad setup
- macro web-search veto only runs on very strong candidates

Recommended starting mode:
- AUTO_EXECUTE=false
- RISK_PER_TRADE=0.005
- MAX_OPEN_TRADES=1
