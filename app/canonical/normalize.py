"""Canonical product normalizer v3 (pure: no network, no LLM, no database).

Port of ``tools/canonical_coverage_proto.py`` (rules r1-r5, q1-q10; see
``docs/canonical/canonical-coverage-v3.md``) plus the corrections ``c1``-``c7``:

- c1 ``Original`` / ``Flores e Vegetais`` are real brands (not in the invalid list)
- c2 parser: YOPRO/PRO+ (protein), ``gts`` (gratis), ranges ``350g-370g``, ``30CP``
- c3 kits with two brands are not given a (guessed) brand
- c4 ``Porta Ovos Duzia`` is not an egg nor a dozen
- c5 spelling ``Lo'r`` -> ``L'Or``
- c6 department noise (Baly in Hortifruti, Aurora in Bazar) is flagged
- c7 Dalben/Davitta have no brand field (flagged, not treated as "invalid")

Two levels:
  * row level: ``parse_title`` and ``normalize_row`` (needs a ``BrandDictionary``);
  * corpus level: ``normalize_corpus`` builds the dictionary from the rows and assigns
    the coverage group (A1/A2/B1/B2/B3/B4/C/R), which depends on cross-retailer matches.
"""

from __future__ import annotations

import collections
import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.catalog.taxonomy import canonical_department

NORMALIZER_VERSION = "canon-3.0"
PIPELINE_VERSION = "canonical-v1"

V2_RULES = frozenset({"r1", "r2", "r3", "r4", "r5"})
V3_RULES = V2_RULES | {f"q{i}" for i in range(1, 11)}
CORRECTIONS = frozenset({"c1", "c2", "c3", "c4", "c5", "c6", "c7"})
ALL_RULES = V3_RULES | CORRECTIONS
GROUPS = ("A1", "A2", "B1", "B2", "B3", "B4", "C", "R")

# --------------------------------------------------------------------------- text helpers


def fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s if isinstance(s, str) else "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def alnum(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(s))


def toks(s: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(s))


# --------------------------------------------------------------------------- regexes

NUM = r"(\d+(?:[.,]\d+)?)"
UNIT = r"(kgs?|quilos?|kilos?|gramas?|grs?|g|mg|litros?|lts?|lt|l|ml|cl|mls)"
SIZE_V1 = re.compile(r"(?<![\w,.])" + NUM + r"\s*" + UNIT + r"(?![a-z0-9])", re.I)
SIZE_V2 = re.compile(r"(?<![\w,.%])" + NUM + r"\s*" + UNIT + r"(?!\w)", re.I)
MULT = re.compile(r"(?<![\w,.])(\d{1,3})\s*[x×]\s*" + NUM + r"\s*" + UNIT + r"(?![a-z0-9])", re.I)
CADA = re.compile(
    r"(?<![\w,.])(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?|pe[cç]as?|sach[eê]s?|tabletes?|barras?)\s*(?:de|x)\s*"
    + NUM + r"\s*" + UNIT + r"\b(?:\s*cada)?", re.I)
CADA8 = re.compile(
    r"(?<![\w,.])(?:c\s*/\s*|com\s+)?(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?|pe[cç]as?|sach[eê]s?|tabletes?|barras?)\.?\s*"
    r"(?:(?:de|x)\s*" + NUM + r"\s*" + UNIT + r"\b|" + NUM + r"\s*" + UNIT + r"\s*cada\b)", re.I)
LEVE8 = re.compile(r"(?:leve|lv)\s*(" + NUM + r"\s*" + UNIT + r"?)\s*(?:pague|pg)\s*" + NUM + r"\s*" + UNIT + r"?", re.I)
LEVE = re.compile(r"leve\s*(" + NUM + r"\s*" + UNIT + r"?)\s*pague\s*" + NUM + r"\s*" + UNIT + r"?", re.I)
NONSIZE_AFTER = re.compile(r"^\s*(?:de\s+)?(?:prote|fibra|vitamin|c[aá]lcio|colag|a[cç][uú]car|s[oó]dio|gordura|carbo)", re.I)
PACK_STRICT = [
    re.compile(r"\bpack\s*(?:c/|com)?\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(?:cx|caixa|fardo)\s*(?:c/|com|de|:)?\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g|ml|l\b))", re.I),
]
CSLASH = re.compile(r"\bc\s*/\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g|ml|l\b))", re.I)
UNITCNT = [
    re.compile(r"\b(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?|pecas|peças|fl|folhas|sach[eê]s?)\b", re.I),
    re.compile(r"\bcom\s+(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?)?\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b))", re.I),
    re.compile(r"\b(?:kit|leve)\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g|ml|l\b))", re.I),
]


