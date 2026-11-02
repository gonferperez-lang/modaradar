"""Tests de ModaRadar (sin red): python -m unittest discover -s tests -v"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modaradar import analysis, notify  # noqa: E402
from modaradar.filters import categorize, fits, is_women, size_tokens  # noqa: E402
from modaradar.models import Product  # noqa: E402
from modaradar.sources import PLATFORMS, nike, shopify, zadig, zara  # noqa: E402
from modaradar.state import State, store_threshold, thresholds  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


CFG = {
    "general": {"min_store_pct": 20, "currency": "EUR"},
    "filters": {"exclude": ["tarjeta regalo"]},
    "notifications": {"min_discount_pct": 40, "destacadas_min_pct": 30, "chollo_pct": 50,
                      "notify_price_drop_pct": 10, "categories": ["ropa"], "mis_tallas": [], "max_per_run": 3,
                      "watchlist": ["cachemir"]},
    "stores": [
        {"id": "zara", "name": "Zara", "platform": "zara", "destacada": True, "url": "https://www.zara.com"},
        {"id": "brownie", "name": "Brownie", "platform": "shopify", "destacada": True, "url": "https://www.browniespain.com"},
        {"id": "lola", "name": "Lola", "platform": "shopify", "url": "https://lola.example"},
    ],
}


def prod(id_: str, store: str = "lola", price: float = 50, original: float = 100, **kw) -> Product:
    base = dict(id=f"{store}:{id_}", store=store, title=kw.pop("title", f"Vestido {id_}"), url=f"https://x/{id_}",
                price=price, original=original, available=True, category="ropa", prenda="vestidos", sizes=["S", "M"])
    base.update(kw)
    return Product(**base)


class TestFilters(unittest.TestCase):
    def test_categorize(self):
        cases = {
            "Vestido con cinturón": ("ropa", "vestidos"),
            "Chaqueta de punto": ("ropa", "punto"),
            "Chaqueta tweed": ("ropa", "abrigos"),
            "Pantalón vaquero recto": ("ropa", "vaqueros"),
            "Camisa vaquera": ("ropa", "camisas"),
            "Camiseta básica": ("ropa", "camisetas"),
            "Falda pantalón": ("ropa", "faldas"),
            "Bolso shopper piel": ("bolsos", ""),
            "Sandalia tacón": ("calzado", ""),
            "Pendientes aro": ("accesorios", ""),
            "Eau de parfum 100 ml": ("", ""),
            "Tarjeta regalo": ("", ""),
        }
        for title, want in cases.items():
            self.assertEqual(categorize(title), want, title)
        # la clasificación de la tienda ayuda cuando el título no lo dice
        self.assertEqual(categorize("KONGSBERG", "COATS"), ("ropa", "abrigos"))
        self.assertEqual(categorize("Modelo 1981", "", "HANDBAGS"), ("bolsos", ""))

    def test_women_only(self):
        self.assertTrue(is_women("Vestido midi lunares"))
        self.assertTrue(is_women("Jersey women cashmere"))
        self.assertFalse(is_women("Vestido corto de niña"))
        self.assertFalse(is_women("Camisa hombre lino"))

    def test_sizes(self):
        self.assertEqual(size_tokens("XS-S"), {"XS", "S"})
        self.assertEqual(size_tokens("Talla única"), {"*"})
        self.assertTrue(fits(["XS-S", "M-L"], ["s"]))
        self.assertFalse(fits(["XL"], ["S", "M"]))
        self.assertTrue(fits(None, ["S"]))          # la tienda no publica tallas: no se descarta
        self.assertTrue(fits(["U"], ["38"]))         # talla única
        self.assertTrue(fits(["S"], []))             # sin tallas configuradas
        self.assertFalse(fits([], ["S"]))            # agotada en todas


class TestShopify(unittest.TestCase):
    def test_parse_discounts_and_sizes(self):
        data = fixture("shopify.json")["products"]
        store = {"id": "brownie", "name": "Brownie"}
        out = shopify.parse(data, store, CFG, "https://www.browniespain.com/es-es")
        ids = {p.id for p in out}
        # solo las rebajadas (las 3 primeras); ni la de precio completo ni la infantil
        self.assertEqual(len(out), 3, [p.title for p in out])
        self.assertNotIn(f"brownie:{data[3]['id']}", ids)
        for p in out:
            self.assertGreaterEqual(p.discount, 0.2)
            self.assertLess(p.price, p.original)
            self.assertTrue(p.url.startswith("https://www.browniespain.com/es-es/products/"))
            self.assertIn("width=500", p.image)
            self.assertIsInstance(p.sizes, list)
            self.assertEqual(p.category, "ropa")

    def test_kids_line_excluded_by_sizes(self):
        kid = copy.deepcopy(fixture("shopify.json")["products"][4])
        kid["title"] = "Vestido corto cuadros"   # sin «niña» en el título: lo delatan las tallas (4-5Yrs…)
        out = shopify.parse([kid], {"id": "cf"}, CFG, "https://cf.example")
        self.assertEqual(out, [])

    def test_min_store_pct(self):
        p = copy.deepcopy(fixture("shopify.json")["products"][0])
        for v in p["variants"]:
            v["compare_at_price"] = str(round(float(v["price"]) * 1.1, 2))   # solo un 9 % de rebaja
        self.assertEqual(shopify.parse([p], {"id": "b"}, CFG, "https://b.example"), [])


class TestZara(unittest.TestCase):
    def test_discover_sale_sections(self):
        found = zara.discover(fixture("zara_menu.json"))
        ids = [c["id"] for c in found]
        self.assertIn(2419737, ids)          # SPECIAL PRICES (ya resuelta la redirección)
        self.assertIn(999002, ids)           # REBAJAS de mujer (nueva)
        self.assertNotIn(2, ids)             # las de hombre no

    def test_parse(self):
        out = zara.parse(fixture("zara_products.json"), {"id": "zara"}, "https://www.zara.com/es/es", 0.2, "Special prices")
        self.assertEqual(len(out), 3)
        p = out[0]
        self.assertEqual((p.price, p.original), (15.99, 29.95))
        self.assertEqual(p.prenda, "pantalones")
        self.assertIsNone(p.sizes)
        self.assertRegex(p.url, r"^https://www\.zara\.com/es/es/[a-z0-9-]+-p\d+\.html\?v1=\d+$")
        self.assertTrue(p.image.startswith("https://static.zara.net/assets/public/"))

    def test_fetch_uses_memo(self):
        calls = []

        class Fake:
            def get_json(self, url):
                calls.append(url)
                return fixture("zara_menu.json") if "categories" in url else fixture("zara_products.json")

        memo: dict = {}
        store = {"id": "zara", "url": "https://www.zara.com", "locale": "/es/es"}
        zara.fetch(Fake(), store, CFG, memo=memo)
        n = len(calls)
        zara.fetch(Fake(), store, CFG, memo=memo)   # el menú no se vuelve a pedir
        self.assertEqual(sum("categories?" in c for c in calls), 1)
        self.assertEqual(len(calls) - n, n - 1)


class TestZadig(unittest.TestCase):
    def test_sale_price(self):
        price = {"regular": {"value": 295}, "special": {"value": 177, "from": "2026-01-01T00:00:00+00:00",
                                                       "to": "2099-01-01T00:00:00+00:00"}}
        self.assertEqual(zadig.sale_price(price), (177.0, 295.0))
        expired = {"regular": {"value": 295}, "special": {"value": 100, "to": "2020-01-01T00:00:00+00:00"}}
        self.assertEqual(zadig.sale_price(expired), (295.0, 295.0))
        self.assertEqual(zadig.sale_price({"regular": {"value": 295}, "special": []}), (295.0, 295.0))

    def test_parse(self):
        out = zadig.parse(fixture("zadig_products.json")["products"], {"id": "zadig"}, 0.2)
        self.assertEqual(len(out), 1)        # el segundo tiene la rebaja caducada
        p = out[0]
        self.assertEqual((p.price, p.original), (177.0, 295.0))
        self.assertEqual(p.prenda, "camisas")
        self.assertTrue(p.url.startswith("https://zadig-et-voltaire.com/eu/es/p/"))
        self.assertTrue(p.image.startswith("https://media.zadig-et-voltaire.com/product/"))
        self.assertTrue(p.sizes)


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_is_silent_then_new_items_notify(self):
        s = self.state
        self.assertEqual(s.merge("lola", [prod("a")], CFG), [])           # primera pasada: memoriza
        ev = s.merge("lola", [prod("a"), prod("b", price=55), prod("c", price=70)], CFG)
        # b (−45 %) avisa; c (−30 %) no llega al 40 % de una tienda normal
        self.assertEqual([(e["type"], e["id"]) for e in ev], [("new", "lola:b")])
        self.assertEqual(ev[0]["pct"], 45)
        self.assertNotIn("hot", ev[0])

    def test_featured_threshold_and_hot(self):
        s = self.state
        s.merge("zara", [], CFG)
        ev = s.merge("zara", [prod("x", "zara", price=70), prod("y", "zara", price=40)], CFG)
        self.assertEqual({e["id"] for e in ev}, {"zara:x", "zara:y"})   # −30 % basta en una destacada
        y = next(e for e in ev if e["id"] == "zara:y")
        self.assertTrue(y["hot"] and y["dest"])

    def test_price_drop_and_restock(self):
        s = self.state
        s.merge("lola", [prod("a", price=60), prod("b", price=50, available=False)], CFG)
        ev = s.merge("lola", [prod("a", price=50), prod("b", price=50, available=True)], CFG)
        kinds = {e["id"]: e["type"] for e in ev}
        # a: de −40 % a −50 % (baja un 17 %) · b: vuelve a haber stock
        self.assertEqual(kinds, {"lola:a": "price_drop", "lola:b": "restock"})
        drop = next(e for e in ev if e["id"] == "lola:a")
        self.assertEqual(drop["old_price"], 60)
        self.assertTrue(drop["minimo"])
        # una bajada pequeña (2 %) que no cruza el umbral no avisa
        self.assertEqual(s.merge("lola", [prod("a", price=49), prod("b", price=50)], CFG), [])

    def test_crossing_threshold_counts_as_drop(self):
        s = self.state
        s.merge("lola", [prod("a", price=75)], CFG)                  # −25 %: guardada, sin aviso
        ev = s.merge("lola", [prod("a", price=58)], CFG)              # −42 %
        self.assertEqual([e["type"] for e in ev], ["price_drop"])

    def test_unseen_and_comeback(self):
        s = self.state
        s.merge("lola", [prod("a")], CFG)
        s.merge("lola", [], CFG)
        self.assertIn("unseen", s.items["lola:a"].extra)
        self.assertEqual(s.merge("lola", [prod("a")], CFG), [])   # un despiste de una pasada no avisa
        self.assertNotIn("unseen", s.items["lola:a"].extra)
        s.merge("lola", [], CFG)
        s.items["lola:a"].extra["unseen"] = "2026-01-01T00:00:00+00:00"   # lleva días sin aparecer
        ev = s.merge("lola", [prod("a")], CFG)       # vuelve a estar rebajada
        self.assertEqual([e["type"] for e in ev], ["restock"])

    def test_my_size_back(self):
        cfg = copy.deepcopy(CFG)
        cfg["notifications"]["mis_tallas"] = ["M"]
        s = self.state
        s.merge("lola", [prod("a", sizes=["S"])], cfg)
        ev = s.merge("lola", [prod("a", sizes=["S", "M"])], cfg)
        self.assertEqual([e["type"] for e in ev], ["restock"])

    def test_save_roundtrip(self):
        s = self.state
        s.merge("lola", [prod("a", sizes=[])], CFG)
        s.save({})
        again = State(self.tmp.name)
        p = again.items["lola:a"]
        self.assertEqual(p.sizes, [])                 # [] (agotada) no se confunde con None
        self.assertEqual(p.discount, 0.5)
        row = json.loads((Path(self.tmp.name) / "products.json").read_text().splitlines()[1])
        self.assertEqual(row["pct"], 50)


class TestNotify(unittest.TestCase):
    def events(self):
        s = State(tempfile.mkdtemp())
        s.merge("zara", [], CFG)
        s.merge("lola", [], CFG)
        return (s.merge("zara", [prod("z1", "zara", title="Pantalón pliegues", price=15.99, original=29.95, sizes=None)], CFG)
                + s.merge("lola", [prod("l1", price=45, sizes=["XS", "S"]),
                                   prod("l2", price=30, title="Bolso shopper", category="bolsos", prenda="")], CFG))

    def test_build(self):
        msgs = notify.build(self.events(), CFG, {"zara": "Zara", "lola": "Lola"})
        self.assertEqual(len(msgs), 2)   # el bolso no avisa (categoría «ropa»)
        z = next(m for m in msgs if "Zara" in m.title)
        self.assertTrue(z.title.startswith("⭐ Zara · −47 %"), z.title)
        self.assertIn("15,99 € (antes 29,95 €)", z.body)
        self.assertIn("Tallas: mira en la web", z.body)
        lola = next(m for m in msgs if "Lola" in m.title)
        self.assertIn("🔥", lola.title)
        self.assertEqual(lola.priority, 5)
        self.assertIn("Tallas: XS, S", lola.body)

    def test_size_filter_and_summary(self):
        cfg = copy.deepcopy(CFG)
        cfg["notifications"]["mis_tallas"] = ["L"]
        msgs = notify.build(self.events(), cfg, {})
        self.assertEqual(len(msgs), 1)   # Lola no tiene la L; Zara no publica tallas → sí avisa
        cfg["notifications"].update(mis_tallas=[], max_per_run=1, categories=["ropa", "bolsos"])
        msgs = notify.build(self.events(), cfg, {"zara": "Zara", "lola": "Lola"})
        self.assertEqual(len(msgs), 1)
        self.assertTrue(msgs[0].title.startswith("🛍️ 3 rebajas más"), msgs[0].title)

    def test_euros(self):
        self.assertEqual(notify.euros(15.99), "15,99 €")
        self.assertEqual(notify.euros(1295.0), "1.295 €")


class TestAnalysisAndConfig(unittest.TestCase):
    def test_analyse(self):
        ps = [prod("a", price=40), prod("b", price=80), prod("c", price=50, available=False)]
        rep = analysis.analyse(ps, CFG["stores"], thresholds(CFG))
        lola = next(r for r in rep["stores"] if r["id"] == "lola")
        self.assertEqual((lola["items"], lola["avg"], lola["max"], lola["big"], lola["alert"]), (2, 40, 60, 1, 1))
        self.assertTrue(rep["stores"][0].get("destacada"))

    def test_config(self):
        with (ROOT / "config.toml").open("rb") as f:
            cfg = tomllib.load(f)
        ids = [s["id"] for s in cfg["stores"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in cfg["stores"]:
            self.assertIn(s["platform"], PLATFORMS, s["id"])
        self.assertEqual({s["id"] for s in cfg["stores"] if s.get("destacada")}, {"zara", "brownie", "zadig"})
        self.assertTrue({"poloclub", "scuffers", "emestudios", "yuxus", "nike"} <= set(ids))


class TestMixedBrandsAndNike(unittest.TestCase):
    def shop_item(self, ptype="Woman Top Standard", tags=("woman",), handle="top-azul"):
        return {"id": 1, "title": "Top azul", "handle": handle, "product_type": ptype, "tags": list(tags),
                "options": [{"name": "Size", "position": 1}],
                "variants": [{"id": 9, "option1": "S", "price": "20.00", "compare_at_price": "40.00", "available": True}],
                "images": [{"src": "https://cdn.shopify.com/x.jpg?v=1"}]}

    def test_women_terms(self):
        store = {"id": "scuffers", "women_terms": ["woman", "girl", "mujer"]}
        self.assertEqual(len(shopify.parse([self.shop_item()], store, CFG, "https://s.example")), 1)
        man = self.shop_item(ptype="Unisex Hoodie", tags=("new",))
        self.assertEqual(shopify.parse([man], store, CFG, "https://s.example"), [])
        polo = self.shop_item(ptype="MUJER > TEXTIL > Jersey", tags=())
        self.assertEqual(len(shopify.parse([polo], {"id": "polo", "women_terms": ["mujer"]}, CFG, "https://p.example")), 1)

    def test_product_url_template(self):
        store = {"id": "eme", "product_url": "https://emestudios.com/es/es/product/{handle}"}
        out = shopify.parse([self.shop_item(handle="duke-sand-pants")], store, CFG, "https://eme-official.myshopify.com")
        self.assertEqual(out[0].url, "https://emestudios.com/es/es/product/duke-sand-pants")

    def test_nike_parse(self):
        html = (FIX / "nike_wall.html").read_text(encoding="utf-8")
        out = nike.parse(html, {"id": "nike", "url": "https://www.nike.com"}, 0.2)
        # 3 de mujer rebajadas; fuera la de hombre y la que no tiene rebaja
        self.assertEqual(len(out), 3, [p.title for p in out])
        p = out[0]
        self.assertEqual((p.price, p.original), (31.49, 44.99))
        self.assertEqual((p.category, p.prenda), ("ropa", "camisetas"))
        self.assertNotIn("Mujer", p.title)
        self.assertTrue(p.url.startswith("https://www.nike.com/es/t/"))
        self.assertEqual(out[1].prenda, "pantalones")   # leggings
        with self.assertRaises(Exception):
            nike.parse("<html>sin datos</html>", {"id": "nike"}, 0.2)

    def test_store_threshold_and_partial(self):
        cfg = copy.deepcopy(CFG)
        cfg["stores"].append({"id": "polo", "name": "Polo", "platform": "shopify", "min_discount_pct": 60})
        cfg["stores"].append({"id": "nike", "name": "Nike", "platform": "nike", "partial": True})
        self.assertEqual(store_threshold(cfg, "polo"), 0.6)
        self.assertEqual(store_threshold(cfg, "zara"), 0.3)
        self.assertEqual(store_threshold(cfg, "lola"), 0.4)
        s = State(tempfile.mkdtemp())
        s.merge("polo", [], cfg)
        ev = s.merge("polo", [prod("a", "polo", price=45), prod("b", "polo", price=35)], cfg)
        self.assertEqual([e["id"] for e in ev], ["polo:b"])          # −55 % no llega a su 60 %
        s.merge("nike", [prod("n", "nike")], cfg)
        s.merge("nike", [], cfg)                                      # ya no sale entre las más nuevas
        self.assertNotIn("unseen", s.items["nike:n"].extra)
        s.items["nike:n"].extra["unseen"] = "2026-01-01T00:00:00+00:00"
        self.assertEqual(s.merge("nike", [prod("n", "nike")], cfg), [])   # su vuelta no es reposición


if __name__ == "__main__":
    unittest.main()
