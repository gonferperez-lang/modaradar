"""Conectores de tiendas. Cada uno devuelve una lista de `Product` (solo prendas rebajadas)."""
from __future__ import annotations

from collections.abc import Callable

from ..http import PoliteClient, SourceSkipped  # noqa: F401  (re-exportado)
from ..models import Product
from . import nike, shopify, zadig, zara

Fetcher = Callable[..., list[Product]]  # (client, store, cfg[, memo=…]) → productos

PLATFORMS: dict[str, Fetcher] = {
    "shopify": shopify.fetch,
    "zara": zara.fetch,
    "zadig": zadig.fetch,
    "nike": nike.fetch,
}