def _type_alt(types: Sequence[tuple[str, str]]) -> str:
    return "|".join(f"(?P<{n}>{p})" for n, p in types)


_TYPES_V3 = [
    ("sache", r"sach[eê]s?"), ("capsula", r"c[aá]psulas?|caps"), ("rolo", r"rolos?"),
    ("folha", r"folhas?|fl"), ("peca", r"pe[cç]as?|pcs?"), ("tablete", r"tabletes?|comprimidos?|tabs"),
    ("saco", r"sacos?"), ("un", r"un|und|unid|unidades?"),
]
# c2: "30CP" / "cps" / "comp" = comprimidos
_TYPES_C2 = [
    ("sache", r"sach[eê]s?"), ("capsula", r"c[aá]psulas?|caps"), ("rolo", r"rolos?"),
    ("folha", r"folhas?|fl"), ("peca", r"pe[cç]as?|pcs?"), ("tablete", r"tabletes?|comprimidos?|tabs|cps?|comp"),
    ("saco", r"sacos?"), ("un", r"un|und|unid|unidades?"),
]


def _count_t(types):
    alt = _type_alt(types)
    return [
        re.compile(r"(?<![\w,.])(\d{1,4})\s*(?:" + alt + r")\b", re.I),
        re.compile(r"\b(?:c\s*/\s*|com\s+|pacote\s+com\s+|pct\s+com\s+)(\d{1,4})\s*(?:" + alt
                   + r")?\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b|cm|mm|m\b))", re.I),
    ]


COUNT_T = _count_t(_TYPES_V3)
COUNT_T_C2 = _count_t(_TYPES_C2)
KIT_SUM_CP = re.compile(r"(?<![\w,.])(\d{1,4})\s*(?:cps?|c[aá]psulas?|caps|comprimidos?|comp)\s*\+\s*(\d{1,4})\s*(?:cps?|c[aá]psulas?|caps|comprimidos?|comp)\b", re.I)
DUZIA = re.compile(r"(?<![\w,.])(\d{1,3})\s*(d[uú]zias?|dz)\b", re.I)
DUZIA1 = re.compile(r"\bd[uú]zia\b", re.I)
PORTA_OVOS = re.compile(r"porta[\s\-]*ovos?", re.I)
DIM = [
    re.compile(r"(?<![\w,.])" + NUM + r"\s*(cm|mm)\b", re.I),
    re.compile(r"(?<![\w,.])" + NUM + r"\s*m\b(?!l)", re.I),
    re.compile(r"(?<![\w,.])(\d{2,4})\s*(v|volts?|w|watts?)\b", re.I),
    re.compile(r"\bbivolt\b", re.I),
    re.compile(r"\bn[º°o.]?\s*\.?\s*(\d{1,2})\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b))", re.I),
    re.compile(r"(?<![\w,.])(\d{2})\s*[/-]\s*(\d{2})\b", re.I),
    re.compile(r"\b(pp|xgg|xxg|xg|gg)\b", re.I),
    re.compile(r"\btam(?:anho)?\.?\s*(pp|p|m|g|gg|xg|\d{1,2})\b", re.I),
    re.compile(r"\b\d{3}/\d{2}\s*r\s*\d{2}\b", re.I),
    re.compile(r"\bref\.?\s*\d{2,6}\b", re.I),
    re.compile(r"(?<![\w,.])(\d{1,3})\s*x\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b))", re.I),
]
KG_IMPL = re.compile(r"(?<![\w])(kg|quilo|kilo|a\s+granel|granel|por\s+quilo)(?![\w])", re.I)
UN_IMPL = re.compile(r"(?<![\w,.\d])(?:1\s*)?(un|und|unid|unidade)(?![\w])", re.I)
UN_IMPL3 = re.compile(r"(?<![\w,.])(?<!\d\s)(?:1\s*)?(un|und|unid|unidade)(?![\w])", re.I)
KIT = re.compile(r"\bkit\b|\bcombo\b|\bpack\b.*\+|\+", re.I)
KIT_WORD = re.compile(r"\bkit\b|\bcombo\b", re.I)
_PKG_SRC = {
    "lata": r"\blata\b|\blt\b(?=.*\d+\s*ml)", "long neck": r"\blong\s*neck\b|\bln\b",
    "garrafa": r"\bgarrafa\b|\bgfa\b|\bgf\b", "pet": r"\bpet\b", "caixa": r"\bcaixa\b|\bcx\b",
    "pacote": r"\bpacote\b|\bpct\b|\bpc\b", "sache": r"\bsach[eê]\b|\bsc\b", "pote": r"\bpote\b",
    "frasco": r"\bfrasco\b|\bfr\b", "tubo": r"\btubo\b", "bandeja": r"\bbandeja\b|\bbdj\b",
    "saco": r"\bsaco\b", "vidro": r"\bvidro\b", "tetra": r"\btetra\s*pak\b|\bcaixinha\b",
    "balde": r"\bbalde\b", "refil": r"\brefil\b", "barra": r"\bbarra\b",
}
PKG = {k: re.compile(v, re.I) for k, v in _PKG_SRC.items()}
BEV_PKG = {"lata", "long neck", "garrafa", "pet"}
PROMO1 = re.compile(r"\+\s*" + NUM + r"\s*" + UNIT + r"\s*gr[aá]tis", re.I)
PROMO2 = re.compile(r"gr[aá]tis\s*(?:fps\s*\d+\s*)?" + NUM + r"\s*" + UNIT + r"\b", re.I)
PROMO1_C2 = re.compile(r"\+\s*" + NUM + r"\s*" + UNIT + r"\s*(?:gr[aá]tis|gts)\b", re.I)
PROMO2_C2 = re.compile(r"(?:gr[aá]tis|gts)\s*(?:fps\s*\d+\s*)?" + NUM + r"\s*" + UNIT + r"\b", re.I)
PROMO3 = re.compile(r"\d+\s*%\s*desc\w*", re.I)
DREN = re.compile(NUM + r"\s*" + UNIT + r"\s*dren\w*", re.I)
PROT_KW = re.compile(r"whey|prote|completo|fibra", re.I)
PROT_KW_C2 = re.compile(r"whey|prote|completo|fibra|yopro|\bpro\b", re.I)
RANGE_C2 = re.compile(r"(?<![\w,.])" + NUM + r"\s*" + UNIT + r"\s*[-–]\s*" + NUM + r"\s*" + UNIT + r"(?!\w)", re.I)


