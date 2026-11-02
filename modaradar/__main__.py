"""ModaRadar · ejecuta una pasada de vigilancia.

    python -m modaradar                 # vigila, guarda y avisa
    python -m modaradar --dry-run       # no envía avisos (los muestra en pantalla)
    python -m modaradar --only zara     # solo algunas tiendas
    python -m modaradar --test-notify   # envía un aviso de prueba al móvil
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__, analysis, notify
from .http import Blocked, PoliteClient, RateLimited, SourceSkipped
from .models import now_iso, parse_iso
from .sources import PLATFORMS
from .state import State, thresholds

ROOT = Path(__file__).resolve().parent.parent
DETECTORS_VERSION = "moda-1"   # cámbialo al mejorar la detección para re-sembrar sin avisos
# opciones de una tienda que cambian QUÉ prendas se leen: si cambian, esa tienda se re-siembra sin avisos
FETCH_KEYS = ("platform", "url", "locale", "collections", "max_pages", "collection_pages", "categories",
              "sale_categories", "exclude", "exclude_tags", "min_store_pct", "section", "store_code",
              "women_terms", "pages")


def fetch_hash(store: dict[str, Any]) -> str:
    sel = {k: store[k] for k in FETCH_KEYS if k in store}
    return hashlib.sha1(json.dumps(sel, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]


def topic_fingerprint() -> str:
    """Huella del tema de ntfy para comprobarlo sin publicarlo (los logs de un repo público son visibles)."""
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic:
        return ""
    digest = hashlib.sha256(topic.encode()).hexdigest()[:8]
    source = os.environ.get("NTFY_TOPIC_SOURCE") or "?"
    return f"Tema configurado en: {source} · {len(topic)} caracteres · huella {digest}."


def local_hhmm(dt: datetime) -> str:
    """Hora de España para los mensajes de la app («19:21»)."""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Europe/Madrid")).strftime("%H:%M")
    except Exception:
        return dt.strftime("%H:%M UTC")


def annotate(level: str, message: str) -> None:
    """Muestra el mensaje en el panel «Annotations» de GitHub Actions (además del log)."""
    print(message, file=sys.stderr if level != "notice" else sys.stdout)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        clean = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{level} title=ModaRadar::{clean}")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        cfg = tomllib.load(f)
    ids = [s["id"] for s in cfg.get("stores", [])]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"IDs de tienda repetidos en la configuración: {', '.join(sorted(dupes))}")
    for s in cfg.get("stores", []):
        if s.get("platform") not in PLATFORMS:
            raise SystemExit(f"Tienda {s.get('id')}: plataforma desconocida '{s.get('platform')}'")
    return cfg


def run(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config))
    gen = cfg["general"]
    client = PoliteClient(gen.get("user_agent", f"ModaRadar/{__version__}"),
                          delay=float(gen.get("request_delay_seconds", 2.0)),
                          respect_robots=bool(gen.get("respect_robots_txt", True)))
    store_names = {s["id"]: s["name"] for s in cfg["stores"]}

    if args.test_notify:
        msg = notify.Message(title="✅ ModaRadar conectado",
                             body="Los avisos de rebajas y outlet de Zara, Brownie, Zadig&Voltaire y el resto de "
                                  "tiendas llegarán aquí.",
                             url=(os.environ.get("APP_URL") or "").strip(), tags=["white_check_mark"])
        errs = notify.send([msg], client)
        for err in errs:
            annotate("error", err)
        if not errs:
            annotate("notice", "Aviso de prueba enviado. Si no te llega, revisa que la suscripción de ntfy sea "
                               "exactamente al mismo tema que guardaste en NTFY_TOPIC (al valor, no al nombre). "
                               + topic_fingerprint())
        return 1 if errs else 0

    data_dir = Path(args.data_dir or (ROOT / gen.get("data_dir", "docs/data")))
    prev = _read_status(data_dir)
    if args.min_gap:
        # Las pasadas del programador de GitHub son solo de respaldo: si el reloj
        # (o el botón «Revisar») acaba de revisar, no se repite el trabajo.
        last = parse_iso(prev.get("generated"))
        if last and datetime.now(timezone.utc) - last < timedelta(minutes=args.min_gap):
            mins = int((datetime.now(timezone.utc) - last).total_seconds() // 60)
            print(f"Ya se revisó hace {mins} min: esta pasada de respaldo no hace falta.")
            return 0
    state = State(data_dir)
    only = set(args.only.split(",")) if args.only else None
    results: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []

    max_pause = float(gen.get("blocked_pause_hours", 12))
    max_ratelimit = float(gen.get("ratelimit_pause_hours", 3))
    now_dt = datetime.now(timezone.utc)
    prev_status = {r["id"]: r for r in prev.get("stores", [])}

    def fetch_store(store: dict[str, Any]) -> tuple[dict[str, Any], list | None, dict | None]:
        """Descarga una tienda (en paralelo con las demás). No toca el estado compartido."""
        t0 = time.monotonic()
        res: dict[str, Any] = {"id": store["id"], "name": store["name"], "at": now_iso()}
        items = None
        st = state.store_state.get(store["id"], {})
        retry = parse_iso(st.get("retry_after"))
        if retry and retry > now_dt:
            # La tienda limitó el acceso hace poco: no insistimos hasta que pase la pausa
            res.update(status="blocked", until=retry.isoformat(),
                       message=f"En pausa hasta las {local_hhmm(retry)}: la tienda limita el acceso automático "
                               f"({st.get('reason', 'bloqueo')}). Se reintenta sola.")
            return res, None, None
        every = int(store.get("every_minutes", 0) or 0)
        last_ok = parse_iso(st.get("last_ok"))
        if every and last_ok and now_dt - last_ok < timedelta(minutes=every - 2) and not only:
            # tienda con catálogo grande: se consulta con menos frecuencia
            old = prev_status.get(store["id"], {})
            res.update(status="ok", at=old.get("at", st.get("last_ok")), items=old.get("items"),
                       events=0, message=f"Se consulta cada {every} min para no saturarla")
            return res, None, None
        memo = json.loads(json.dumps(st.get("memo") or {}))
        try:
            fetcher = PLATFORMS[store["platform"]]
            kwargs = {"memo": memo} if "memo" in inspect.signature(fetcher).parameters else {}
            items = fetcher(client, store, cfg, **kwargs)
            res.update(status="ok", items=len(items))
            if memo.get("sections"):
                res["sections"] = memo["sections"]
        except SourceSkipped as e:
            res.update(status="skipped", message=str(e))
        except RateLimited as e:
            res.update(status="blocked", message=str(e), kind="ratelimit",
                       wait=float(getattr(e, "wait_seconds", 0) or 0) / 3600)
        except Blocked as e:
            res.update(status="blocked", message=str(e), kind="blocked")
        except Exception as e:  # una tienda caída no detiene al resto
            res.update(status="error", message=f"{type(e).__name__}: {e}"[:300])
        res["seconds"] = round(time.monotonic() - t0, 1)
        return res, items, memo

    # Si cambian los filtros o los umbrales, prendas que ya existían entran por primera vez y
    # parecerían novedades: esa pasada se guarda en silencio.
    fhash = hashlib.sha1((json.dumps([cfg.get("filters", {}), gen.get("min_store_pct", 20)], sort_keys=True)
                          + DETECTORS_VERSION).encode()).hexdigest()[:12]
    silent = state.filters_hash != fhash
    if silent:
        print("Filtros nuevos o modificados: esta pasada actualiza el catálogo sin enviar avisos.")
    state.filters_hash = fhash

    stores = [s for s in cfg["stores"] if not only or s["id"] in only]
    with ThreadPoolExecutor(max_workers=int(gen.get("parallel_stores", 6))) as pool:
        fetched = list(pool.map(fetch_store, stores))

    for store, (res, items, memo) in zip(stores, fetched):  # fusión en orden, sin hilos
        st = state.store_state.setdefault(store["id"], {})
        kind, wait = res.pop("kind", None), res.pop("wait", 0)
        if kind:
            # pausa progresiva: 1 h, 2 h, 4 h… hasta el máximo (12 h bloqueo, 3 h exceso de peticiones)
            st["fails"] = int(st.get("fails", 0)) + 1
            cap = max_ratelimit if kind == "ratelimit" else max_pause
            hours = max(min(cap, 2 ** (st["fails"] - 1)), wait)
            until = (now_dt + timedelta(hours=hours)).replace(microsecond=0)
            st["retry_after"] = until.isoformat()
            st["reason"] = "demasiadas peticiones" if kind == "ratelimit" else "bloqueo anti-bots"
            res["until"] = st["retry_after"]
            res["message"] = (f"En pausa hasta las {local_hhmm(until)}: la tienda limita el acceso automático "
                              f"({st['reason']}). Se reintenta sola. Detalle: {res.get('message', '')}")[:300]
        elif res["status"] == "ok" and items is not None:
            for k in ("retry_after", "fails", "reason"):
                st.pop(k, None)
            st["last_ok"] = res["at"]
            if memo:
                st["memo"] = memo
        if items is not None:
            # tienda nueva o que ahora lee otras secciones: lo que aparece por primera vez
            # no son rebajas nuevas, así que esta pasada se guarda sin avisos
            h = fetch_hash(store)
            quiet = silent or st.get("cfg") != h
            if quiet and not silent:
                print(f"{store['name']}: configuración nueva; esta pasada actualiza su catálogo sin avisos.")
            st["cfg"] = h
            events = state.merge(store["id"], items, cfg, silent=quiet)
            all_events += events
            res["events"] = len(events)
        results.append(res)
        print(f"[{res['status']:>7}] {store['name']:<22} "
              f"{res.get('items', '-'):>5} rebajadas · {res.get('events', 0)} novedades"
              + (f" · {res['message']}" if res.get("message") else ""), flush=True)

    # Las tiendas que no se han consultado esta vez conservan su último estado
    for s in cfg["stores"]:
        if not any(r["id"] == s["id"] for r in results) and s["id"] in prev_status:
            results.append(prev_status[s["id"]])
    order = {s["id"]: i for i, s in enumerate(cfg["stores"])}
    results.sort(key=lambda r: order.get(r["id"], 999))

    state.prune(int(gen.get("forget_after_days", 7)), {s["id"] for s in cfg["stores"]})
    th = thresholds(cfg)
    report = analysis.analyse(state.products(), cfg["stores"], th, cfg)

    messages = notify.build(all_events, cfg, store_names)
    notify_errors: list[str] = []
    if messages:
        if args.dry_run:
            for m in messages:
                print(f"  ✉ {m.title} — {m.body.splitlines()[0]}")
        else:
            notify_errors = notify.send(messages, client)
            for err in notify_errors:
                annotate("warning", err)

    n = cfg.get("notifications", {})
    status = {
        "version": __version__,
        "generated": now_iso(),
        "stores": results,
        "events_this_run": len(all_events),
        "notifications_sent": 0 if args.dry_run else len(messages) - len(notify_errors),
        "notify_errors": notify_errors,
        "watchlist": n.get("watchlist", []),
        "categories": n.get("categories", ["ropa"]),
        "mis_tallas": n.get("mis_tallas", []),
        "umbral": {k: round(v * 100) for k, v in th.items()},
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),   # para el botón «Revisar» de la app
        "destacadas": [{"id": s["id"], "name": s["name"], "short": s.get("short") or s["name"]}
                       for s in cfg["stores"] if s.get("destacada")],
        # últimas revisiones y quién las lanzó (reloj, GitHub, botón…): la app las muestra
        "history": ([{"at": now_iso(), "by": os.environ.get("MODARADAR_TRIGGER") or "local"}]
                    + [h for h in prev.get("history", []) if isinstance(h, dict)])[:24],
    }
    changed = state.save({"stores.json": report, "status.json": status})
    print(f"{len(all_events)} novedades · {len(messages)} avisos · archivos actualizados: "
          f"{', '.join(changed) or 'ninguno'}")
    return 0


def _read_status(data_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((data_dir / "status.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="modaradar", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--data-dir", help="carpeta de datos (por defecto, la de config.toml)")
    ap.add_argument("--only", help="ids de tienda separados por comas")
    ap.add_argument("--dry-run", action="store_true", help="no envía avisos")
    ap.add_argument("--test-notify", action="store_true", help="envía un aviso de prueba")
    ap.add_argument("--min-gap", type=float, default=0, metavar="MIN",
                    help="no hace nada si la última revisión fue hace menos de MIN minutos")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
