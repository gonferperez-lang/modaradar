"""Cliente HTTP educado: respeta robots.txt, se identifica con un User-Agent
honesto, espacia las peticiones por dominio y no reintenta de forma agresiva.

Si una web bloquea el acceso (403, captcha, robots.txt) el monitor simplemente
la omite y lo registra: nunca intenta saltarse protecciones anti-bot.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Any


class Blocked(Exception):
    """La web no permite el acceso automatizado (robots.txt o bloqueo explícito)."""


class FetchError(Exception):
    pass


class RateLimited(Blocked):
    """La web pide bajar el ritmo (HTTP 429): se hace una pausa más corta que un bloqueo."""


class SourceSkipped(Exception):
    """El conector no puede ejecutarse (p. ej. faltan credenciales). No es un error."""


class PoliteClient:
    def __init__(self, user_agent: str, delay: float = 2.0, timeout: float = 25.0,
                 respect_robots: bool = True):
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        # Se consultan varias tiendas a la vez: un candado por dominio mantiene
        # la pausa mínima entre peticiones al mismo sitio.
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    # ── robots.txt ──────────────────────────────────────────────────────────
    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock("robots:" + origin):
            if origin not in self._robots:
                self._robots[origin] = self._load_robots(origin)
            return self._robots[origin]

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        try:
            body = self._raw("GET", origin + "/robots.txt")[1]
            rp.parse(body.decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                rp = None  # RFC 9309: robots.txt inexistente → acceso permitido
            else:
                rp = urllib.robotparser.RobotFileParser()
                rp.disallow_all = True  # error de servidor → por prudencia, no acceder
        except Exception:
            rp = urllib.robotparser.RobotFileParser()
            rp.disallow_all = True
        return rp

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self._robots_for(url)
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    # ── peticiones ──────────────────────────────────────────────────────────
    def _throttle(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).netloc
        with self._lock("host:" + host):
            wait = self._last_hit.get(host, 0) + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.monotonic()

    def _raw(self, method: str, url: str, data: bytes | None = None,
             headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        self._throttle(url)
        h = {"User-Agent": self.user_agent, "Accept-Encoding": "identity"}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.status, resp.read()

    def request(self, method: str, url: str, *, data: bytes | None = None,
                headers: dict[str, str] | None = None, check_robots: bool = True) -> bytes:
        if check_robots and not self.allowed(url):
            raise Blocked(f"robots.txt no permite {url}")
        for attempt in (1, 2):
            try:
                return self._raw(method, url, data, headers)[1]
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise Blocked(f"HTTP {e.code} en {url}") from e
                if e.code == 429 and attempt == 2:
                    raise RateLimited(f"HTTP 429 (demasiadas peticiones) en {url}") from e
                if e.code == 429 and attempt == 1:
                    retry = e.headers.get("Retry-After", "")
                    secs = int(retry) if retry.isdigit() else 30
                    if secs <= 60:
                        time.sleep(secs)
                        continue
                    err = RateLimited(f"HTTP 429 (pide esperar {secs}s) en {url}")
                    err.wait_seconds = secs
                    raise err from e
                if 500 <= e.code < 600 and attempt == 1:
                    time.sleep(5)
                    continue
                raise FetchError(f"HTTP {e.code} en {url}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == 1:
                    time.sleep(5)
                    continue
                raise FetchError(f"{type(e).__name__}: {e} en {url}") from e
        raise FetchError(f"Sin respuesta de {url}")

    def get(self, url: str, **kw: Any) -> bytes:
        return self.request("GET", url, **kw)

    def get_json(self, url: str, **kw: Any) -> Any:
        body = self.get(url, headers={"Accept": "application/json"}, **kw)
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            # Las páginas de "verificación" de los anti-bots devuelven HTML en vez de JSON
            raise Blocked(f"Respuesta no-JSON (posible protección anti-bot) en {url}") from e

    def post_json(self, url: str, payload: Any, headers: dict[str, str] | None = None,
                  **kw: Any) -> Any:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        h.update(headers or {})
        body = self.request("POST", url, data=json.dumps(payload).encode(), headers=h, **kw)
        return json.loads(body) if body.strip() else {}

    def post_form(self, url: str, form: dict[str, str], headers: dict[str, str] | None = None,
                  **kw: Any) -> Any:
        h = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        h.update(headers or {})
        body = self.request("POST", url, data=urllib.parse.urlencode(form).encode(), headers=h, **kw)
        return json.loads(body)