def to_base(val: str, unit: str) -> tuple[float | None, str | None]:
    u = fold(unit)
    v = float(val.replace(",", "."))
    if u.startswith(("kg", "quilo", "kilo")):
        return v * 1000, "g"
    if u in ("g", "gr", "grs", "grama", "gramas"):
        return v, "g"
    if u == "mg":
        return v / 1000, "g"
    if u.startswith(("l", "litro")) and u not in ("ml", "mls"):
        return v * 1000, "ml"
    if u in ("ml", "mls"):
        return v, "ml"
    if u == "cl":
        return v * 10, "ml"
    return None, None


def clean_title(name: str, dept: str, rules: frozenset[str]) -> str:
    if "q6" not in rules or "|" not in name:
        return name
    out = []
    for p in (x.strip() for x in name.split("|")):
        if re.fullmatch(r"\d{2,4}", p) and dept == "Bebidas":
            p = p + " ml"
        out.append(p)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


# --------------------------------------------------------------------------- title parser


@dataclass
class Parsed:
    size: str = ""  # "500ml", "1000g", "dim:15cm", "10un", "1un" ("" = none)
    size_src: str = ""  # title|mult|dimension|count|implicit_kg|implicit_un|""
    multi: bool = False
    conflict: bool = False
    pack_qty: int = 0
    unit_count: int = 0
    unit_type: str = ""
    pkg: str = ""


