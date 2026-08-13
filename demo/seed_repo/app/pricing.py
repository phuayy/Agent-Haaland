"""Order pricing helpers for the seed 'orders-api' service."""

from __future__ import annotations


def average_item_price(items: list[dict]) -> float:
    total = sum(item["price"] for item in items)
    return total / len(items)


def apply_discount(items: list[dict], discount_pct: float) -> float:
    avg_price = average_item_price(items)
    return avg_price * (1 - discount_pct / 100)
