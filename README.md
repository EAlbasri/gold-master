# Gold Master Intraday XAUUSD

This project is an MT5 + Claude intraday gold trader for XAUUSD.

## Architecture
- MT5 price data scans every minute.
- The technical engine proposes multiple intraday setup families:
  - breakout retest
  - breakout continuation
  - liquidity sweep reversal
  - trend pullback
  - impulse continuation
- Claude reviews the technical candidate.
- Claude web search can add a macro/news/geopolitical veto on high-score candidates.
- Telegram messages are sent as Gold Master.

## Important
- Rotate any credentials you previously pasted into chat.
- Start with `AUTO_EXECUTE=false`.
- Keep `RISK_PER_TRADE=0.005` while validating on demo.
- Anthropic web search must be enabled in your Claude Console/org to use live web checks.

## Run
1. Copy `.env.template` to `.env`
2. Fill in MT5, Anthropic, and Telegram credentials
3. `pip install -r requirements.txt`
4. Keep MT5 desktop open and logged in
5. `python main.py`

## Notes on memory/state
This project does not rely on LLM memory. It stores state locally in `gold_master_state.json` and passes relevant prior context back into Claude.
