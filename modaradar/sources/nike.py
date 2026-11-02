"""Nike: páginas de ofertas de mujer de nike.com/es (las mismas que ve cualquier visitante).

Cada página trae, dentro de la propia web (`__NEXT_DATA__`), sus primeros ~36 productos con
precio actual, precio original y descuento. Se piden ordenadas por «lo más nuevo», así que
cada pasada ve las últimas rebajas que ha sacado Nike, que es justo lo que interesa avisar.

Nike no publica `robots.txt` en su API de paginación, así que solo se leen estas páginas
(su robots.txt sí permite las de listado `/w/`; las fichas `/p/` no se visitan nunca).
Opciones: `pages` = rutas de listado a leer.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..filters import categorize, is_women
from ..http import Blocked, PoliteClient
from ..models import Product

_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_GENDER = re.compile(r"\s*[-–]\s*(mujer|unisex)\s*$", re.I)


def fetch(client: PoliteClient, store: dict[str, Any], cfg: dict[str, Any]) -> list[Product]:
    base = store["url"].rstrip("/")
    min_pct = float(store.get("min_store_pct", cfg.get("general", {}).get("min_store_pct", 20))) / 100
    out: dict[str, Product] = {}
    for path in store.get("pages", []):
        html = client.get(base + path).decode("utf-8", "replace")
        for prod in parse(html, store, min_pct):
            out.setdefault(prod.id, prod)
    return list(out.values())


def products_of(html: str) -> list[dict[str, Any]]:
    m = _NEXT.search(html)
    if not m:
        raise Blocked("La página de Nike no trae datos de productos (posible protección anti-bots)")
    data = json.loads(m.group(1))
    wall = (((data.get("props") or {}).get("pageProps") or {}).get("initialState") or {}).get("Wall") or {}
    return [p for g in wall.get("productGroupings") or [] for p in (g.get("products") or [])]


def parse(html: str, store: dict[str, Any], min_pct: float) -> list[Product]:
    out: list[Product] = []
    for p in products_of(html):
        prices = p.get("prices") or {}
        price, orig = prices.get("currentPrice"), prices.get("initialPrice")
        if not price or not orig or orig <= price or 1 - price / orig < min_pct:
            continue
        copy = p.get("copy") or {}
        sub = (copy.get("subTitle") or "").strip()
        if sub and not re.search(r"mujer|unisex", sub, re.I) and not is_women(sub):
            continue   # «- Hombre», «- Niño/a»…
        kind = _GENDER.sub("", sub)
        name = (copy.get("title") or "").replace("\xa0", " ").strip()
        category, prenda = categorize(kind or name, "", p.get("productType") or "")
        if not category:
            continue
        images = p.get("colorwayImages") or {}
        out.append(Product(
            id=f"{store['id']}:{p.get('productCode') or p.get('internalPid')}",
            store=store["id"],
            title=f"{name} · {kind}" if kind else name,
            url=(p.get("pdpUrl") or {}).get("url") or store["url"],
            price=round(float(price), 2),
            original=round(float(orig), 2),
            currency=prices.get("currency") or "EUR",
            available=True,       # en el listado solo salen productos que se pueden comprar
            image=images.get("portraitURL") or images.get("squarishURL"),
            category=category,
            prenda=prenda,
            sizes=None,           # el listado no trae las tallas
            extra={"color": (p.get("displayColors") or {}).get("colorDescription")} if p.get("displayColors") else {},
        ))
    return out
