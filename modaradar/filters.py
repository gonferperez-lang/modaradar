"""Texto: normalización, filtros, categoría (ropa, calzado…), tipo de prenda y tallas."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def fold(text: str) -> str:
    """minúsculas + sin acentos + espacios normalizados."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _contains(haystack: str, needle: str) -> bool:
    needle = fold(needle)
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def matches_any(text: str, words: Iterable[str]) -> bool:
    t = fold(text)
    return any(_contains(t, w) for w in words)


# ── solo mujer ──────────────────────────────────────────────────────────────
# (las tiendas de mujer a veces tienen una línea infantil o de hombre)
NOT_WOMEN = [
    "hombre", "caballero", "homme", "uomo", "herren", "men", "man", "mens", "men's",
    "nino", "nina", "ninos", "ninas", "infantil", "kids", "kid", "junior", "bebe", "baby", "girl", "girls",
    "boy", "boys", "enfant", "enfants", "bambina", "bambino", "bimba", "teen",
]


def is_women(text: str, extra_exclude: Iterable[str] = ()) -> bool:
    return not matches_any(text, [*NOT_WOMEN, *extra_exclude])


# ── categoría ───────────────────────────────────────────────────────────────
# lo que no es moda (se descarta siempre)
_NOT_FASHION = re.compile(
    r"\bperfumes?\b|\bfragancia|eau de (parfum|toilette)|\bcolonia\b|\bvelas?\b|\btazas?\b|tarjeta regalo|gift ?card"
    r"|carte cadeau|\bmaquillaje\b|\bpintalabios\b|\blabial\b|\bcrema\b|\bserum\b|\bbody milk\b|\bhome\b|\blibro\b"
    r"|\bpackaging\b|\bbolsa de regalo\b|\bcaja regalo\b|\bmascarilla\b|\bbeauty\b|\bbelleza\b|\bambientador"
    r"|\bseguro\b|\bdonacion\b|\bshipping\b|\benvio\b|\btoallas?\b|\bbotellas?\b|\bbalon(es)?\b"
)
_SHOES = re.compile(
    r"\bzapat(o|os|illa|illas)\b|\bsandalias?\b|\bbotas?\b|\bbotin(es)?\b|\bbotines\b|\bbailarinas?\b|\bmocasin(es)?\b"
    r"|\bsneakers?\b|\bdeportivas?\b|\bshoes?\b|\bchaussures?\b|\bscarp[ae]\b|\balpargatas?\b|\bespadrilles?\b"
    r"|\bsalon(es)?\b|\bmules?\b|\bzuecos?\b|\bchanclas?\b|\bboots?\b|\bminibotas?\b|\bankle boot|\bstiletto|\bslingback"
    r"|\bbambas?\b|\brunning\b|\bzapatos\b|\bcalzado\b|\bfootwear\b|\bbaskets?\b|\bderbies\b|\bloafers?\b|\bpumps?\b"
    r"|\btacon\b"
)
_BAGS = re.compile(
    r"\bbols(o|os|ito|itos|a|as)\b|\bbags?\b|\bhandbags?\b|\bsac\b|\bborsa\b|\bmochilas?\b|\bclutch\b|\bbandolera\b"
    r"|\bshopper\b|\btote\b|\brinonera\b|\bmonederos?\b|\bcarteras?\b|\bwallets?\b|\bneceser(es)?\b|\bpurses?\b"
    r"|\bpochette\b|\bcabas\b|\bcrossbody\b|\bmarroquineria\b|\bleather goods\b|\btarjeteros?\b"
)
_ACCESSORIES = re.compile(
    r"\bbisuteria\b|\bjoyas?\b|\bjewel|\bcollar(es)?\b|\bpendientes?\b|\banillos?\b|\bpulseras?\b|\bbroches?\b"
    r"|\bcinturon(es)?\b|\bbelts?\b|\bgorr[oa]s?\b|\bsombreros?\b|\bbufandas?\b|\bpanuelos?\b|\bfular(es)?\b"
    r"|\bguantes?\b|\bmitones\b|\bcalcetines\b|\bsocks?\b|\bmedias\b|\bpantys?\b|\bgafas\b|\bsunglasses\b|\brelo(j|jes)\b"
    r"|\bwatch(es)?\b|\bdiademas?\b|\bcoleteros?\b|\bpinzas?\b|\bhorquillas?\b|\bcharms?\b|\bllaveros?\b|\bparaguas\b"
    r"|\bfundas?\b|\bearrings?\b|\bnecklaces?\b|\bbracelets?\b|\brings?\b|\bscar(f|ves)\b|\bhats?\b|\bcaps?\b"
    r"|\bbeanie\b|\bchal(es)?\b|\bshawls?\b|\bestolas?\b|\bgloves?\b|\bhair\b|\bbijoux\b|\becharpe\b|\bfoulard\b"
    r"|\bceinture\b|\bchapeau\b|\bcomplementos?\b|\baccesorios?\b|\baccessor(y|ies)\b|\bcomples\b|\bgorro\b"
    r"|\bboina\b|\bclips?\b|\bbandanas?\b|\bfoulards?\b|\bfoular\b|\bcalcetin\b|\bbombonera\b|\bcintas? (para el )?pelo\b|\bmunequeras?\b|\bcintas?\b"
)

