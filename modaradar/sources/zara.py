"""Zara: el mismo catálogo público (JSON) que usa su web.

- `categories?ajax=true`: el menú. De ahí se sacan las secciones de rebajas de MUJER
  («SPECIAL PRICES» todo el año; «REBAJAS», «SALE», «BLACK FRIDAY»… cuando las abre).
  Se consulta como mucho cada `menu_hours` horas (se guarda en la memoria del radar).
- `category/<id>/products?ajax=true`: las prendas de cada sección, con precio actual, precio
  anterior (`oldPrice`) y descuento. Los precios vienen en céntimos.

Zara no publica las tallas en el listado (su robots.txt no permite consultar la disponibilidad
por talla), así que de Zara se avisa sin filtrar por talla.
"""
from __future__ import annotations

import re
import time
from typing import Any

from ..filters import categorize, fold
from ..http import PoliteClient
from ..models import Product

SALE_RX = re.compile(r"rebaja|special price|precios? especial|\bsale\b|outlet|black friday|ofertas?|descuento|last chance"
                     r"|ultimas? unidades|\bpromo")
SKIP_RX = re.compile(r"perfume|beauty|belleza|maquillaje|\bhair\b|\bhome\b|kids|\bnin[oa]s?\b|hombre|\bman\b|\bmen\b")


def discover(menu: dict[str, Any], section: str = "MUJER") -> list[dict[str, Any]]:
    """Secciones de rebajas dentro de MUJER: [{"id", "name"}] (el id ya resuelto si redirige)."""
    found: list[dict[str, Any]] = []

    def walk(cats: list[dict[str, Any]], depth: int) -> None:
        for c in cats:
            name = c.get("name") or ""
            key = fold(f"{name} {(c.get('seo') or {}).get('keyword') or ''}")
            layout = c.get("layout") or ""
            if SALE_RX.search(key) and not SKIP_RX.search(key) and "products" in layout:
                cid = c.get("redirectCategoryId") or c.get("id")
                if cid and all(f["id"] != cid for f in found):
                    found.append({"id": cid, "name": name.strip().title()})
                continue   # sus subsecciones ya están dentro
            walk(c.get("subcategories") or [], depth + 1)

    for top in menu.get("categories", []):
        if fold(top.get("name") or "") == fold(section):
            walk(top.get("subcategories") or [], 1)
            break
    return found


def fetch(client: PoliteClient, store: dict[str, Any], cfg: dict[str, Any],
          memo: dict[str, Any] | None = None) -> list[Product]:
    base = store["url"].rstrip("/") + store.get("locale", "/es/es")
    memo = memo if memo is not None else {}
    hours = float(store.get("menu_hours", 6))
    cats = memo.get("cats")
    if not cats or time.time() - float(memo.get("cats_at", 0)) > hours * 3600:
        menu = client.get_json(f"{base}/categories?ajax=true")
        cats = discover(menu, store.get("section", "MUJER"))[: int(store.get("max_sections", 6))]
        if cats:
            memo["cats"], memo["cats_at"] = cats, time.time()
    if not cats:
        cats = [{"id": c, "name": "Special prices"} for c in store.get("categories", [])]
    gen = cfg.get("general", {})
    min_pct = float(store.get("min_store_pct", gen.get("min_store_pct", 20))) / 100
    out: dict[str, Product] = {}
    for cat in cats:
        data = client.get_json(f"{base}/category/{cat['id']}/products?ajax=true")
        for prod in parse(data, store, base, min_pct, cat.get("name", "")):
            out.setdefault(prod.id, prod)
    memo["sections"] = [c.get("name", "") for c in cats]
    return list(out.values())


def _image(c: dict[str, Any]) -> str | None:
    colors = (c.get("detail") or {}).get("colors") or []
    medias = []
    for col in colors[:1]:
        medias = col.get("xmedia") or []
    medias = medias or c.get("xmedia") or []
    for m in medias:
        if m.get("type") == "image" and m.get("path") and m.get("name"):
            return f"https://static.zara.net{m['path']}/{m['name']}.jpg?ts={m.get('timestamp', '')}&w=500"
    return None


def parse(data: dict[str, Any], store: dict[str, Any], base: str, min_pct: float, section: str = "") -> list[Product]:
    out: list[Product] = []
    for group in data.get("productGroups", []) or []:
        for el in group.get("elements", []) or []:
            for c in el.get("commercialComponents", []) or []:
                if c.get("type") != "Product" or not c.get("price"):
                    continue
                price = c["price"] / 100
                old = (c.get("oldPrice") or 0) / 100
                if not old or old <= price or 1 - price / old < min_pct:
                    continue
                seo = c.get("seo") or {}
                if not seo.get("keyword") or not seo.get("seoProductId"):
                    continue
                name = (c.get("name") or "").strip().capitalize()
                category, prenda = categorize(name, c.get("familyName") or "",
                                              f"{c.get('subfamilyName') or ''} {'' if c.get('kind') == 'Wear' else c.get('kind') or ''}")
                if not category:
                    continue
                avail = c.get("availability")
                tags = c.get("tagTypes") or []
                out.append(Product(
                    id=f"{store['id']}:{c.get('id')}",
                    store=store["id"],
                    title=name,
                    url=f"{base}/{seo['keyword']}-p{seo['seoProductId']}.html?v1={seo.get('discernProductId') or c.get('id')}",
                    price=round(price, 2),
                    original=round(old, 2),
                    available=True if avail == "in_stock" else (False if avail else None),
                    image=_image(c),
                    category=category,
                    prenda=prenda,
                    sizes=None,   # Zara no publica las tallas en el listado
                    extra={k: v for k, v in {
                        "seccion": section,
                        "hasta": next((t.get("displayName") for t in tags if t.get("displayName")), None),
                    }.items() if v},
                ))
    return out