def parse_title(name: str, dept: str, rules: frozenset[str] = ALL_RULES) -> Parsed:
    R = rules
    n = name or ""
    o = Parsed()
    work = n
    if "q8" in R:
        p1, p2 = (PROMO1_C2, PROMO2_C2) if "c2" in R else (PROMO1, PROMO2)
        work = p1.sub(" ", work)
        work = p2.sub(lambda m: m.group(0) if re.search(r"%\s*$", work[: m.start()]) else " ", work)
        work = PROMO3.sub(" ", work)
        work = DREN.sub(" ", work)
    if "c2" in R:  # 350g-370g -> 350g
        work = RANGE_C2.sub(lambda m: m.group(0) if fold(m.group(2)) != fold(m.group(4)) else f"{m.group(1)}{m.group(2)}", work)
    if "r4" in R:
        m = (LEVE8 if "q8" in R else LEVE).search(work)
        if m:
            work = work[: m.start()] + " " + m.group(1) + " " + work[m.end():]
    sizes: list[tuple[float, str]] = []
    mult = None
    cada = (CADA8 if "q8" in R else CADA).search(work) if "r4" in R else None
    if cada:
        g2, g3 = (cada.group(2), cada.group(3)) if cada.group(2) else (cada.group(4), cada.group(5))
        q, u = to_base(g2, g3)
        if q:
            mult = (int(cada.group(1)), q, u)
    for m in MULT.finditer(work):
        q, u = to_base(m.group(2), m.group(3))
        if q:
            mult = (int(m.group(1)), q, u)
    rx = SIZE_V2 if "r4" in R else SIZE_V1
    for m in rx.finditer(work):
        if "r4" in R and NONSIZE_AFTER.match(work[m.end(): m.end() + 20]):
            continue
        q, u = to_base(m.group(1), m.group(2))
        if q and q > 0:
            sizes.append((q, u))
    if "q8" in R and len(sizes) > 1 and (PROT_KW_C2 if "c2" in R else PROT_KW).search(n):
        big = {u: max(q for q, uu in sizes if uu == u) for _, u in sizes}
        keep = []
        for q, u in sizes:
            small_g = u == "g" and q <= 40 and (any(uu == "ml" for _, uu in sizes) or big["g"] >= 5 * q)
            if not small_g:
                keep.append((q, u))
        sizes = keep or sizes
    distinct = {(round(s[0], 1), s[1]) for s in sizes}
    if mult:
        o.size = f"{mult[1]:g}{mult[2]}"
        o.size_src = "mult"
        o.pack_qty = mult[0]
        if cada:
            distinct = {d for d in distinct if not abs(d[0] - mult[0] * mult[1]) < 1}
        distinct = {d for d in distinct if d != (round(mult[0] * mult[1], 1), mult[2])}
        distinct.add((round(mult[1], 1), mult[2]))
    elif sizes:
        o.size = f"{round(sizes[0][0], 1):g}{sizes[0][1]}"
        o.size_src = "title"
    if len(distinct) > 1:
        if "r4" in R and KIT.search(n):
            o.multi = True
        else:
            o.conflict = True
    for k, r in PKG.items():
        if r.search(n):
            o.pkg = k
            break
    if not o.pack_qty:
        for p in PACK_STRICT:
            m = p.search(n)
            if m and 2 <= int(m.group(1)) <= 48:
                o.pack_qty = int(m.group(1))
                break
    m = CSLASH.search(n)
    cs = int(m.group(1)) if m and 2 <= int(m.group(1)) <= 48 else 0
    if cs:
        if "r4" in R and not (dept == "Bebidas" or o.pkg in BEV_PKG):
            o.unit_count = cs
            o.unit_type = "un"
        elif not o.pack_qty:
            o.pack_qty = cs
    if "q2" in R:
        porta = "c4" in R and PORTA_OVOS.search(n)
        md = None if porta else DUZIA.search(n)
        ksum = KIT_SUM_CP.search(n) if "c2" in R else None
        if porta:
            o.unit_count = 1
            o.unit_type = "un"
        elif md:
            o.unit_count = int(md.group(1))
            o.unit_type = "dz"
        elif DUZIA1.search(n):
            o.unit_count = 1
            o.unit_type = "dz"
        if not porta and ksum and (not o.unit_type or o.unit_type == "un"):
            o.unit_count = int(ksum.group(1)) + int(ksum.group(2))
            o.unit_type = "tablete"
        elif not porta and (not o.unit_type or o.unit_type == "un"):
            for rxx in COUNT_T_C2 if "c2" in R else COUNT_T:
                m = rxx.search(n)
                if m and 2 <= int(m.group(1)) <= 1000:
                    t = next((k for k, v in m.groupdict().items() if v), "un")
                    if o.unit_count and o.unit_type == "un" and t == "un":
                        break
                    o.unit_count = int(m.group(1))
                    o.unit_type = t
                    break
    elif not o.unit_count:
        for p in UNITCNT:
            m = p.search(n)
            if m and 2 <= int(m.group(1)) <= 1000:
                o.unit_count = int(m.group(1))
                o.unit_type = "un"
                break
    if not o.size and "q1" in R:
        labs = []
        for rxx in DIM:
            m = rxx.search(n)
            if m:
                labs.append(re.sub(r"\s+", "", m.group(0).lower()))
        if labs:
            o.size = "dim:" + "/".join(labs[:2])
            o.size_src = "dimension"
    if not o.size and "q2" in R and o.unit_count:
        o.size = f"{o.unit_count}{o.unit_type or 'un'}"
        o.size_src = "count"
    if not o.size and ({"r1", "r1k", "r1u"} & R):
        if KG_IMPL.search(n) and ({"r1", "r1k"} & R):
            o.size = "1000g"
            o.size_src = "implicit_kg"
        elif (UN_IMPL3 if "q2" in R else UN_IMPL).search(n) and ({"r1", "r1u"} & R):
            o.size = "1un"
            o.size_src = "implicit_un"
    return o