# tipo de prenda (en orden: «chaqueta de punto» es punto, «vestido camisero» es vestido…)
PRENDAS: list[tuple[str, str, re.Pattern[str]]] = [
    ("monos", "Monos", re.compile(r"\bmonos?\b|\bjumpsuits?\b|\bpetos?\b|\bcombinaison|\bplaysuit|\btuta\b|\bovershirt dress\b")),
    ("vestidos", "Vestidos", re.compile(r"\b(?:mini|maxi)?vestidos?\b|\bdress(es)?\b|\brobes?\b|\babit[oi]\b|\bkleid")),
    ("faldas", "Faldas", re.compile(r"\b(?:mini|maxi)?faldas?\b|\bskirts?\b|\bjupes?\b|\bgonn[ae]\b|\bskort")),
    ("bano", "Baño", re.compile(r"\bbikinis?\b|\bbanadores?\b|\bswim|\bmaillot de bain\b|\btrikini\b|\bcostume\b|\bpareos?\b")),
    ("lenceria", "Lencería y pijamas", re.compile(
        r"\blenceria\b|\bsujetador(es)?\b|\bbragas?\b|\bbralettes?\b|\bbras?\b|\bpijamas?\b|\bcamison\b|\bbatas?\b"
        r"|\bunderwear\b|\blingerie\b|\bculotte (de encaje|lencera)\b|\bintimates\b")),
    ("punto", "Punto: jerséis y cárdigans", re.compile(
        r"\bchaquetas? de punto\b|\bjersei?s?\b|\bjerseys?\b|\bsueter(es)?\b|\bsweaters?\b|\bcardigans?\b|\bcardigan\b|\bpunto\b|\bknit(s|wear)?\b"
        r"|\bpull(over)?s?\b|\bmaglion[ei]\b|\bmaglia\b|\bgilet\b|\bcachemir[ae]?\b|\bcashmere\b|\bchaleco de punto\b|\btricot\b")),
    ("sudaderas", "Sudaderas", re.compile(r"\bsudaderas?\b|\bsweatshirts?\b|\bhoodies?\b|\bsweats?\b|\bfelpa\b")),
    ("abrigos", "Abrigos, chaquetas y blazers", re.compile(
        r"\babrigos?\b|\bchaquet(a|as|on|ones)\b|\bcazadoras?\b|\bblazers?\b|\bamericanas?\b|\bgabardinas?\b|\btrench\b"
        r"|\bparkas?\b|\bplumifer[oa]s?\b|\banoraks?\b|\bchalecos?\b|\bcapas?\b|\bcapes?\b|\bcoats?\b|\bjackets?\b"
        r"|\bmanteaux?\b|\bvestes?\b|\bcappott[oi]\b|\bgiacc[ah]e?\b|\bpuffers?\b|\bbombers?\b|\bsobrecamisa\b|\bovershirt\b"
        r"|\bperfecto\b|\bcaban\b|\bpeacoat\b|\bponchos?\b|\bsastre\b|\bwaistcoats?\b|\bvests?\b|\bdown jacket\b|\boutwear\b|\boutwerwear\b|\bouterwear\b|\bdoudoune\b|\bblouson\b")),
    ("vaqueros", "Vaqueros", re.compile(r"\bpantalon(es)? vaquer[oa]s?\b|\bvaquer[oa]s?\b|\bjeans?\b|\btejan[oa]s?\b|\bdenim\b")),
    ("shorts", "Shorts y bermudas", re.compile(r"\bshorts?\b|\bbermudas?\b|\bpantalon(es)? cort[oa]s?\b")),
    ("pantalones", "Pantalones", re.compile(
        r"\bpantalon(es)?\b|\btrousers?\b|\bpants?\b|\bculottes?\b|\bleggings?\b|\bjoggers?\b|\bchinos?\b|\bpalazzo\b"
        r"|\bpantaloni?\b|\bcargo\b|\bmallas?\b|\btights\b|\bleggins\b")),
    ("camisas", "Camisas y blusas", re.compile(
        r"\bcamisas?\b|\bblusas?\b|\bshirts?\b|\bblouses?\b|\bchemises?\b|\bcamicie?a?\b|\btunicas?\b|\bcamisola\b|\bsayo\b")),
    ("camisetas", "Camisetas y tops", re.compile(
        r"\bcamisetas?\b|\btops?\b|\bt-?shirts?\b|\btees?\b|\bbod(y|ies)\b|\bbodysuits?\b|\bpolos?\b|\btank\b|\bcorpi[nñ]o\b"
        r"|\bcorset\b|\bbustier\b|\bbrassiere\b|\bbandeau\b|\bhenley\b|\bcrop\b|\btirantes\b|\bcanale\b|\bdebardeur\b"
        r"|\btop\b|\bblusones?\b|\bparte de arriba\b|\bmaillot\b")),
    ("conjuntos", "Conjuntos", re.compile(r"\bconjuntos?\b|\bsets?\b|\bco-?ord\b|\btotal look\b|\btraje\b|\bsuit\b")),
]
PRENDA_NAMES = {k: label for k, label, _ in PRENDAS} | {"otras": "Otras prendas"}


