import MetaTrader5 as mt5
import pandas as pd

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER


def connect():
    if mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return True
    raise RuntimeError("MT5 initialize failed: {0}".format(mt5.last_error()))


def ensure_connection():
    info = mt5.terminal_info()
    if info is None:
        return connect()
    return True


def shutdown():
    mt5.shutdown()


def ensure_symbol(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError("symbol_info failed for {0}: {1}".format(symbol, mt5.last_error()))
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError("symbol_select failed for {0}: {1}".format(symbol, mt5.last_error()))
    return True


def get_rates(symbol, timeframe, count=500):
    ensure_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError("copy_rates_from_pos failed: {0}".format(mt5.last_error()))
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_tick(symbol):
    ensure_symbol(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError("symbol_info_tick failed: {0}".format(mt5.last_error()))
    return tick


def get_symbol_info(symbol):
    ensure_symbol(symbol)
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError("symbol_info failed: {0}".format(mt5.last_error()))
    return info


def get_account_info():
    account = mt5.account_info()
    if account is None:
        raise RuntimeError("account_info failed: {0}".format(mt5.last_error()))
    return account


def get_open_positions(symbol=None):
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return positions or []


def _send_order(symbol, lot, order_type, price, sl, tp, deviation=20, comment="gold_master"):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": 20260329,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    check = mt5.order_check(request)
    if check is None:
        raise RuntimeError("order_check failed: {0}".format(mt5.last_error()))
    return mt5.order_send(request)


def place_buy(symbol, lot, sl, tp, deviation=20, comment="gold_master_buy"):
    tick = get_tick(symbol)
    return _send_order(symbol, lot, mt5.ORDER_TYPE_BUY, tick.ask, sl, tp, deviation, comment)


def place_sell(symbol, lot, sl, tp, deviation=20, comment="gold_master_sell"):
    tick = get_tick(symbol)
    return _send_order(symbol, lot, mt5.ORDER_TYPE_SELL, tick.bid, sl, tp, deviation, comment)