# --------------------------------------------------------------------------- brands

STOP = set(
    "de da do das dos com sem para por em e a o c un und unid unidade unidades pack kit cx caixa pct pacote lata garrafa pet long neck sache frasco pote saco vidro bandeja refil tubo leve preco quilo kg g ml l lt gr granel".split()
)
BRANDLESS_DEPTS = {"Hortifruti", "Açougue", "Peixaria", "Padaria", "Bazar e Utilidades"}
EGG = re.compile(r"\bovos?\b", re.I)
BRANDLESS_TITLE = re.compile(r"\bovos?\b|\bgranel\b", re.I)
EASTER = re.compile(
    r"p[aá]scoa|chocolate|kids|brinqued|surpresa|recheado|colher|arcor|nestl|lacta|garoto|ferrero|kinder|cacau|moana|expande|massinha|drag[aã]o|unic[oó]rnio|\bmini\b|bombom|brigadeiro|ninho|trento|hershey",
    re.I,
)
COMMON_WORDS = set(
    "sabor maria life cristal alecrim brasa natural premium tradicional original classico integral especial extra super mega max plus bom boa leve forte suave fino fina nobre real royal gold ouro prata azul verde vermelho branco preto rosa casa vida festa mix top light zero diet baby kids pro nova novo dia todo bem mais ideal sao santa".split()
)
GENERIC_OK = {"generico"}
_INVALID_BASE = ["Du para", "Pra Você", "Mais dog", "Generico", "Genérico", "Tradicional"]
_INVALID_PROTO_EXTRA = ["Original", "Flores e Vegetais", "Flores E Vegetais"]
INVALID_BRANDS = frozenset(alnum(x) for x in _INVALID_BASE)  # c1: Original/Flores e Vegetais are valid
INVALID_BRANDS_PROTO = frozenset(alnum(x) for x in _INVALID_BASE + _INVALID_PROTO_EXTRA)
SHORT_OK = {"lor", "nik", "ype", "tok", "bic", "omo", "lux", "vim", "ace"}
APPROVED_BRANDS = ["Dasabor", "Black Skull", "Gabriela Sabatini", "Fest Lar", "Tok", "Casamia", "Fortlar", "Peterlongo"]
BRAND_ALIASES = {"lo r": "lor"}  # c5: "Lo'r" -> L'Or
NO_BRAND_FIELD_RETAILERS = {"dalben", "davitta"}  # c7
MEAT = re.compile(
    r"lingui[cç]a|\bling\b|churrasc|costela|picanha|\bbife|\bcarne\b|\bcoxa|sobrecoxa|\bpeito\b|toscana|alcatra|fraldinha|maminha|cupim|contra\s*fil[eé]|fil[eé] mignon|paleta|pernil|bisteca|lombo|acem|ac[eé]m|patinho|ac[eé]m|coxao|cox[aã]o|bacon|salsicha|hamburg|frango|su[ií]na|bovin",
    re.I,
)
EGG_DEPTS = ("Hortifruti", "Frios e Laticínios", "Mercearia", "Padaria", "Outros", "Bazar e Utilidades")


@dataclass
class BrandDictionary:
    display: dict[str, str]  # brand key -> display name
    surface: dict[str, str]  # token string -> brand key
    ambiguous: set[str]
    protected: set[str]
    short_ok: set[str] = field(default_factory=lambda: set(SHORT_OK))
    rules: frozenset[str] = ALL_RULES
    _maxn: int = 1

    def __post_init__(self) -> None:
        self._maxn = max((len(s.split()) for s in self.surface), default=1)

    def _guard(self, s: str, n: int) -> bool:
        if n == 1 and s not in self.protected:
            if s in self.ambiguous:
                return False
            if len(s) < 4 and not ("q5" in self.rules and s in self.short_ok):
                return False
        return True

    def find(self, name: str) -> str | None:
        t = toks(name)
        for n in range(min(self._maxn, 4), 0, -1):
            for i in range(len(t) - n + 1):
                s = " ".join(t[i: i + n])
                k = self.surface.get(s)
                if k is None or not self._guard(s, n):
                    continue
                return k
        return None

    def find_all(self, name: str) -> list[str]:
        t = toks(name)
        used: set[int] = set()
        found: list[str] = []
        for n in range(min(self._maxn, 4), 0, -1):
            for i in range(len(t) - n + 1):
                if used & set(range(i, i + n)):
                    continue
                s = " ".join(t[i: i + n])
                k = self.surface.get(s)
                if k is None or not self._guard(s, n):
                    continue
                used |= set(range(i, i + n))
                if k not in found:
                    found.append(k)
        return found


