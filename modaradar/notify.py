"""Avisos push al móvil: ntfy (app gratuita) y, opcionalmente, Telegram."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from .filters import PRENDA_NAMES, fits, matches_any
from .http import PoliteClient

ICON = {"new": "🆕", "price_drop": "💸", "restock": "🔁"}
LABEL = {"new": "Nuevo en outlet", "price_drop": "Rebajado aún más", "restock": "Vuelve a haber stock"}


@dataclass
class Message:
    title: str
    body: str
    url: str = ""
    image: str | None = None
    priority: int = 3
    tags: list[str] = field(default_factory=list)


def euros(v: float | None) -> str:
    if v is None:
        return ""
    txt = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{txt[:-3] if txt.endswith(',00') else txt} €"


def select(events: list[dict[str, Any]], cfg: dict[str, Any]) -> list[tuple[dict[str, Any], bool]]:
    """Devuelve [(evento, es_prioritario)] según la configuración de avisos."""
    n = cfg.get("notifications", {})
    enabled = {"new": n.get("notify_new", True), "restock": n.get("notify_restock", True),
               "price_drop": bool(n.get("notify_price_drop_pct", 10))}
    cats = set(n.get("categories", ["ropa"]))
    watch = n.get("watchlist", [])
    mine = n.get("mis_tallas", [])
    chosen = []
    for e in events:
        if not enabled.get(e["type"]):
            continue
        watched = bool(watch) and matches_any(e["title"], watch)
        if e.get("category") not in cats and not watched:
            continue
        if not fits(e.get("sizes"), mine):
            continue   # no queda tu talla
        hot = bool(e.get("hot") or e.get("dest") or watched)
        chosen.append((e, hot))
    # prioritarios primero y, dentro de cada grupo, los descuentos más grandes
    chosen.sort(key=lambda t: (not t[0].get("hot"), not t[1], -(t[0].get("pct") or 0)))
    return chosen


def build(events: list[dict[str, Any]], cfg: dict[str, Any], store_names: dict[str, str]) -> list[Message]:
    chosen = select(events, cfg)
    n = cfg.get("notifications", {})
    mine = n.get("mis_tallas", [])
    limit = max(1, int(n.get("max_per_run", 6)))
    msgs: list[Message] = []
    show = chosen if len(chosen) <= limit else chosen[: limit - 1]
    for e, hot in show:
        store = store_names.get(e["store"], e["store"])
        label = LABEL[e["type"]]
        if e["type"] == "restock" and mine:
            label = "Vuelve tu talla"
        pct = f"−{e['pct']} %" if e.get("pct") else ""
        head = f"{'🔥 ' if e.get('hot') else ''}{pct} · {ICON[e['type']]} {label} · {store}"
        if e.get("dest"):
            head = f"⭐ {store} · {'🔥 ' if e.get('hot') else ''}{pct} · {ICON[e['type']]} {label}"
        price = euros(e.get("price"))
        if e.get("original"):
            price += f" (antes {euros(e['original'])})"
        lines = [e["title"], price]
        if e["type"] == "price_drop" and e.get("old_price"):
            lines.append(f"💸 Bajó de {euros(e['old_price'])} a {euros(e.get('price'))}")
        if e.get("minimo") and e["type"] == "price_drop":
            lines.append("📉 El precio más bajo que hemos visto")
        sizes = e.get("sizes")
        if sizes is not None:
            mine_ok = [s for s in sizes if fits([s], mine)] if mine else sizes
            if sizes == ["Única"]:
                lines.append("Talla única")
            elif mine_ok:
                lines.append(("Tus tallas: " if mine else "Tallas: ") + ", ".join(mine_ok[:10]))
        elif e.get("store") and e.get("category") == "ropa":
            lines.append("Tallas: mira en la web")
        if e.get("prenda") and e.get("prenda") != "otras":
            lines.append(f"👗 {PRENDA_NAMES.get(e['prenda'], e['prenda'])}")
        msgs.append(Message(title=head, body="\n".join(x for x in lines if x), url=e.get("url", ""),
                            image=e.get("image"), priority=5 if e.get("hot") else (4 if hot else 3),
                            tags=["fire"] if e.get("hot") else []))
    rest = chosen[len(show):]
    if rest:
        count: dict[str, int] = {}
        for e, _ in rest:
            name = store_names.get(e["store"], e["store"])
            count[name] = count.get(name, 0) + 1
        best = max((e.get("pct") or 0) for e, _ in rest)
        msgs.append(Message(
            title=f"🛍️ {len(rest)} rebajas más (hasta −{best} %)",
            body="En: " + ", ".join(f"{k} ({v})" for k, v in sorted(count.items(), key=lambda kv: -kv[1]))
                 + "\nÁbrelas en ModaRadar.",
            url=(os.environ.get("APP_URL") or "").strip(), priority=3, tags=["shopping_bags"]))
    return msgs


def send(messages: list[Message], client: PoliteClient) -> list[str]:
    """Envía por los canales configurados. Devuelve la lista de errores (vacía si todo ok)."""
    errors: list[str] = []
    # GitHub pasa los secrets inexistentes como texto vacío: se tratan como "no definido"
    env = lambda k: (os.environ.get(k) or "").strip()  # noqa: E731
    topic = env("NTFY_TOPIC")
    server = (env("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    tg_token, tg_chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not topic and not (tg_token and tg_chat):
        return ["No hay canal de avisos: crea el secret NTFY_TOPIC en GitHub "
                "(Settings → Secrets and variables → Actions → pestaña Secrets)."]
    if topic and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        return [f"El tema de ntfy («{topic[:3]}…», {len(topic)} caracteres) no es válido: usa solo letras sin "
                "acentos ni ñ, números, guiones (-) y guiones bajos (_), sin espacios y con 64 caracteres como máximo."]
    if not server.startswith(("http://", "https://")):
        return ["NTFY_SERVER debe empezar por https:// (o bórralo para usar https://ntfy.sh)."]
    headers = {}
    if env("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {env('NTFY_TOKEN')}"
    for m in messages:
        if topic:
            payload: dict[str, Any] = {"topic": topic, "title": m.title, "message": m.body,
                                       "priority": m.priority, "tags": m.tags}
            if m.url:
                payload["click"] = m.url
                payload["actions"] = [{"action": "view", "label": "Ver prenda", "url": m.url}]
            if m.image:
                payload["attach"] = m.image
            try:
                client.post_json(server + "/", payload, headers=headers, check_robots=False)
            except Exception as e:
                errors.append(f"ntfy: {e}")
        if tg_token and tg_chat:
            text = f"<b>{_esc(m.title)}</b>\n{_esc(m.body)}"
            if m.url:
                text += f'\n<a href="{_esc(m.url)}">Ver prenda</a>'
            try:
                if m.image:
                    client.post_json(f"https://api.telegram.org/bot{tg_token}/sendPhoto",
                                     {"chat_id": tg_chat, "photo": m.image, "caption": text[:1000],
                                      "parse_mode": "HTML"}, check_robots=False)
                else:
                    client.post_json(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                     {"chat_id": tg_chat, "text": text, "parse_mode": "HTML"},
                                     check_robots=False)
            except Exception as e:
                errors.append(f"telegram: {type(e).__name__}")  # sin token en el mensaje
    return errors


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
