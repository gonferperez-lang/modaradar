"""Tiendas Shopify: catálogo público `/products.json`.

Shopify publica para cada talla/color su precio y su «precio de comparación» (`compare_at_price`,
el precio original tachado). Si el precio es menor, la prenda está rebajada.

Opciones de la tienda en config.toml:
- `locale`: prefijo del mercado español (p. ej. "/es-es"): títulos en español y precios de España.
- `max_pages`: páginas de 250 productos del catálogo completo (0 = no leerlo).
- `collections`: colecciones que se leen además (p. ej. "outlet"), hasta `collection_pages` páginas.
- `exclude`: palabras que descartan un producto (título y tipo).
- `exclude_tags`: etiquetas exactas que lo descartan (p. ej. la línea infantil «Mini»).
- `women_terms`: en marcas que también venden ropa de hombre, palabras que deben aparecer en el
  tipo de producto o en las etiquetas para que cuente como de mujer (p. ej. ["mujer", "woman"]).
- `product_url`: plantilla del enlace cuando la web pública no es la de Shopify
  (p. ej. "https://emestudios.com/es/es/product/{handle}").
"""
from __future__ import annotations

import re
from typing import Any

from ..filters import categorize, fold, is_women, matches_any
from ..http import PoliteClient
from ..models import Product

SIZE_NAMES = ("size", "talla", "taille", "taglia", "tamano", "grosse", "größe", "maat", "tall")
_KID_SIZE = re.compile(r"^(\d{1,2})(\s*-\s*\d{1,2})?\s*(yrs?|years?|anos?|a|y|m|meses|months?)?$")


def kids_sizes(values: list[str]) -> bool:
    """Tallas de niña/o: «4-5Yrs», «6 años», «8», «10», «12» (las de mujer son XS…XL o 32…48)."""
    vals = [fold(v) for v in values if v and fold(v) not in ("default title", "u", "unica", "tu")]
    if not vals:
        return False
    for v in vals:
        m = _KID_SIZE.match(v)
        if not m or int(m.group(1)) > 16:
            return False
    return True


def fetch(client: PoliteClient, store: dict[str, Any], cfg: dict[str, Any]) -> list[Product]:
    base = store["url"].rstrip("/") + (store.get("locale") or "").rstrip("/")
    sources: list[tuple[str, int]] = []
    if int(store.get("max_pages", 4)):
        sources.append(("/products.json", int(store.get("max_pages", 4))))
    sources += [(f"/collections/{c}/products.json", int(store.get("collection_pages", 4)))
                for c in store.get("collections", [])]
    out: list[Product] = []
    seen: set[str] = set()
    for path, max_pages in sources:
        for page in range(1, max_pages + 1):
            data = client.get_json(f"{base}{path}?limit=250&page={page}")
            items = data.get("products", []) if isinstance(data, dict) else []
            for prod in parse(items, store, cfg, base):
                if prod.id not in seen:
                    seen.add(prod.id)
                    out.append(prod)
            if len(items) < 250:
                break
    return out


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _image(p: dict[str, Any]) -> str | None:
    images = p.get("images") or []
    src = images[0].get("src") if images else None
    if not src:
        return None
    return src + ("&" if "?" in src else "?") + "width=500"   # miniatura (el CDN de Shopify la recorta)


def parse(items: list[dict[str, Any]], store: dict[str, Any], cfg: dict[str, Any], base: str) -> list[Product]:
    gen = cfg.get("general", {})
    min_pct = float(store.get("min_store_pct", gen.get("min_store_pct", 20))) / 100
    excl = [*cfg.get("filters", {}).get("exclude", []), *store.get("exclude", [])]
    excl_tags = {fold(t) for t in store.get("exclude_tags", [])}
    women_terms = store.get("women_terms") or []
    url_tpl = store.get("product_url") or f"{base}/products/{{handle}}"
    currency = store.get("currency") or gen.get("currency", "EUR")
    out: list[Product] = []
    for p in items:
        tags = p.get("tags") or []
        tags = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(",")]
        if excl_tags and any(fold(t) in excl_tags for t in tags):
            continue
        title = (p.get("title") or "").strip()
        ptype = p.get("product_type") or ""
        if not is_women(f"{title} {ptype}", excl):
            continue
        if women_terms and not matches_any(f"{ptype} | {' | '.join(tags)}", women_terms):
            continue   # marca mixta: no es de su línea de mujer
        variants = p.get("variants") or []
        if not variants:
            continue
        # la mejor rebaja entre las tallas/colores con stock (o entre todas si está agotada)
        pool = [v for v in variants if v.get("available")] or variants
        best = None
        for v in pool:
            price, orig = _num(v.get("price")), _num(v.get("compare_at_price"))
            if orig > price > 0:
                disc = 1 - price / orig
                if best is None or disc > best[0] + 1e-9 or (abs(disc - best[0]) < 1e-9 and price < best[1]):
                    best = (disc, price, orig)
        if best is None or best[0] < min_pct:
            continue   # sin rebaja (o muy pequeña): no es lo que buscamos
        category, prenda = categorize(title, ptype, " ".join(tags))
        if not category:
            continue
        # tallas con stock que están rebajadas
        options = p.get("options") or []
        idx = next((i for i, o in enumerate(options[:3], 1)
                    if fold(o.get("name") if isinstance(o, dict) else str(o)).startswith(SIZE_NAMES)), None)
        if idx and kids_sizes([str(v.get(f"option{idx}") or "") for v in variants]):
            continue   # línea infantil
        on_sale = [v for v in variants if _num(v.get("compare_at_price")) > _num(v.get("price")) > 0]
        avail = [v for v in on_sale if v.get("available")]
        if idx:
            sizes: list[str] = []
            for v in avail:
                s = str(v.get(f"option{idx}") or "").strip()
                if s and s not in sizes:
                    sizes.append(s)
        else:
            sizes = ["Única"] if avail else []
        out.append(Product(
            id=f"{store['id']}:{p['id']}",
            store=store["id"],
            title=title,
            url=url_tpl.format(handle=p.get("handle", "")),
            price=round(best[1], 2),
            original=round(best[2], 2),
            currency=currency,
            available=bool(avail),
            image=_image(p),
            created=p.get("created_at") or p.get("published_at"),
            category=category,
            prenda=prenda,
            sizes=sizes,
        ))
    return out
