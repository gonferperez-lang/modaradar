"""Tiendas con Salesforce Commerce Cloud (Desigual, Bimba y Lola, Liu Jo, Superdry, Parfois,
y las de Tendam: Fifty Outlet, Cortefiel, Women'secret, Springfield, Pedro del Hierro…).

Se leen sus páginas de listado de outlet/rebajas de mujer, las mismas que ve cualquier
visitante, paginando con `?start=…&sz=…`. Cada tarjeta de producto trae su precio rebajado y
su precio original tachado; cada web los marca un poco distinto, así que se prueban varias
formas conocidas (precio en JSON, `strike-through`/`sales`, `basePrice`/`salesPrice`…).

Opciones en config.toml:
- `pages`: rutas de listado (p. ej. "/es/es/mujer").
- `page_size` y `max_pages`: tamaño de página (`sz`) y páginas por ruta. `page_size = 0`: solo la
  primera página, sin parámetros (para webs cuyo robots.txt no permite `?start=`).
- `tile`: expresión que marca el inicio de cada tarjeta (por defecto la estándar de Salesforce).
- `name_re`: expresión para sacar el nombre si la web lo pone en un sitio poco habitual.
"""
from __future__ import annotations

import html as htmllib
import re
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from ..filters import categorize, is_women
from ..http import Blocked, PoliteClient
from ..models import Product

DEFAULT_TILE = r'class="product[^"]*"\s+data-pid="'
_NUM = r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"

ORIGINAL = [
    re.compile(r'"list"\s*:\s*\{\s*"value"\s*:\s*([\d.]+)'),
    re.compile(r'class="discounted-price"[\s\S]{0,200}?content="([\d.]+)"'),
    re.compile(r'item_orig_price(?:&quot;|")\s*:\s*([\d.]+)'),
    re.compile(r'strike-through[\s\S]{0,700}?content="([\d.]+)"'),
    re.compile(r'class="[^"]*\bbasePrice\b[^"]*"[^>]*>\s*' + _NUM),
    re.compile(r'<del\b[\s\S]{0,400}?' + _NUM + r'\s*(?:&euro;|€)'),
    re.compile(r'class="[^"]*(?:price--old|old-price|price-old|was-price)[^"]*"[^>]*>[\s\S]{0,200}?' + _NUM),
]
SALE = [
    re.compile(r'"sales"\s*:\s*\{\s*"value"\s*:\s*([\d.]+)'),
    re.compile(r'class="sales[\s\S]{0,500}?content="([\d.]+)"'),
    re.compile(r'class="[^"]*\bsalesPrice\b[^"]*"[^>]*>\s*' + _NUM),
    re.compile(r'class="[^"]*(?:price--sale|sale-price|price-sale|special-price)[^"]*"[^>]*>[\s\S]{0,200}?' + _NUM),
]
NAME = [
    re.compile(r'"productName"\s*:\s*"((?:[^"\\]|\\.)+)"'),
    re.compile(r'class="[^"]*\bproduct-name\b[^"]*"[^>]*>\s*([^<]{3,}?)\s*<'),
    re.compile(r'class="[^"]*(?:pdp-link|tile-title|tile-name|product-title|productName|name-link|productTile__name)[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,}?)\s*<'),
    re.compile(r'itemprop="name"[^>]*content="([^"]{3,})"'),
    re.compile(r'<a\b[^>]*\btitle="([^"]{3,})"'),
    re.compile(r'<img\b[^>]*\balt="([^"]{3,})"'),
]
URL = [
    re.compile(r'class="[^"]*(?:product-name|pdp-link|tile-link|productTile__link|product-tile__link|link)[^"]*"[^>]*\bhref="([^"#]+)"'),
    re.compile(r'\bhref="([^"#]+)"[^>]*class="[^"]*(?:product-name|pdp-link|tile-link|link)'),
    re.compile(r'"url"\s*:\s*"(/[^"]+)"'),
    re.compile(r'\bhref="((?:https?://[^"/]+)?/[^"#]+?\.html[^"#]*)"'),
]
IMAGE = re.compile(r'(?:data-src|data-srcset|srcset|src)="([^"\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\s]*)?)', re.I)


