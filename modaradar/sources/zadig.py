"""Zadig&Voltaire: API pública de catálogo («Helios»), documentada por la propia marca en
https://zadig-et-voltaire.com/llms.txt para programas automáticos (solo lectura, sin claves).

`GET /v1/catalog/categories/<id>/products?storeCode=es_es` devuelve cada prenda con su precio
normal (`regular`), el rebajado (`special`, con fechas) y las tallas con stock.

Opciones en config.toml:
- `categories`: secciones que se leen enteras (187 = Mujer › Ropa) para ver cualquier rebaja.
- `sale_categories`: secciones de rebajas/outlet (vacías fuera de temporada; se llenan solas).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..filters import categorize, fold
from ..http import PoliteClient
from ..models import Product, parse_iso

API = "https://helios.zadig-et-voltaire.com/api/v1/catalog"
MEDIA = "https://media.zadig-et-voltaire.com/product"


def fetch(client: PoliteClient, store: dict[str, Any], cfg: dict[str, Any]) -> list[Product]:
    code = store.get("store_code", "es_es")
    gen = cfg.get("general", {})
    min_pct = float(store.get("min_store_pct", gen.get("min_store_pct", 20))) / 100
    out: dict[str, Product] = {}
    for cid in [*store.get("categories", []), *store.get("sale_categories", [])]:
        page, pages = 1, 1
        while page <= min(pages, 10):
            data = client.get_json(f"{API}/categories/{cid}/products?storeCode={code}&pageSize=500&page={page}")
            pages = int(data.get("totalPages") or 1)
            for prod in parse(data.get("products") or [], store, min_pct):
                out.setdefault(prod.id, prod)
            page += 1
    return list(out.values())


def _active(d: dict[str, Any], now: datetime) -> bool:
    start, end = parse_iso(d.get("from") or None), parse_iso(d.get("to") or None)
    return (start is None or start <= now) and (end is None or now <= end)


def sale_price(price: dict[str, Any], now: datetime | None = None) -> tuple[float | None, float | None]:
    """(precio actual, precio original) del bloque `price` de la API."""
    now = now or datetime.now(timezone.utc)
    regular = (price.get("regular") or {}).get("value")
    if not regular:
        return None, None
    best = float(regular)
    special = price.get("special")
    for sp in (special if isinstance(special, list) else [special]):
        if isinstance(sp, dict) and sp.get("value") and _active(sp, now):
            best = min(best, float(sp["value"]))
    for tier in price.get("tier") or []:   # grupo 0 = cliente sin sesión
        if isinstance(tier, dict) and tier.get("value") and int(tier.get("groupId", 0) or 0) == 0 and _active(tier, now):
            best = min(best, float(tier["value"]))
    return best, float(regular)


def parse(items: list[dict[str, Any]], store: dict[str, Any], min_pct: float) -> list[Product]:
    out: list[Product] = []
    for p in items:
        if not p.get("enabled", True) or p.get("isKids"):
            continue
        if fold(p.get("gender") or "mujer") not in ("mujer", "women", "femme", "woman", "unisex"):
            continue
        price, orig = sale_price(p.get("price") or {})
        if not price or not orig or orig <= price or 1 - price / orig < min_pct:
            continue
        name = (p.get("name") or "").strip()
        category, prenda = categorize(name, p.get("type") or "", p.get("family") or "")
        if not category:
            continue
        medias = p.get("medias") or []
        img = next((m for m in medias if "image" in (m.get("roles") or [])), medias[0] if medias else None)
        stock = p.get("stock") or {}
        sizes = [str(s) for s in (p.get("inStockSizes") or [])]
        out.append(Product(
            id=f"{store['id']}:{p.get('sku')}",
            store=store["id"],
            title=name,
            url=f"https://zadig-et-voltaire.com/eu/es/p/{p.get('sku')}/{p.get('slug', '')}",
            price=round(price, 2),
            original=round(orig, 2),
            currency=((p.get("price") or {}).get("regular") or {}).get("currency") or "EUR",
            available=bool(stock.get("is_in_stock")) if stock else None,
            image=f"{MEDIA}{img['url']}?auto=format,compress&w=500" if img and img.get("url") else None,
            category=category,
            prenda=prenda,
            sizes=sizes,
            extra={"temporada": p["collection"]} if p.get("collection") else {},
        ))
    return out
