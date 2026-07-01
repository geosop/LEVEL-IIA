from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_RATE_Q = Decimal("0.001")


def rate_display_from_count(count: int, total: int) -> str:
    """Display count/total as a three-decimal ROUND_HALF_UP rate."""
    count_i = int(count)
    total_i = int(total)
    if total_i <= 0:
        raise ValueError("total must be positive")
    value = (Decimal(count_i) / Decimal(total_i)).quantize(
        _RATE_Q, rounding=ROUND_HALF_UP
    )
    return f"{value:.3f}"


def rate_display(value: object) -> str:
    """Display a scalar rate using Decimal(str(value)) and ROUND_HALF_UP."""
    dec = Decimal(str(value)).quantize(_RATE_Q, rounding=ROUND_HALF_UP)
    return f"{dec:.3f}"


def count_rate_display(count: int, total: int) -> str:
    """Display an exact count and its count-derived rounded rate."""
    return f"{int(count)}/{int(total)} ({rate_display_from_count(count, total)})"