@dataclass(frozen=True)
class SourceRow:
    id: int
    retailer: str
    name: str
    brand: str = ""
    gtin: str = ""
    categories: tuple[str, ...] = ()


def build_dictionary(
    rows: Iterable[tuple[str, str]], rules: frozenset[str] = ALL_RULES
) -> BrandDictionary:
    """``rows`` = (title, source_brand) pairs (cleaned titles, invalid brands already blanked)."""
    R = rules
    invalid = INVALID_BRANDS if "c1" in R else INVALID_BRANDS_PROTO
    data = [(n, b, alnum(b)) for n, b in rows if b != ""]
    if "q9" in R:
        data = [x for x in data if x[2] not in invalid]
    minn = 3 if "r3" in R else 5
    cnt: collections.Counter = collections.Counter(bk for _, _, bk in data)
    spell: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for _, b, bk in data:
        spell[bk][b] += 1
    keep = [k for k in cnt if cnt[k] >= minn and len(k) >= 3]
    disp: dict[str, str] = {}
    surface: dict[str, str] = {}
    protected: set[str] = set()
    for k in keep:
        d = spell[k].most_common(1)[0][0]
        disp[k] = d
        forms = ({d} | set(spell[k])) if "r3" in R else {d}
        for f in forms:
            t = " ".join(toks(f))
            if t:
                surface[t] = k
            if "r3" in R and t:
                surface.setdefault(t.replace(" ", ""), k)
    if "q3" in R:
        for a in APPROVED_BRANDS:
            k = alnum(a)
            disp[k] = a
            surface[" ".join(toks(a))] = k
            protected.add(" ".join(toks(a)))
            surface.setdefault(k, k)
            if " " not in " ".join(toks(a)):
                protected.add(k)
    if "c5" in R:
        for alias, k in BRAND_ALIASES.items():
            if k in disp:
                surface[alias] = k
    ambiguous: set[str] = set()
    if "r3" in R:
        single = {t for t in surface if " " not in t}
        occ: collections.Counter = collections.Counter()
        other: collections.Counter = collections.Counter()
        for name, _, bk in data:
            for t in set(toks(name)):
                if t in single:
                    occ[t] += 1
                    if surface[t] != bk:
                        other[t] += 1
        for t in single:
            if "q3" in R and t in protected:
                continue
            if "q5" in R and t in SHORT_OK:
                continue
            if t in COMMON_WORDS or (occ[t] >= 5 and other[t] / occ[t] >= 0.3) or len(t) < 4:
                ambiguous.add(t)
    return BrandDictionary(disp, surface, ambiguous, protected, set(SHORT_OK), R)


# --------------------------------------------------------------------------- row-level result


@dataclass
class Normalized:
    id: int
    retailer: str
    source_name: str
    title: str
    department: str
    gtin: str
    source_brand: str
    brand_key: str
    brand_name: str
    brand_origin: str  # source|inferred|no_brand_ok|none|multi_brand
    parsed: Parsed
    core: str
    qty: int
    key: str
    flags: list[str] = field(default_factory=list)
    group: str = ""
    gtin_match: bool = False
    key_match: bool = False
    canonical_name: str = ""
    canonical_name_no_brand: str = ""

    @property
    def size(self) -> str:
        return self.parsed.size


def _is_egg(n: str, d: str, R: frozenset[str]) -> bool:
    if "q7" in R:
        egg = bool(EGG.search(n) and not EASTER.search(n) and d in EGG_DEPTS)
        if "c4" in R and PORTA_OVOS.search(n):
            egg = False
        return egg or bool(re.search(r"\bgranel\b", n, re.I))
    return bool(BRANDLESS_TITLE.search(n))


def _core(n: str, b: str, bk: str, R: frozenset[str]) -> str:
    bt = set(toks(b))
    t = [x for x in toks(n) if x not in bt and x not in STOP and not re.fullmatch(r"\d+(ml|l|g|kg|gr|lt)?", x) and len(x) > 1]
    c = " ".join(sorted(set(t)))
    if not c and "r5" in R and bk:
        c = "_" + bk
    return c


