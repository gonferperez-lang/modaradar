"""Resumen de cada tienda para la app: cuántas prendas rebajadas tiene, cuánto rebaja y si avisa."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from .models import Product, parse_iso
from .state import store_threshold


def analyse(products: list[Product], stores: list[dict[str, Any]], th: dict[str, float],
            cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    week = datetime.now(timezone.utc) - timedelta(days=7)
    out = []
    for s in stores:
        ps = [p for p in products if p.store == s["id"] and not (p.extra or {}).get("unseen") and p.available]
        ropa = [p for p in ps if p.category == "ropa"]
        discounts = [p.discount for p in ps]
        thr = store_threshold(cfg or {"stores": stores, "notifications": {
            "min_discount_pct": th["min"] * 100, "destacadas_min_pct": th["dest"] * 100}}, s["id"])
        row = {k: s[k] for k in ("id", "name", "url", "platform", "note", "country", "outlet_url", "destacada", "short", "partial")
               if s.get(k) not in (None, "")}
        if s.get("web"):
            row["url"] = s["web"]    # la web pública (no la tienda Shopify que se lee)
        row.update(
            items=len(ps),
            ropa=len(ropa),
            avg=round(mean(discounts) * 100) if discounts else None,
            max=round(max(discounts) * 100) if discounts else None,
            big=sum(1 for d in discounts if round(d * 100) >= round(th["chollo"] * 100)),  # 🔥 −50 % o más
            alert=sum(1 for d in discounts if d >= thr),              # lo que te avisaría
            week=sum(1 for p in ps if (parse_iso(p.first_seen) or week) > week),
            thr=round(thr * 100),
        )
        out.append(row)
    # destacadas primero; después, las que más rebajas grandes tienen
    out.sort(key=lambda r: (not r.get("destacada"), -(r["alert"]), -(r["avg"] or 0)))
    return {"stores": out}
