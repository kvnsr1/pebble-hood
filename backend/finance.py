"""Decimal strings at every boundary; absent data never becomes zero."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re


def number(value):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 48
        or not re.fullmatch(r"-?\d{1,19}(?:\.\d{1,18})?", value)
    ):
        raise ValueError("Financial values must be bounded decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal") from None
    if not result.is_finite() or abs(result) > Decimal("1e18"):
        raise ValueError("Decimal out of range")
    return result


def money(value):
    if value is None:
        return None
    if not value.is_finite() or abs(value) > Decimal("1e18"):
        raise ValueError("Financial result out of range")
    with localcontext() as ctx:
        ctx.prec = 60
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return "0.00" if rounded == 0 else str(rounded)


def percent(change, base):
    return (
        None
        if change is None or base is None or base <= 0
        else money(change / base * 100)
    )


def _holding(
    ticker,
    name,
    quantity,
    price,
    average_cost=None,
    previous_close=None,
    asset_class="equity",
):
    q, p, c, prev = map(number, (quantity, price, average_cost, previous_close))
    value = None if q is None or p is None else q * p
    basis = None if q is None or c is None else q * c
    gain = None if value is None or basis is None else value - basis
    daily = None if p is None or prev is None else p - prev
    return dict(
        ticker=ticker,
        name=name,
        asset_class=asset_class,
        quantity=quantity,
        price=money(p),
        value=money(value),
        average_cost=money(c),
        unrealized=money(gain),
        unrealized_pct=percent(gain, abs(basis) if basis else None),
        price_day=money(daily),
        price_day_pct=percent(daily, prev),
    )


def holding(
    ticker,
    name,
    quantity,
    price,
    average_cost=None,
    previous_close=None,
    asset_class="equity",
):
    with localcontext() as ctx:
        ctx.prec = 80
        return _holding(
            ticker, name, quantity, price, average_cost, previous_close, asset_class
        )


def sort_holdings(rows):
    return sorted(
        rows,
        key=lambda h: (
            h["value"] is None,
            -(number(h["value"]) or Decimal(0)),
            h["ticker"],
        ),
    )


def chart_pixels(points):
    """Downsample observed values, preserving endpoints; never compute returns."""
    if len(points) < 2:
        return []
    if len(points) > 24:
        points = [points[i * (len(points) - 1) // 23] for i in range(24)]
    values = [number(p["value"]) for p in points]
    if any(v is None for v in values):
        return []
    lo, hi = min(values), max(values)
    return [50 if lo == hi else int((v - lo) / (hi - lo) * 100) for v in values]
