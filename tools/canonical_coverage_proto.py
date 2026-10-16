#!/usr/bin/env python3
"""Prototype v3 (NOT wired into the app): canonical coverage.

Read-only: reads backups/analysis/products.csv (export of active store products),
recomputes groups A1/A2/B1-B4/C (+R = review sample) with rule toggles and prints
v1 -> v2 -> v3.  v2 rules: r1..r5.  v3 rules: q1..q10 (see RULES_V3).
Usage: python tools/canonical_coverage_proto.py CSV OUTDIR
"""
import sys, re, json, collections, unicodedata
import pandas as pd

CSV = sys.argv[1] if len(sys.argv) > 1 else "backups/analysis/products.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "docs/canonical"
try:
    from app.catalog.taxonomy import canonical_department
except Exception:
    sys.path.insert(0, ".")
    from taxonomy import canonical_department

V2 = {"r1", "r2", "r3", "r4", "r5"}
RULES_V3 = {
    "q1": "dimensão/numeração = atributo válido (32,5cm, N.6, V, nº sapato)",
    "q2": "contagens = quantidade com unidade (dúzia, un, cápsula, sachê, rolo, peça)",
    "q3": "marcas aprovadas (Dasabor, Black Skull, Gabriela Sabatini, Fest Lar, Tok, Casamia, Fortlar, Peterlongo)",
    "q4": "departamento Açougue para palavras de carne em 'Outros'",
    "q5": "whitelist de marcas curtas (L'Or, Nik, Ypê, Tok…) na guarda len<4",
    "q6": "limpeza de título ('|' → espaço, número solto = ml em bebida)",
    "q7": "regra de ovo restrita a ovos (sem Páscoa/brinquedo)",
    "q8": "parser: whey/proteína, dren/liq, Grátis/% Desconto",
    "q9": "lista de marcas de origem inválidas",
    "q10": "GTIN + 1 un implícita vai para amostra de revisão (R)",
}
V3 = V2 | set(RULES_V3)

