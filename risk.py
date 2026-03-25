from mt5_client import get_symbol_info


def calc_lot_size(symbol, entry, sl, balance, risk_pct):
    info = get_symbol_info(symbol)
    risk_amount = balance * risk_pct
    stop_distance = abs(entry - sl)
    if stop_distance <= 0:
        return 0.0

    tick_size = getattr(info, "trade_tick_size", 0.0) or info.point
    tick_value = getattr(info, "trade_tick_value", 0.0)

    if tick_size <= 0 or tick_value <= 0:
        contract_size = max(getattr(info, "trade_contract_size", 100.0), 1.0)
        money_risk_per_lot = stop_distance * contract_size
    else:
        money_risk_per_lot = (stop_distance / tick_size) * tick_value

    if money_risk_per_lot <= 0:
        return 0.0

    raw_lot = risk_amount / money_risk_per_lot

    volume_min = getattr(info, "volume_min", 0.01)
    volume_max = getattr(info, "volume_max", raw_lot)
    volume_step = getattr(info, "volume_step", 0.01) or 0.01

    lot = max(volume_min, min(raw_lot, volume_max))
    lot = round(lot / volume_step) * volume_step
    return round(lot, 2)
