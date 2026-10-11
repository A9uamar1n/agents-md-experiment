"""Работа с деньгами.

Внутри системы суммы хранятся в копейках (int), чтобы не ловить ошибки округления float.
В рубли переводим только на выходе отчёта.
"""
from decimal import ROUND_HALF_UP, Decimal


def to_kopecks(value: str) -> int:
    """'1234.50' -> 123450"""
    return int((Decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_rubles(kopecks: int) -> float:
    """123450 -> 1234.5"""
    return round(kopecks / 100, 2)


def split_evenly(total: int, parts: int) -> list[int]:
    """Делит сумму в копейках на parts частей. Лишние копейки достаются первым частям."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    base, rest = divmod(total, parts)
    return [base + (1 if i < rest else 0) for i in range(parts)]