def fold(s):
    s = unicodedata.normalize("NFKD", s if isinstance(s, str) else "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()
def alnum(s): return re.sub(r"[^a-z0-9]", "", fold(s))
def toks(s): return re.findall(r"[a-z0-9]+", fold(s))

NUM = r"(\d+(?:[.,]\d+)?)"
UNIT = r"(kgs?|quilos?|kilos?|gramas?|grs?|g|mg|litros?|lts?|lt|l|ml|cl|mls)"
SIZE_V1 = re.compile(r"(?<![\w,.])" + NUM + r"\s*" + UNIT + r"(?![a-z0-9])", re.I)
SIZE_V2 = re.compile(r"(?<![\w,.%])" + NUM + r"\s*" + UNIT + r"(?!\w)", re.I)
MULT = re.compile(r"(?<![\w,.])(\d{1,3})\s*[x×]\s*" + NUM + r"\s*" + UNIT + r"(?![a-z0-9])", re.I)
CADA = re.compile(r"(?<![\w,.])(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?|pe[cç]as?|sach[eê]s?|tabletes?|barras?)\s*(?:de|x)\s*" + NUM + r"\s*" + UNIT + r"\b(?:\s*cada)?", re.I)
CADA8 = re.compile(r"(?<![\w,.])(?:c\s*/\s*|com\s+)?(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?|pe[cç]as?|sach[eê]s?|tabletes?|barras?)\.?\s*(?:(?:de|x)\s*" + NUM + r"\s*" + UNIT + r"\b|" + NUM + r"\s*" + UNIT + r"\s*cada\b)", re.I)
LEVE8 = re.compile(r"(?:leve|lv)\s*(" + NUM + r"\s*" + UNIT + r"?)\s*(?:pague|pg)\s*" + NUM + r"\s*" + UNIT + r"?", re.I)
LEVE = re.compile(r"leve\s*(" + NUM + r"\s*" + UNIT + r"?)\s*pague\s*" + NUM + r"\s*" + UNIT + r"?", re.I)
NONSIZE_AFTER = re.compile(r"^\s*(?:de\s+)?(?:prote|fibra|vitamin|c[aá]lcio|colag|a[cç][uú]car|s[oó]dio|gordura|carbo)", re.I)
PACK_STRICT = [re.compile(r"\bpack\s*(?:c/|com)?\s*(\d{1,3})\b", re.I),
               re.compile(r"\b(?:cx|caixa|fardo)\s*(?:c/|com|de|:)?\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g|ml|l\b))", re.I)]
CSLASH = re.compile(r"\bc\s*/\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g|ml|l\b))", re.I)
UNITCNT = [re.compile(r"\b(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?|pecas|peças|fl|folhas|sach[eê]s?)\b", re.I),
           re.compile(r"\bcom\s+(\d{1,3})\s*(?:un|und|unid|unidades?|pcs?)?\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b))", re.I),
           re.compile(r"\b(?:kit|leve)\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g|ml|l\b))", re.I)]
# v3: counts with unit type
TYPES = [("sache", r"sach[eê]s?"), ("capsula", r"c[aá]psulas?|caps"), ("rolo", r"rolos?"), ("folha", r"folhas?|fl"),
         ("peca", r"pe[cç]as?|pcs?"), ("tablete", r"tabletes?|comprimidos?|tabs"), ("saco", r"sacos?"), ("un", r"un|und|unid|unidades?")]
TYPE_ALT = "|".join(f"(?P<{n}>{p})" for n, p in TYPES)
COUNT_T = [re.compile(r"(?<![\w,.])(\d{1,4})\s*(?:" + TYPE_ALT + r")\b", re.I),
           re.compile(r"\b(?:c\s*/\s*|com\s+|pacote\s+com\s+|pct\s+com\s+)(\d{1,4})\s*(?:" + TYPE_ALT + r")?\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b|cm|mm|m\b))", re.I)]
DUZIA = re.compile(r"(?<![\w,.])(\d{1,3})\s*(d[uú]zias?|dz)\b", re.I)
DUZIA1 = re.compile(r"\bd[uú]zia\b", re.I)
DIM = [re.compile(r"(?<![\w,.])" + NUM + r"\s*(cm|mm)\b", re.I),
       re.compile(r"(?<![\w,.])" + NUM + r"\s*m\b(?!l)", re.I),
       re.compile(r"(?<![\w,.])(\d{2,4})\s*(v|volts?|w|watts?)\b", re.I),
       re.compile(r"\bbivolt\b", re.I),
       re.compile(r"\bn[º°o.]?\s*\.?\s*(\d{1,2})\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b))", re.I),
       re.compile(r"(?<![\w,.])(\d{2})\s*[/-]\s*(\d{2})\b", re.I),
       re.compile(r"\b(pp|xgg|xxg|xg|gg)\b", re.I),
       re.compile(r"\btam(?:anho)?\.?\s*(pp|p|m|g|gg|xg|\d{1,2})\b", re.I),
       re.compile(r"\b\d{3}/\d{2}\s*r\s*\d{2}\b", re.I),
       re.compile(r"\bref\.?\s*\d{2,6}\b", re.I),
       re.compile(r"(?<![\w,.])(\d{1,3})\s*x\s*(\d{1,3})\b(?!\s*[,.]?\d*\s*(?:kg|g\b|ml|l\b))", re.I)]
KG_IMPL = re.compile(r"(?<![\w])(kg|quilo|kilo|a\s+granel|granel|por\s+quilo)(?![\w])", re.I)
UN_IMPL = re.compile(r"(?<![\w,.\d])(?:1\s*)?(un|und|unid|unidade)(?![\w])", re.I)
UN_IMPL3 = re.compile(r"(?<![\w,.])(?<!\d\s)(?:1\s*)?(un|und|unid|unidade)(?![\w])", re.I)
KIT = re.compile(r"\bkit\b|\bcombo\b|\bpack\b.*\+|\+", re.I)
PKG = {"lata": r"\blata\b|\blt\b(?=.*\d+\s*ml)", "long neck": r"\blong\s*neck\b|\bln\b", "garrafa": r"\bgarrafa\b|\bgfa\b|\bgf\b",
       "pet": r"\bpet\b", "caixa": r"\bcaixa\b|\bcx\b", "pacote": r"\bpacote\b|\bpct\b|\bpc\b", "sache": r"\bsach[eê]\b|\bsc\b",
       "pote": r"\bpote\b", "frasco": r"\bfrasco\b|\bfr\b", "tubo": r"\btubo\b", "bandeja": r"\bbandeja\b|\bbdj\b", "saco": r"\bsaco\b",
       "vidro": r"\bvidro\b", "tetra": r"\btetra\s*pak\b|\bcaixinha\b", "balde": r"\bbalde\b", "refil": r"\brefil\b", "barra": r"\bbarra\b"}
PKG = {k: re.compile(v, re.I) for k, v in PKG.items()}
BEV_PKG = {"lata", "long neck", "garrafa", "pet"}
PROMO1 = re.compile(r"\+\s*" + NUM + r"\s*" + UNIT + r"\s*gr[aá]tis", re.I)
PROMO2 = re.compile(r"gr[aá]tis\s*(?:fps\s*\d+\s*)?" + NUM + r"\s*" + UNIT + r"\b", re.I)
PROMO3 = re.compile(r"\d+\s*%\s*desc\w*", re.I)
DREN = re.compile(NUM + r"\s*" + UNIT + r"\s*dren\w*", re.I)
PROT_KW = re.compile(r"whey|prote|completo|fibra", re.I)

def to_base(val, unit):
    u = fold(unit); v = float(val.replace(",", "."))
    if u.startswith(("kg", "quilo", "kilo")): return v * 1000, "g"
    if u in ("g", "gr", "grs", "grama", "gramas"): return v, "g"
    if u == "mg": return v / 1000, "g"
    if u.startswith(("l", "litro")) and u not in ("ml", "mls"): return v * 1000, "ml"
    if u in ("ml", "mls"): return v, "ml"
    if u == "cl": return v * 10, "ml"
    return None, None

def clean_title(n, dept, R):
    if "q6" not in R or "|" not in n: return n
    parts = [p.strip() for p in n.split("|")]
    out = []
    for p in parts:
        if re.fullmatch(r"\d{2,4}", p) and dept == "Bebidas": p = p + " ml"
        out.append(p)
    return re.sub(r"\s+", " ", " ".join(out)).strip()

def parse(name, dept, R):
    n = name or ""
    o = dict(size="", size_src="", multi=False, conflict=False, pack_qty=0, unit_count=0, unit_type="", pkg="", sw=False)
    work = n
    if "q8" in R:
        work = PROMO1.sub(" ", work)
        work = PROMO2.sub(lambda m: m.group(0) if re.search(r"%\s*$", work[:m.start()]) else " ", work); work = PROMO3.sub(" ", work); work = DREN.sub(" ", work)
    if "r4" in R:
        m = (LEVE8 if "q8" in R else LEVE).search(work)
        if m: work = work[:m.start()] + " " + m.group(1) + " " + work[m.end():]
    sizes = []; mult = None
    cada = (CADA8 if "q8" in R else CADA).search(work) if "r4" in R else None
    if cada:
        g2, g3 = (cada.group(2), cada.group(3)) if cada.group(2) else (cada.group(4), cada.group(5))
        q, u = to_base(g2, g3)
        if q: mult = (int(cada.group(1)), q, u)
    for m in MULT.finditer(work):
        q, u = to_base(m.group(2), m.group(3))
        if q: mult = (int(m.group(1)), q, u)
    rx = SIZE_V2 if "r4" in R else SIZE_V1
    for m in rx.finditer(work):
        if "r4" in R and NONSIZE_AFTER.match(work[m.end():m.end() + 20]): continue
        q, u = to_base(m.group(1), m.group(2))
        if q and q > 0: sizes.append((q, u))
    if "q8" in R and len(sizes) > 1 and PROT_KW.search(n):
        big = {u: max(q for q, uu in sizes if uu == u) for _, u in sizes}
        keep = []
        for q, u in sizes:
            small_g = u == "g" and q <= 40 and (any(uu == "ml" for _, uu in sizes) or big["g"] >= 5 * q)
            if not small_g: keep.append((q, u))
        sizes = keep or sizes
    distinct = set((round(s[0], 1), s[1]) for s in sizes)
    if mult:
        o["size"] = f"{mult[1]:g}{mult[2]}"; o["size_src"] = "mult"; o["pack_qty"] = mult[0]
        distinct = {d for d in distinct if not (cada and abs(d[0] - mult[0] * mult[1]) < 1)} if cada else distinct
        distinct = {d for d in distinct if d != (round(mult[0] * mult[1], 1), mult[2])}
        distinct.add((round(mult[1], 1), mult[2]))
    elif sizes:
        o["size"] = f"{round(sizes[0][0], 1):g}{sizes[0][1]}"; o["size_src"] = "title"
    if len(distinct) > 1:
        if "r4" in R and KIT.search(n): o["multi"] = True
        else: o["conflict"] = True
    for k, r in PKG.items():
        if r.search(n): o["pkg"] = k; break
    # pack / unit count
    if not o["pack_qty"]:
        for p in PACK_STRICT:
            m = p.search(n)
            if m and 2 <= int(m.group(1)) <= 48: o["pack_qty"] = int(m.group(1)); break
    m = CSLASH.search(n)
    cs = int(m.group(1)) if m and 2 <= int(m.group(1)) <= 48 else 0
    if cs:
        if "r4" in R and not (dept == "Bebidas" or o["pkg"] in BEV_PKG): o["unit_count"] = cs; o["unit_type"] = "un"
        elif not o["pack_qty"]: o["pack_qty"] = cs
    cnt_src = ""
    if "q2" in R:
        md = DUZIA.search(n)
        if md:
            o["unit_count"] = int(md.group(1)); o["unit_type"] = "dz"
        elif DUZIA1.search(n):
            o["unit_count"] = 1; o["unit_type"] = "dz"
        if not o["unit_type"] or o["unit_type"] == "un":
            for rxx in COUNT_T:
                m = rxx.search(n)
                if m and 2 <= int(m.group(1)) <= 1000:
                    t = next((k for k, v in m.groupdict().items() if v), "un")
                    if o["unit_count"] and o["unit_type"] == "un" and t == "un": break
                    o["unit_count"] = int(m.group(1)); o["unit_type"] = t; break
    elif not o["unit_count"]:
        for p in UNITCNT:
            m = p.search(n)
            if m and 2 <= int(m.group(1)) <= 1000: o["unit_count"] = int(m.group(1)); o["unit_type"] = "un"; break
    # dimension attribute
    if not o["size"] and "q1" in R:
        labs = []
        for rxx in DIM:
            m = rxx.search(n)
            if m: labs.append(re.sub(r"\s+", "", m.group(0).lower()))
        if labs:
            o["size"] = "dim:" + "/".join(labs[:2]); o["size_src"] = "dimension"
    # count as quantity
    if not o["size"] and "q2" in R and o["unit_count"]:
        o["size"] = f"{o['unit_count']}{o['unit_type'] or 'un'}"; o["size_src"] = "count"
    # implicit quantities (r1)
    if not o["size"] and ({"r1", "r1k", "r1u"} & R):
        if KG_IMPL.search(n) and ({"r1", "r1k"} & R): o["size"] = "1000g"; o["size_src"] = "implicit_kg"
        elif (UN_IMPL3 if "q2" in R else UN_IMPL).search(n) and ({"r1", "r1u"} & R): o["size"] = "1un"; o["size_src"] = "implicit_un"
    return o

STOP = set("de da do das dos com sem para por em e a o c un und unid unidade unidades pack kit cx caixa pct pacote lata garrafa pet long neck sache frasco pote saco vidro bandeja refil tubo leve preco quilo kg g ml l lt gr granel".split())
BRANDLESS_DEPTS = {"Hortifruti", "Açougue", "Peixaria", "Padaria", "Bazar e Utilidades"}
BRANDLESS_TITLE = re.compile(r"\bovos?\b|\bgranel\b", re.I)
EGG = re.compile(r"\bovos?\b", re.I)
EASTER = re.compile(r"p[aá]scoa|chocolate|kids|brinqued|surpresa|recheado|colher|arcor|nestl|lacta|garoto|ferrero|kinder|cacau|moana|expande|massinha|drag[aã]o|unic[oó]rnio|\bmini\b|bombom|brigadeiro|ninho|trento|hershey", re.I)
COMMON_WORDS = set("sabor maria life cristal alecrim brasa natural premium tradicional original classico integral especial extra super mega max plus bom boa leve forte suave fino fina nobre real royal gold ouro prata azul verde vermelho branco preto rosa casa vida festa mix top light zero diet baby kids pro nova novo dia todo bem mais ideal sao santa".split())
GENERIC_OK = {"generico"}
INVALID_BRANDS = {alnum(x) for x in ["Du para", "Pra Você", "Original", "Mais dog", "Generico", "Genérico", "Tradicional", "Flores e Vegetais", "Flores E Vegetais"]}
SHORT_OK = {"lor", "nik", "ype", "tok", "bic", "omo", "lux", "vim", "ace"}
APPROVED = ["Dasabor", "Black Skull", "Gabriela Sabatini", "Fest Lar", "Tok", "Casamia", "Fortlar", "Peterlongo"]
MEAT = re.compile(r"lingui[cç]a|\bling\b|churrasc|costela|picanha|\bbife|\bcarne\b|\bcoxa|sobrecoxa|\bpeito\b|toscana|alcatra|fraldinha|maminha|cupim|contra\s*fil[eé]|fil[eé] mignon|paleta|pernil|bisteca|lombo|acem|ac[eé]m|patinho|ac[eé]m|coxao|cox[aã]o|bacon|salsicha|hamburg|frango|su[ií]na|bovin", re.I)

def build_dictionary(df, R):
    b = df[df.brand != ""].copy(); b["bk"] = b.brand.map(alnum)
    if "q9" in R: b = b[~b.bk.isin(INVALID_BRANDS)]
    minn = 3 if "r3" in R else 5
    cnt = b.groupby("bk").size()
    spell = {k: collections.Counter(v) for k, v in b.groupby("bk").brand}
    keep = [k for k in cnt.index if cnt[k] >= minn and len(k) >= 3]
    disp, surface, protected = {}, {}, set()
    for k in keep:
        d = spell[k].most_common(1)[0][0]; disp[k] = d
        forms = {d} | set(spell[k]) if "r3" in R else {d}
        for f in forms:
            t = " ".join(toks(f))
            if t: surface[t] = k
            if "r3" in R and t: surface.setdefault(t.replace(" ", ""), k)
    if "q3" in R:
        for a in APPROVED:
            k = alnum(a); disp[k] = a; surface[" ".join(toks(a))] = k; protected.add(" ".join(toks(a)))
            surface.setdefault(k, k)
            if " " not in " ".join(toks(a)): protected.add(k)
    ambiguous = set()
    if "r3" in R:
        single = {t for t in surface if " " not in t}
        occ = collections.Counter(); other = collections.Counter()
        for name, bk in zip(b.name, b.bk):
            for t in set(toks(name)):
                if t in single:
                    occ[t] += 1
                    if surface[t] != bk: other[t] += 1
        for t in single:
            if "q3" in R and t in protected: continue
            if "q5" in R and t in SHORT_OK: continue
            if t in COMMON_WORDS or (occ[t] >= 5 and other[t] / occ[t] >= 0.3) or len(t) < 4:
                ambiguous.add(t)
    return disp, surface, ambiguous, protected

def make_finder(surface, ambiguous, protected, R):
    maxn = max(len(s.split()) for s in surface) if surface else 1
    def find(name):
        t = toks(name)
        for n in range(min(maxn, 4), 0, -1):
            for i in range(len(t) - n + 1):
                s = " ".join(t[i:i + n]); k = surface.get(s)
                if k is None: continue
                if n == 1 and s not in protected:
                    if s in ambiguous: continue
                    if len(s) < 4 and not ("q5" in R and s in SHORT_OK): continue
                return k
        return None
    return find

def run(df, R, dept0):
    R = set(R)
    # title cleaning + department
    names = [clean_title(n, d, R) for n, d in zip(df.name, dept0)]
    dept = list(dept0)
    if "q4" in R:
        dept = ["Açougue" if (d == "Outros" and MEAT.search(n)) else d for d, n in zip(dept, names)]
    P = [parse(n, d, R) for n, d in zip(names, dept)]
    brand = df.brand.values.copy()
    if "q9" in R: brand = [("" if alnum(b) in INVALID_BRANDS else b) for b in brand]
    generic_src = [alnum(b) in GENERIC_OK for b in df.brand.values] if "q9" in R else [False] * len(df)
    sub = df.assign(brand=brand, name=names)
    disp, surface, amb, prot = build_dictionary(sub, R)
    find = make_finder(surface, amb, prot, R)
    inferred = [None] * len(df)
    for i, (b, n) in enumerate(zip(brand, names)):
        if b == "":
            k = find(n)
            if k: inferred[i] = k
    out = pd.DataFrame({"id": df.id.values, "slug": df.slug.values, "name": df.name.values, "title": names, "dept": dept, "gtin": df.gtin.values, "src_brand": df.brand.values})
    bs, bk, bn = [], [], []
    for i, (b, inf, d, n) in enumerate(zip(brand, inferred, dept, names)):
        gen = generic_src[i]
        egg = (EGG.search(n) and not EASTER.search(n) and d in ("Hortifruti", "Frios e Laticínios", "Mercearia", "Padaria", "Outros", "Bazar e Utilidades")) if "q7" in R else BRANDLESS_TITLE.search(n)
        if "q7" in R: egg = bool(egg) or bool(re.search(r"\bgranel\b", n, re.I))
        if b: bs.append("source"); bk.append(alnum(b)); bn.append(b)
        elif inf: bs.append("inferred"); bk.append(inf); bn.append(disp[inf])
        elif "r2" in R and (d in BRANDLESS_DEPTS or egg or gen): bs.append("sem marca"); bk.append("semmarca"); bn.append("sem marca (não importa)")
        else: bs.append("none"); bk.append(""); bn.append("")
    out["brand_src"], out["bk"], out["brand_name"] = bs, bk, bn
    out["size"] = [p["size"] for p in P]; out["size_src"] = [p["size_src"] for p in P]
    out["conflict"] = [p["conflict"] for p in P]; out["multi"] = [p["multi"] for p in P]
    out["pack_qty"] = [p["pack_qty"] for p in P]; out["unit_count"] = [p["unit_count"] for p in P]
    out["unit_type"] = [p["unit_type"] for p in P]; out["pkg"] = [p["pkg"] for p in P]
    def core(n, b, bk_):
        bt = set(toks(b)); t = [x for x in toks(n) if x not in bt and x not in STOP and not re.fullmatch(r"\d+(ml|l|g|kg|gr|lt)?", x) and len(x) > 1]
        c = " ".join(sorted(set(t)))
        if not c and "r5" in R and bk_: c = "_" + bk_
        return c
    out["core"] = [core(n, b if bs_ != "sem marca" else "", k) for n, b, bs_, k in zip(names, out.brand_name, out.brand_src, out.bk)]
    out["qty"] = out.pack_qty.where(out.pack_qty > 0, out.unit_count)
    out["key"] = out.bk + "|" + out.core + "|" + out["size"] + "|" + out.qty.astype(str)
    has_b = out.bk != ""; has_s = out["size"] != ""
    okc = has_b & has_s & (out.core != "")
    k = out[okc].groupby("key").slug.nunique(); multi = set(k[k >= 2].index)
    out["key_x"] = out.key.isin(multi)
    gok = out.gtin.str.match(r"^\d{8,14}$")
    g = out[gok].groupby("gtin").slug.nunique(); gm = set(g[g >= 2].index)
    out["gtin_x"] = out.gtin.isin(gm) & gok
    q10 = "q10" in R
    def tier(r):
        if q10 and r.gtin_x and not r.key_x and r.size_src == "implicit_un": return "R"
        if r.gtin_x or r.key_x: return "A1"
        okk = r.bk and r["size"] and r.core
        if okk and not r.conflict and not r.multi and r.brand_src in ("source", "sem marca"): return "A2"
        if okk and not r.conflict and not r.multi and r.brand_src == "inferred": return "B1"
        if r.conflict or r.multi: return "B2"
        if r.bk and not r["size"]: return "B3"
        if r["size"] and not r.bk: return "B4"
        if r.bk and r["size"]: return "B3"
        return "C"
    out["tier"] = out.apply(tier, axis=1)
    return out

GROUPS = ["A1", "A2", "B1", "B2", "B3", "B4", "C", "R"]
RANK = {"A1": 0, "A2": 1, "R": 1, "B1": 2, "B2": 3, "B3": 3, "B4": 4, "C": 5}

def vc(o): return o.tier.value_counts().reindex(GROUPS).fillna(0).astype(int).to_dict()

def main():
    df = pd.read_csv(CSV, names=["id", "slug", "name", "brand", "gtin", "measure", "cats", "llm"], header=0, dtype=str, keep_default_na=False)
    dept = [canonical_department(c.split(" > ") if c else [], n) for c, n in zip(df.cats, df.name)]
    v1 = run(df, set(), dept)
    v1c = (v1.tier == "B3") & (v1.bk != "") & (v1["size"] != "") & (v1.core == "")
    v1.loc[v1c, "tier"] = "C"
    v2 = run(df, V2, dept)
    v3 = run(df, V3, dept)
    res = {"v1": vc(v1), "v2": vc(v2), "v3": vc(v3)}
    isA = lambda o: o.tier.isin(["A1", "A2"])
    solo = {}
    for q in sorted(RULES_V3):
        d = run(df, V2 | {q}, dept)
        t_old, t_new = v2.tier.map(RANK), d.tier.map(RANK)
        solo[q] = dict(desc=RULES_V3[q], groups=vc(d), into_A=int((isA(d) & ~isA(v2)).sum()), out_of_A=int((~isA(d) & isA(v2)).sum()),
                       improved=int((t_new < t_old).sum()), worsened=int((t_new > t_old).sum()))
    res["solo_on_v2"] = solo
    res["v2_to_v3_into_A"] = int((isA(v3) & ~isA(v2)).sum()); res["v2_to_v3_out_of_A"] = int((~isA(v3) & isA(v2)).sum())
    res["v1_to_v3_into_A"] = int((isA(v3) & ~isA(v1)).sum())
    res["moves_v2_v3"] = pd.crosstab(v2.tier, v3.tier).reindex(index=GROUPS, columns=GROUPS).fillna(0).astype(int).to_dict("index")
    for key, col in [("dept", "dept"), ("retailer", "slug")]:
        rows = []
        for val in v3[col].value_counts().index:
            r = {"name": val}
            for nm, o in [("v1", v1), ("v2", v2), ("v3", v3)]:
                x = o[o[col] == val] if col == "slug" else o[o.dept == val]
                r["n_" + nm] = len(x); r["A_" + nm] = round(100 * isA(x).mean(), 1) if len(x) else 0
                r["BC_" + nm] = round(100 * x.tier.isin(["B1", "B2", "B3", "B4", "C"]).mean(), 1) if len(x) else 0
            rows.append(r)
        res[key] = rows
    # dept v1/v2 use their own dept (v3 has meat remap): note
    res["dept_changed_q4"] = int((v3.dept != pd.Series(dept)).sum())
    res["diag"] = dict(size_src_v3=v3.size_src.value_counts().to_dict(), brand_src_v3=v3.brand_src.value_counts().to_dict(), brand_src_v2=v2.brand_src.value_counts().to_dict(),
                       unit_type_v3=v3[v3.unit_count > 0].unit_type.value_counts().to_dict(), dozens=int((v3.unit_type == "dz").sum()),
                       conflict_v2=int(v2.conflict.sum()), conflict_v3=int(v3.conflict.sum()), has_size_v2=int((v2["size"] != "").sum()), has_size_v3=int((v3["size"] != "").sum()),
                       multi_v3=int(v3.multi.sum()), review_R=int((v3.tier == "R").sum()))
    def reasons(o):
        r = {}
        for g in ["B1", "B2", "B3", "B4", "C"]:
            s = o[o.tier == g]; c = collections.Counter()
            for _, x in s.iterrows():
                nm = x["title"]
                if g == "B3": c["sem nenhuma medida/contagem no título"] += 1
                elif g == "B4":
                    c["sem marca na origem nem no dicionário"] += 1
                elif g == "B1": c["marca só inferida do título"] += 1
                elif g == "B2": c["kit / multi-medida" if x.multi else "tamanhos conflitantes"] += 1
                else: c["sem marca e sem tamanho"] += 1
            r[g] = dict(c.most_common())
        return r
    res["reasons_v3"] = reasons(v3)
    for g in ["B3", "B4", "C"]:
        res[f"{g}_by_dept_v3"] = v3[v3.tier == g].dept.value_counts().head(8).to_dict()
        res[f"{g}_by_ret_v3"] = v3[v3.tier == g].slug.value_counts().head(6).to_dict()
    # candidates (v2 extraction) with approval flags
    disp, surface, amb, prot = build_dictionary(df, {"r3"})
    rest = v2[(v2.brand_src == "none") | (v2.brand_src == "sem marca")]
    NOUN_SKIP = set("de da do das dos com sem para em e a o".split())
    DESCR = set("tradicional integral natural sabor premium original classico extra especial suave forte light zero diet gelado congelado resfriado fresco fatiado ralado moido picado seco pronto liquido liq po pasta cremoso tipo azul verde vermelho branco preto rosa amarelo laranja grande medio pequeno pequena media gde med peq infantil adulto adulta masculino feminino unissex leite chocolate morango limao uva maca banana coco carne frango bovino suino peixe queijo presunto tomate cebola alho batata arroz feijao milho trigo mel cafe cha agua suco pao bolo doce salgado azeite oleo sal acucar manteiga mussarela parmesao cheddar catupiry creme calabresa mista misto vegano vegetal sem lactose gluten acucar zero un und unid unidade kg g ml l lt litro quilo pacote caixa lata garrafa frasco pote saco bandeja refil kit pack combo sortido sortida diversos diversas cores cor variadas".split())
    cand = collections.defaultdict(lambda: dict(items=0, slugs=set(), ex=[], nouns=collections.Counter(), disp=collections.Counter()))
    branded_tok = collections.Counter()
    for name, b in zip(df.name, df.brand):
        if b:
            bt = set(toks(b))
            for t in set(toks(name)):
                if t not in bt: branded_tok[t] += 1
    for _, x in rest.iterrows():
        words = re.findall(r"[\wÀ-ÿ'&.]+", x["name"])
        if len(words) < 3: continue
        noun = words[0]; i = 1; seq = []
        while i < len(words) and len(seq) < 2:
            w = words[i]; f = fold(w).strip(".'&")
            if f in NOUN_SKIP and not seq: i += 1; continue
            if len(f) < 3 or re.search(r"\d", f) or f in DESCR or f in STOP: break
            seq.append(w); i += 1
        if not seq: continue
        c = " ".join(seq); kk = alnum(c)
        if kk in disp or " ".join(toks(c)) in surface: continue
        d = cand[kk]; d["items"] += 1; d["slugs"].add(x.slug); d["nouns"][fold(noun)] += 1; d["disp"][c] += 1
        if len(d["ex"]) < 2 and x["name"] not in d["ex"]: d["ex"].append(x["name"])
    rows = []
    for kk, d in cand.items():
        if d["items"] < 2: continue
        first = toks(d["disp"].most_common(1)[0][0])[0]
        common = first in COMMON_WORDS or branded_tok[first] >= 30 or len(d["nouns"]) / d["items"] > 0.6
        rows.append(dict(candidate=d["disp"].most_common(1)[0][0], items=d["items"], retailers=len(d["slugs"]), top_noun=d["nouns"].most_common(1)[0][0],
                         nouns_distinct=len(d["nouns"]), common_word_risk="SIM" if common else "", example_1=d["ex"][0], example_2=d["ex"][1] if len(d["ex"]) > 1 else ""))
    cdf = pd.DataFrame(rows).sort_values(["items", "retailers"], ascending=False)
    cdf = cdf[cdf.common_word_risk == ""].head(200).copy()
    appr = {alnum(a): a for a in APPROVED}
    cdf["approve"] = [("SIM" if alnum(c) in appr else "") for c in cdf.candidate]
    cdf["source"] = "extração"
    miss = [a for k, a in appr.items() if k not in {alnum(c) for c in cdf.candidate}]
    extra = pd.DataFrame([dict(candidate=a, items=int(v3.brand_name.eq(a).sum()), retailers=int(v3[v3.brand_name == a].slug.nunique()), top_noun="", nouns_distinct="", common_word_risk="", example_1="", example_2="", approve="SIM", source="aprovado pelo usuário") for a in miss])
    cdf = pd.concat([cdf, extra], ignore_index=True)
    cdf.to_csv(f"{OUT}/brand-candidates.csv", index=False, encoding="utf-8-sig")
    res["approved_hits"] = {a: int(v3.brand_name.eq(a).sum()) for a in APPROVED}
    v3.drop(columns=["gtin"]).to_csv("/tmp/coverage_v3_rows.csv", index=False)
    v2.drop(columns=["gtin"]).to_csv("/tmp/coverage_v2b_rows.csv", index=False)
    json.dump(res, open("/tmp/coverage_v3.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: res[k] for k in ["v1", "v2", "v3", "v2_to_v3_into_A", "v2_to_v3_out_of_A", "v1_to_v3_into_A", "diag", "reasons_v3", "approved_hits"]}, ensure_ascii=False, indent=1, default=str))

if __name__ == "__main__":
    main()
