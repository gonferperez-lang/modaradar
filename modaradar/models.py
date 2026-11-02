from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Product:
    id: str                       # "<tienda>:<id nativo>"
    store: str
    title: str
    url: str
    price: float | None = None    # precio actual (el más bajo con stock)
    original: float | None = None  # precio original, antes de la rebaja
    currency: str = "EUR"
    available: bool | None = None
    image: str | None = None
    created: str | None = None    # fecha de alta en la tienda (si la publica)
    category: str = ""            # ropa · calzado · bolsos · accesorios
    prenda: str = ""              # vestidos · abrigos · punto… (solo ropa)
    sizes: list[str] | None = None  # tallas con stock (None = la tienda no lo publica)
    first_seen: str = ""
    last_seen: str = ""
    prev_price: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def discount(self) -> float:
        """0.46 = 46 % de descuento sobre el precio original."""
        if not self.price or not self.original or self.original <= self.price:
            return 0.0
        return round(1 - self.price / self.original, 3)

    def to_dict(self) -> dict[str, Any]:
        """Sin los campos vacíos o por defecto (el catálogo puede tener miles de prendas)."""
        d = asdict(self)
        defaults = {"currency": "EUR"}
        out = {k: v for k, v in d.items() if v not in (None, "", {}) and defaults.get(k) != v}
        if self.sizes is not None:      # [] = agotada en todas las tallas (distinto de "no se sabe")
            out["sizes"] = self.sizes
        if self.discount:
            out["pct"] = round(self.discount * 100)
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Product":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)