def prepare(row: SourceRow, rules: frozenset[str] = ALL_RULES) -> tuple[str, str, str, Parsed]:
    """Row-only part: (department, cleaned title, cleaned source brand, parsed title)."""
    dept0 = canonical_department(list(row.categories), row.name)
    title = clean_title(row.name, dept0, rules)
    dept = "Açougue" if ("q4" in rules and dept0 == "Outros" and MEAT.search(title)) else dept0
    invalid = INVALID_BRANDS if "c1" in rules else INVALID_BRANDS_PROTO
    brand = row.brand
    if "q9" in rules and alnum(brand) in invalid:
        brand = ""
    return dept, title, brand, parse_title(title, dept, rules)


def normalize_row(
    row: SourceRow,
    dictionary: BrandDictionary,
    rules: frozenset[str] = ALL_RULES,
    prepared: tuple[str, str, str, Parsed] | None = None,
) -> Normalized:
    R = rules
    dept, title, brand, p = prepared or prepare(row, R)
    generic = "q9" in R and alnum(row.brand) in GENERIC_OK
    flags: list[str] = []
    origin, bk, bn = "none", "", ""
    inferred_all: list[str] = []
    if brand:
        origin, bk, bn = "source", alnum(brand), brand
        if "c5" in R and bk in BRAND_ALIASES.values() and bk in dictionary.display:
            bn = dictionary.display[bk]  # "Lo'r" -> "L'Or"
    else:
        inferred_all = dictionary.find_all(title)
        inf = dictionary.find(title)
        if "c3" in R and KIT_WORD.search(title) and len(inferred_all) >= 2:
            origin, bk, bn = "multi_brand", "", ""
            p.multi = True
            flags.append("kit_multi_brand")
        elif inf:
            origin, bk, bn = "inferred", inf, dictionary.display[inf]
        elif "r2" in R and (dept in BRANDLESS_DEPTS or _is_egg(title, dept, R) or generic):
            origin, bk, bn = "no_brand_ok", "semmarca", "sem marca (não importa)"
    if "c7" in R and row.retailer in NO_BRAND_FIELD_RETAILERS and not row.brand:
        flags.append("retailer_no_brand_field")
    core = _core(title, bn if origin != "no_brand_ok" else "", bk, R)
    qty = p.pack_qty if p.pack_qty > 0 else p.unit_count
    key = f"{bk}|{core}|{p.size}|{qty}"
    gtin = row.gtin if re.fullmatch(r"\d{8,14}", row.gtin or "") else ""
    n = Normalized(row.id, row.retailer, row.name, title, dept, gtin, row.brand, bk, bn, origin, p, core, qty, key, flags)
    if gtin and not gtin_checksum_ok(gtin):
        n.flags.append("gtin_bad_checksum")
    return n


def gtin_checksum_ok(g: str) -> bool:
    if not re.fullmatch(r"\d{8}|\d{12,14}", g or ""):
        return False
    digits = [int(c) for c in g]
    body, check = digits[:-1], digits[-1]
    s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - s % 10) % 10 == check


# --------------------------------------------------------------------------- corpus level


def assign_groups(items: Sequence[Normalized], rules: frozenset[str] = ALL_RULES) -> None:
    """Sets ``group``/``gtin_match``/``key_match`` in place (A1 needs >=2 retailers on the same key/GTIN)."""
    kr: dict[str, set[str]] = collections.defaultdict(set)
    gr: dict[str, set[str]] = collections.defaultdict(set)
    for x in items:
        if x.brand_key and x.parsed.size and x.core:
            kr[x.key].add(x.retailer)
        if x.gtin:
            gr[x.gtin].add(x.retailer)
    q10 = "q10" in rules
    for x in items:
        x.key_match = bool(x.brand_key and x.parsed.size and x.core and len(kr[x.key]) >= 2)
        x.gtin_match = bool(x.gtin and len(gr[x.gtin]) >= 2)
        p = x.parsed
        if q10 and x.gtin_match and not x.key_match and p.size_src == "implicit_un":
            x.group = "R"
        elif x.gtin_match or x.key_match:
            x.group = "A1"
        else:
            okk = bool(x.brand_key and p.size and x.core)
            if okk and not p.conflict and not p.multi and x.brand_origin in ("source", "no_brand_ok"):
                x.group = "A2"
            elif okk and not p.conflict and not p.multi and x.brand_origin == "inferred":
                x.group = "B1"
            elif p.conflict or p.multi:
                x.group = "B2"
            elif x.brand_key and not p.size:
                x.group = "B3"
            elif p.size and not x.brand_key:
                x.group = "B4"
            elif x.brand_key and p.size:
                x.group = "B3"
            else:
                x.group = "C"


