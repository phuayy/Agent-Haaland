from __future__ import annotations

from fastapi import FastAPI

from app.pricing import apply_discount

app = FastAPI(title="orders-api")


@app.post("/orders/quote")
def quote(items: list[dict], discount_pct: float = 0.0) -> dict:
    return {"quoted_price": apply_discount(items, discount_pct)}