def money(txt: str) -> float | None:
    """«1.299,95» → 1299.95 · «49,99» → 49.99 · «159.90» → 159.9."""
    t = txt.strip().replace(" ", "").replace("\xa0", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


NOT_NAMES = {"previous", "next", "anterior", "siguiente", "comprar", "comprar ahora", "ver mas", "añadir"}


def _first(patterns: list[re.Pattern[str]], chunk: str) -> str | None:
    for rx in patterns:
        for m in rx.finditer(chunk):
            v = m.group(1).strip()
            if v.lower() not in NOT_NAMES:
                return v
    return None


def page_url(base: str, path: str, start: int, size: int) -> str:
    """Ruta de listado con `start`/`sz`. Con `size` = 0, la ruta tal cual (una sola página)."""
    if not size:
        return urljoin(base + "/", path.lstrip("/"))
    parts = urlsplit(urljoin(base + "/", path.lstrip("/")) if not path.startswith("http") else path)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ("start", "sz")]
    q += [("start", str(start)), ("sz", str(size))]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), ""))


def fetch(client: PoliteClient, store: dict[str, Any], cfg: dict[str, Any]) -> list[Product]:
    base = store["url"].rstrip("/")
    size = int(store.get("page_size", 48))
    pages = int(store.get("max_pages", 3)) if size else 1
    min_pct = float(store.get("min_store_pct", cfg.get("general", {}).get("min_store_pct", 20))) / 100
    out: dict[str, Product] = {}
    tiles_seen = 0
    for path in store.get("pages", []):
        for n in range(pages):
            html = client.get(page_url(base, path, n * size, size)).decode("utf-8", "replace")
            found, tiles = parse(html, store, cfg, min_pct)
            tiles_seen += tiles
            for p in found:
                out.setdefault(p.id, p)
            if not size or tiles < size:
                break   # última página
    if tiles_seen == 0:
        raise Blocked("La página no trae tarjetas de producto (¿ha cambiado la web o hay protección anti-bots?)")
    return list(out.values())


def parse(html: str, store: dict[str, Any], cfg: dict[str, Any], min_pct: float) -> tuple[list[Product], int]:
    """(prendas rebajadas, nº de tarjetas encontradas)."""
    base = store["url"].rstrip("/")
    tile = re.compile(store.get("tile") or DEFAULT_TILE)
    starts = [m.start() for m in tile.finditer(html)]
    excl = [*cfg.get("filters", {}).get("exclude", []), *store.get("exclude", [])]
    out: list[Product] = []
    seen: set[str] = set()
    for i, s in enumerate(starts):
        chunk = html[s: starts[i + 1] if i + 1 < len(starts) else s + 20000]
        orig, sale = _first(ORIGINAL, chunk), _first(SALE, chunk)
        orig_v, sale_v = money(orig) if orig else None, money(sale) if sale else None
        if not orig_v or not sale_v or sale_v >= orig_v or 1 - sale_v / orig_v < min_pct:
            continue
        name = _first([re.compile(store["name_re"]), *NAME] if store.get("name_re") else NAME, chunk)
        url = _first(URL, chunk)
        if not name or not url:
            continue
        name = htmllib.unescape(name.encode().decode("unicode_escape") if "\\u" in name else name).strip()
        name = re.sub(r"\s+", " ", name)
        if not is_women(name, excl):
            continue
        category, prenda = categorize(name)
        if not category:
            continue
        url = urljoin(base + "/", htmllib.unescape(url))
        pid = re.search(r'data-pid="([^"]+)"', chunk)
        key = (pid.group(1) if pid else urlsplit(url).path).split("?")[0]
        same = (urlsplit(url).path, name.lower(), round(sale_v, 2))   # la misma prenda en otra variante
        if key in seen or same in seen:
            continue
        seen.update((key, same))
        img = IMAGE.search(chunk)
        image = urljoin(base + "/", htmllib.unescape(img.group(1)).split(" ")[0]) if img else None
        out.append(Product(
            id=f"{store['id']}:{key}",
            store=store["id"],
            title=name[:1].upper() + name[1:],
            url=url,
            price=round(sale_v, 2),
            original=round(orig_v, 2),
            available=True,      # en el listado solo salen productos a la venta
            image=image,
            category=category,
            prenda=prenda,
            sizes=None,
        ))
    return out, len(starts)