def _first_match(text: str) -> tuple[str, str] | None:
    """La palabra que aparece antes decide («Vestido con cinturón» es un vestido; «Bolso tipo camisa», un bolso)."""
    best: tuple[int, str, str] | None = None
    for key, _, rx in PRENDAS:
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), "ropa", key)
    for cat, rx in (("calzado", _SHOES), ("bolsos", _BAGS), ("accesorios", _ACCESSORIES)):
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), cat, "")
    return (best[1], best[2]) if best else None


def categorize(title: str, ptype: str = "", hint: str = "") -> tuple[str, str]:
    """(categoría, prenda). Categoría: ropa · calzado · bolsos · accesorios · "" (no es moda: descartar).

    `ptype`/`hint`: la clasificación de la propia tienda (tipo de producto, familia de Zara, etiquetas).
    Se usa cuando el título no lo deja claro.
    """
    t, h = fold(title), fold(f"{ptype} {hint}")
    if _NOT_FASHION.search(t):
        return "", ""
    found = _first_match(t) or _first_match(h)
    if found:
        return found
    if _NOT_FASHION.search(h):
        return "", ""
    return "ropa", "otras"


# ── tallas ──────────────────────────────────────────────────────────────────
ONE_SIZE = {"U", "TU", "UNICA", "UNICO", "ONE SIZE", "ONESIZE", "OS", "T.U.", "TALLA UNICA", "DEFAULT TITLE", "UNIQUE",
            "TAILLE UNIQUE", "UNI"}
_SPLIT = re.compile(r"[\s/\-–,()|+]+")


def size_tokens(label: str) -> set[str]:
    """«XS-S» → {XS, S} · «M/L» → {M, L} · «EU 38» → {EU, 38} · «Petite (P)» → {PETITE, P}."""
    f = fold(label).upper().strip()
    if f in ONE_SIZE:
        return {"*"}
    return {x for x in _SPLIT.split(f) if x}


def fits(sizes: list[str] | None, mine: Iterable[str]) -> bool:
    """¿Queda alguna de mis tallas? Si la tienda no publica tallas (None), se da por buena."""
    mine = {fold(m).upper() for m in mine if str(m).strip()}
    if not mine or sizes is None:
        return True
    for s in sizes:
        tok = size_tokens(s)
        if "*" in tok or tok & mine:
            return True
    return False
