"""Estado persistente (JSON en `docs/data/`) y detección de rebajas nuevas."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .filters import fits
from .models import Product, now_iso, parse_iso

MAX_EVENTS = 300
COMEBACK_HOURS = 3


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path: Path, data: Any) -> bool:
    """Escribe solo si el contenido cambia (evita commits vacíos)."""
    if isinstance(data, dict) and isinstance(data.get("items"), list) and len(data) == 1:
        # Listas grandes: un elemento compacto por línea (pesa menos en el móvil
        # y en el historial de git solo cambian las líneas de lo que cambia)
        rows = ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in data["items"])
        text = '{"items":[\n' + rows + "\n]}\n"
    else:
        text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


def thresholds(cfg: dict[str, Any]) -> dict[str, float]:
    n = cfg.get("notifications", {})
    return {
        "min": float(n.get("min_discount_pct", 40)) / 100,           # «mucho más barata»
        "dest": float(n.get("destacadas_min_pct", 30)) / 100,        # Zara, Brownie, Zadig…
        "chollo": float(n.get("chollo_pct", 50)) / 100,              # 🔥 prioridad alta
        "drop": float(n.get("notify_price_drop_pct", 10) or 0) / 100,  # segunda rebaja
    }


def featured(cfg: dict[str, Any]) -> set[str]:
    return {s["id"] for s in cfg.get("stores", []) if s.get("destacada")}


def store_cfg(cfg: dict[str, Any], store_id: str) -> dict[str, Any]:
    return next((s for s in cfg.get("stores", []) if s.get("id") == store_id), {})


def store_threshold(cfg: dict[str, Any], store_id: str) -> float:
    """Descuento desde el que avisa una tienda: el suyo propio (`min_discount_pct` de la tienda),
    el de las destacadas o el general."""
    s = store_cfg(cfg, store_id)
    th = thresholds(cfg)
    if s.get("min_discount_pct") is not None:
        return float(s["min_discount_pct"]) / 100
    return th["dest"] if s.get("destacada") else th["min"]


class State:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.items: dict[str, Product] = {}
        for d in _read(self.dir / "products.json", {}).get("items", []):
            p = Product.from_dict(d)
            self.items[p.id] = p
        self.events: list[dict[str, Any]] = _read(self.dir / "events.json", {}).get("items", [])
        raw_state = _read(self.dir / "state.json", {})
        self.store_state: dict[str, dict[str, Any]] = raw_state.get("stores", {})
        self.filters_hash: str | None = raw_state.get("filters_hash")

    # ── fusión de resultados de una tienda ──────────────────────────────────
    def merge(self, store_id: str, fetched: list[Product], cfg: dict[str, Any],
              silent: bool = False) -> list[dict[str, Any]]:
        """Fusiona lo descargado y devuelve los eventos (avisos posibles).

        - 🆕 `new`: una prenda entra en rebajas/outlet con un descuento ≥ umbral.
        - 💸 `price_drop`: una prenda ya rebajada baja otra vez (`notify_price_drop_pct`) o
          supera el umbral de descuento.
        - 🔁 `restock`: vuelve a haber stock (o tu talla, si has puesto `mis_tallas`).

        `silent`: actualiza sin generar eventos (primera pasada de una tienda o filtros nuevos).
        """
        th = thresholds(cfg)
        thr = store_threshold(cfg, store_id)
        # tienda «parcial» (Nike): solo se leen sus rebajas más nuevas, así que lo que deja de
        # aparecer no se ha agotado necesariamente ni su vuelta es una reposición
        partial = bool(store_cfg(cfg, store_id).get("partial"))
        mine = cfg.get("notifications", {}).get("mis_tallas", [])
        now = now_iso()
        now_dt = parse_iso(now)
        seeded = self.store_state.get(store_id, {}).get("seeded", False) and not silent
        events: list[dict[str, Any]] = []

        fetched_ids = {p.id for p in fetched}
        for p in fetched:
            old = self.items.get(p.id)
            low = min([x for x in (p.price, (old.extra or {}).get("min") if old else None,
                                   old.price if old else None) if x], default=None)
            p.extra = {**(p.extra or {}), "min": low} if low and low < (p.original or 0) else dict(p.extra or {})
            if old:
                p.first_seen = old.first_seen or now
                p.prev_price = old.price if (p.price != old.price and old.price is not None) else old.prev_price
                if seeded and p.discount >= thr and p.available is not False:
                    # una prenda que no apareció un rato (p. ej. un fallo al paginar) no es una reposición:
                    # solo cuenta si llevaba al menos COMEBACK_HOURS sin aparecer
                    unseen = parse_iso((old.extra or {}).get("unseen"))
                    back = (old.available is False
                            or (not partial and unseen is not None
                                and now_dt - unseen >= timedelta(hours=COMEBACK_HOURS))
                            or (mine and not fits(old.sizes, mine) and fits(p.sizes, mine)))
                    dropped = bool(old.price and p.price and p.price < old.price
                                   and (p.price <= old.price * (1 - th["drop"]) or old.discount < thr))
                    if dropped:
                        events.append(self._event("price_drop", p, now, cfg, old_price=old.price))
                    elif back:
                        events.append(self._event("restock", p, now, cfg))
            else:
                p.first_seen = now
                if seeded and p.discount >= thr and p.available is not False:
                    events.append(self._event("new", p, now, cfg))
            p.last_seen = now[:10]  # solo la fecha: evita reescribir todo el catálogo en cada pasada
            self.items[p.id] = p

        # lo que ya no aparece: se ha agotado del todo o ya no está rebajado
        for q in self.items.values():
            if q.store == store_id and q.id not in fetched_ids and not q.extra.get("unseen") and not partial:
                q.extra = {**q.extra, "unseen": now}
        st = self.store_state.setdefault(store_id, {})
        if not st.get("seeded"):
            st["seeded"] = True
            st["seeded_at"] = now
        self.events = events + self.events
        return events

    @staticmethod
    def _event(kind: str, p: Product, at: str, cfg: dict[str, Any], **extra: Any) -> dict[str, Any]:
        th = thresholds(cfg)
        e = {"type": kind, "at": at, "id": p.id, "store": p.store, "title": p.title, "url": p.url,
             "price": p.price, "original": p.original, "pct": round(p.discount * 100), "currency": p.currency,
             "image": p.image, "category": p.category, "prenda": p.prenda, "available": p.available,
             "sizes": p.sizes}
        if p.discount >= th["chollo"]:
            e["hot"] = True
        if p.store in featured(cfg):
            e["dest"] = True
        if (p.extra or {}).get("min") and p.price is not None and p.price <= p.extra["min"]:
            e["minimo"] = True
        e.update(extra)
        return {k: v for k, v in e.items() if v is not None}

    # ── limpieza y guardado ────────────────────────────────────────────────
    def prune(self, forget_after_days: int, active_store_ids: set[str]) -> None:
        limit = datetime.now(timezone.utc) - timedelta(days=forget_after_days)
        self.items = {
            k: p for k, p in self.items.items()
            if p.store in active_store_ids and (parse_iso(p.last_seen) or limit) >= limit
        }
        self.events = [e for e in self.events if e.get("store") in active_store_ids][:MAX_EVENTS]
        self.store_state = {k: v for k, v in self.store_state.items() if k in active_store_ids}

    def products(self) -> list[Product]:
        return list(self.items.values())

    def save(self, extra_files: dict[str, Any]) -> list[str]:
        ps = sorted(self.items.values(), key=lambda p: (p.first_seen, p.discount, p.id), reverse=True)
        files: dict[str, Any] = {
            "products.json": {"items": [p.to_dict() for p in ps]},
            "events.json": {"items": self.events},
            "state.json": {"stores": self.store_state, "filters_hash": self.filters_hash},
            **extra_files,
        }
        return [name for name, data in files.items() if _write(self.dir / name, data)]
