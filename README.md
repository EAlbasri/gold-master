# Gold Master Hybrid Project

This project uses a hybrid AI architecture for intraday XAUUSD trading:

- Local MT5 strategy engine scans price every minute and builds technical trade candidates
- Claude (Anthropic) is the final trade decision and veto layer for strong candidates only
- OpenAI GPT-5 mini writes human-style market updates and macro/geopolitical commentary
- Local state store keeps prior watched levels, last signal, and last analysis in `gold_master_state.json`

## Why this architecture

The local strategy engine handles almost all of the work:
- breakout continuation
- breakout retest
- liquidity sweep reversal
- impulse continuation
- trend pullback

This keeps cost down and avoids paying for an LLM every loop. Claude is only called when a candidate already scores well locally. OpenAI is used for startup/session/macro commentary.

## Cost controls built in

- Claude review only for candidates with `local_score >= LOCAL_REVIEW_THRESHOLD`
- Claude review only on a new M5 candle if `CLAUDE_REVIEW_ON_NEW_M5_ONLY=true`
- maximum `MAX_CANDIDATES_PER_SCAN`
- pulse updates disabled by default
- macro web checks are infrequent
- commentary and macro use OpenAI; trade review uses Claude

## No model memory required

Do not rely on LLM memory for a trading bot.

Instead, this project stores structured local state:
- last analysis
- watched levels
- last signal
- last macro headline

That state is fed back into the models when needed, which is safer and more auditable than model memory.

## Setup

1. Rotate any secrets previously pasted into chat
2. Copy `.env.template` to `.env`
3. Fill in fresh keys and account values
4. Install dependencies:
   `pip install -r requirements.txt`
5. Start with:
   - `AUTO_EXECUTE=false`
   - `RISK_PER_TRADE=0.005`
   - `MAX_OPEN_TRADES=1`

## Notes

- The scanner runs every minute, but AI review does not run every minute by default.
- Startup/session/macro messages are written as Gold Master.
- Signals and execution messages remain structured.
- This project is for day trading only, not swing trading.