def _flag_dept_noise(items: Sequence[Normalized]) -> None:
    """c6: brand sold mostly in one department but appearing in another one."""
    by: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for x in items:
        if x.brand_origin == "source" and x.brand_key:
            by[x.brand_key][x.department] += 1
    dom = {}
    for k, c in by.items():
        total = sum(c.values())
        d, n = c.most_common(1)[0]
        if total >= 20 and n / total >= 0.6:
            dom[k] = d
    for x in items:
        d = dom.get(x.brand_key)
        if d and x.department != d and x.brand_origin == "source" and by[x.brand_key][x.department] / sum(by[x.brand_key].values()) < 0.05:
            x.flags.append("dept_noise")


def normalize_corpus(rows: Sequence[SourceRow], rules: frozenset[str] = ALL_RULES) -> list[Normalized]:
    prepared = [prepare(r, rules) for r in rows]
    dictionary = build_dictionary(((t, b) for _, t, b, _ in prepared), rules)
    items = [normalize_row(r, dictionary, rules, prep) for r, prep in zip(rows, prepared, strict=True)]
    assign_groups(items, rules)
    for x in items:
        build_canonical_names(x)
    if "c6" in rules:
        _flag_dept_noise(items)
    return items


# --------------------------------------------------------------------------- names


def _fmt_size(size: str) -> str:
    if not size or size.startswith("dim:"):
        return size[4:].replace("/", " ") if size else ""
    m = re.fullmatch(r"([\d.]+)(g|ml|un|dz|[a-z]+)", size)
    if not m:
        return size
    v, u = float(m.group(1)), m.group(2)
    if u == "g" and v >= 1000:
        return f"{v / 1000:g} kg"
    if u == "ml" and v >= 1000:
        return f"{v / 1000:g} L"
    return f"{v:g} {u}"


_STRIP = [SIZE_V2, MULT, CADA8, LEVE8, PROMO3]


def _product_phrase(title: str, brand: str, p: Parsed) -> str:
    t = title
    for rx in _STRIP:
        t = rx.sub(" ", t)
    for rx in PACK_STRICT + [CSLASH, DUZIA, KIT_SUM_CP] + COUNT_T_C2:
        t = rx.sub(" ", t)
    for rx in PKG.values():
        t = rx.sub(" ", t)
    if brand:
        for tk in sorted(toks(brand), key=len, reverse=True):
            t = re.sub(r"(?<![A-Za-z0-9])" + re.escape(tk) + r"(?![A-Za-z0-9])", " ", t, flags=re.I)
    t = re.sub(r"[()\[\]|+,;/]", " ", t)
    words = [w for w in t.split() if fold(w).strip(".'-") not in STOP and not re.fullmatch(r"[\d.,]+", w)]
    return " ".join(words).strip()


def build_canonical_names(x: Normalized) -> None:
    """'Produto + Marca + Embalagem + Tamanho + Pack N' and the variant without brand."""
    p = x.parsed
    brand = x.brand_name if x.brand_origin in ("source", "inferred") else ""
    phrase = _product_phrase(x.title, brand, p) or x.title
    if brand.isupper():
        brand = brand.title()
    pack = f"Pack {x.qty}" if x.qty and x.qty > 1 else ""
    tail = [p.pkg.title() if p.pkg else "", _fmt_size(p.size) if p.size_src != "implicit_un" else "", pack]
    x.canonical_name = re.sub(r"\s+", " ", " ".join([phrase, brand, *tail])).strip()
    x.canonical_name_no_brand = re.sub(r"\s+", " ", " ".join([phrase, *tail])).strip()


def size_columns(p: Parsed) -> tuple[float | None, str | None, str | None]:
    """(size_value, size_unit, size_label) for DB columns."""
    if not p.size:
        return None, None, None
    if p.size.startswith("dim:"):
        return None, "dim", p.size[4:]
    m = re.fullmatch(r"([\d.]+)([a-z]+)", p.size)
    if not m:
        return None, None, p.size
    return float(m.group(1)), m.group(2), p.size


def identity_fingerprint(x: Normalized) -> bytes:
    base = f"gtin:{x.gtin}" if x.gtin else f"key:{x.key}"
    return hashlib.sha256(base.encode()).digest()
