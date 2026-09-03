"""Deterministic meat/butcher (Açougue) parser.

The parser is staged: generic tokens first, then abbreviations, then
source-agnostic cut/species dictionaries. Each stage is idempotent and returns a
``ParsedMeat`` whose ``variant_key`` groups comparable cuts (section 12.4 of the
architecture document: species, cut, bone, presentation, conservation and
seasoning define comparability for meat).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.enrichment.text import ascii_slug, fold, number

# Abbreviations observed across the collected sources. Keys are folded tokens.
ABBREVIATIONS: dict[str, str] = {
    "bov": "bovino",
    "bovina": "bovino",
    "bovino": "bovino",
    "su": "suino",
    "suin": "suino",
    "suina": "suino",
    "suino": "suino",
    "car": "carne",
    "fgo": "frango",
    "frango": "frango",
    "cong": "congelado",
    "congel": "congelado",
    "resf": "resfriado",
    "c/": "com",
    "s/": "sem",
    "s/ osso": "sem osso",
    "bd": "bandeja",
    "emb": "embalado",
    "peca": "peça",
    "granel": "a granel",
    "moida": "moída",
    "moido": "moído",
    "temp": "temperado",
    "temper": "temperado",
    "ling": "linguica",
    "lingui": "linguica",
    "carre": "carre",
    "figado": "figado",
    "pulmao": "pulmao",
    "moela": "moela",
    "sassami": "sassami",
    "sasami": "sassami",
}

# (canonical cut, tuple of folded tokens). Ordered from most specific to broad.
CUTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("frango_inteiro", ("frango inteiro", "ave inteira", "frango caipira", "frango a passarinho")),
    ("miolo_da_alcatra", ("miolo da alcatra", "miolo alcatra", "miolo da paleta")),
    ("costela_minga", ("costela minga",)),
    ("costela_janela", ("costela janela",)),
    ("costela_ripa", ("costela ripa", "ripa")),
    ("costela_ponta", ("costela ponta", "ponta de agulha")),
    ("assado_de_tiras", ("assado de tiras", "tiras")),
    ("capa_de_file", ("capa de filé", "capa de file", "capa file", "capa do filé", "capa do file")),
    ("copa_lombo", ("copa lombo", "copa de lombo", "bisteca do copa", "sobrepaleta")),
    ("file_mignon", ("filé mignon", "file mignon", "mignon", "filezinho")),
    ("contra_file", ("contra filé", "contra file", "contrafilé", "contrafile")),
    ("coxinha_da_asa", ("coxinha da asa", "coxinha asa", "meio da asa")),
    ("coxa_com_sobrecoxa", ("coxa com sobrecoxa", "coxa e sobrecoxa", "coxa sobrecoxa", "coxascoxa")),
    ("coxa", ("coxa", "coxa solteira")),
    ("sobrecoxa", ("sobrecoxa",)),
    ("baby_beef", ("baby beef",)),
    ("ancho", ("ancho",)),
    ("aranha", ("aranha",)),
    ("acem", ("acém", "acem")),
    ("alcatra", ("alcatra",)),
    ("bacon", ("bacon",)),
    ("bisteca", ("bisteca", "bist", "bife")),
    ("carre", ("carré", "carre")),
    ("bananinha", ("bananinha",)),
    ("coxao_duro", ("coxão duro", "coxao duro", "coxa duro")),
    ("coxao_mole", ("coxão mole", "coxao mole", "coxa mole")),
    ("entranha", ("entranha",)),
    ("salsicha", ("salsicha", "salsichão", "hot dog")),
    ("carne_moida", ("carne moída", "carne moida", "moída", "moida")),
    ("carne_seca", ("carne seca", "charque", "jerked")),
    ("coracao", ("coração", "coracao")),
    ("costela", ("costela", "costelinha")),
    ("cupim", ("cupim",)),
    ("figado", ("fígado", "figado")),
    ("fraldinha", ("fraldinha",)),
    ("lagarto", ("lagarto",)),
    ("linguica", ("linguiça", "linguica", "ling")),
    ("lombo", ("lombo",)),
    ("maminha", ("maminha",)),
    ("moela", ("moela",)),
    ("musculo", ("músculo", "musculo")),
    ("paleta", ("paleta",)),
    ("panceta", ("panceta",)),
    ("papada", ("papada",)),
    ("patinho", ("patinho",)),
    ("pe", ("pé", "pe")),
    ("peito", ("peito",)),
    ("pernil", ("pernil",)),
    ("picanha", ("picanha",)),
    ("pulmao", ("pulmão", "pulmao")),
    ("rabo", ("rabo",)),
    ("sassami", ("sassami", "sasami")),
    ("vazio", ("vazio",)),
    ("asa", ("asa", "asinha")),
    ("dorso", ("dorso",)),
    ("barriga", ("barriga",)),
    ("chorizo", ("chorizo",)),
    ("strogonoff", ("strogonoff", "strogonofe")),
    ("tilapia", ("tilápia", "tilapia")),
    ("cacao", ("cação", "cacao")),
    ("camarao", ("camarão", "camarao")),
    ("bacalhau", ("bacalhau",)),
    ("salmão", ("salmão", "salmao")),
    ("toucinho", ("toucinho",)),
)

SPECIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("frango", ("frango", "fgo", "galeto", "galinha", "chester", "peru")),
    ("bovino", ("bovino", "bov", "bovina", "boi", "vitela", "nelore")),
    ("suino", ("suino", "suíno", "suina", "suína", "porco", "leitão", "leitoa")),
    ("ave", ("ave", "ave natalina")),
    ("peixe", ("peixe", "camarão", "camarao", "tilápia", "tilapia", "cação", "cacao", "bacalhau", "salmão", "salmao", "sardinha", "merluza")),
)

BRANDS: tuple[str, ...] = (
    "friboi", "swift", "seara", "sadia", "perdigão", "aurora", "copacol",
    "jbs", "maturatta", "bassi", "quality beef", "reserva", "1953", "alibem",
    "ceratti", "sulita", "cofril", "calemba", "excelência", "gran reserva",
    "nobre", "qualifort", "felicitá", "maister", "languiru", "maravilha",
    "millenium", "festive", "frimesa", "canção", "speciale", "blesser",
    "fiesta", "real", "natto", "formoso", "friato", "regina", "rica",
    "super frango", "bom peixe", "mar & rio", "só pesca", "brazilian fish",
    "qualimar", "riberalves", "gadus morhua", "nho bento", "nutribem",
    "cerrati", "perdigao", "sao vicente", "minerva", "raça",
)

# ascii tokens that mark a non-meat item misclassified as Açougue.
NON_MEAT_TOKENS: tuple[str, ...] = (
    "alim p", "racao", "sache", "molho", "caldo", "massa", "capeletti",
    "ravioli", "faca p", "salg trigo", "mac marata", "lamen", "petisco",
    "acelga", "alface", "agriao", "alecrim", "beterraba", "brocolis",
    "couve", "espinafre", "repolho", "tomate", "cenoura", "batata",
    "cebola", "abobrinha", "alho", "salsinha",
)

_PORK_CUTS = {"bacon", "pernil", "lombo", "paleta", "panceta", "toucinho", "papada", "copa_lombo", "carre"}

_BEEF_CUTS = {
    "acem", "alcatra", "coxao_duro", "coxao_mole", "entranha", "bananinha",
    "capa_de_file", "contra_file", "fraldinha", "patinho", "lagarto",
    "cupim", "maminha", "picanha", "miolo_da_alcatra", "musculo",
    "assado_de_tiras", "vazio", "baby_beef", "aranha", "carne_seca",
}


@dataclass
class ParsedMeat:
    raw_name: str
    species: str | None = None
    cut: str | None = None
    bone_state: str | None = None
    skin_state: str | None = None
    presentation: str | None = None
    conservation: str | None = None
    seasoned: bool = False
    sale_mode: str | None = None  # "kg" | "peso_fixo" | "unidade"
    weight_kg: float | None = None
    brand: str | None = None
    concept: str | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def is_meat(self) -> bool:
        return self.species is not None and self.cut is not None

    @property
    def variant_key(self) -> tuple[Any, ...] | None:
        if not self.is_meat:
            return None
        return (
            self.species,
            self.cut,
            self.bone_state,
            self.skin_state,
            self.presentation,
            self.conservation,
            self.seasoned,
        )

    @property
    def label(self) -> str:
        if self.concept:
            return self.concept
        if not self.is_meat:
            return self.raw_name
        parts = [self.cut.replace("_", " ")]
        if self.bone_state == "sem_osso":
            parts.append("sem osso")
        elif self.bone_state == "com_osso":
            parts.append("com osso")
        if self.conservation:
            parts.append(self.conservation)
        return " ".join(parts).capitalize()


def _match_any(tokens: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for canonical, needles in rules:
        for needle in needles:
            if f" {needle} " in f" {tokens} ":
                return canonical
    return None


def parse_meat(raw_name: str) -> ParsedMeat:
    folded = fold(raw_name)
    tokens = ascii_slug(raw_name)

    result = ParsedMeat(raw_name=raw_name)

    if any(f" {token} " in f" {tokens} " for token in NON_MEAT_TOKENS):
        result.flags.append("non_meat")
        return result

    # Stage: species (needs abbreviations expanded first).
    expanded = _expand(tokens)
    result.species = _match_any(expanded, SPECIES)

    # Stage: conservation.
    result.conservation = _conservation(expanded)

    # Stage: sale mode + weight.
    result.sale_mode, result.weight_kg = _sale_mode(folded)

    # Stage: bone / skin.
    result.bone_state = _bone_state(expanded)
    result.skin_state = _skin_state(expanded)

    # Stage: presentation.
    result.presentation = _presentation(expanded)

    # Stage: seasoned.
    result.seasoned = _seasoned(expanded)

    # Stage: cut.
    result.cut = _match_any(expanded, CUTS)

    # Brand (attribute only; not identity for meat).
    result.brand = _brand(expanded)

    if result.cut and result.species is None and result.cut in _PORK_CUTS:
        result.species = "suino"
    if result.cut and result.species is None and result.cut in _BEEF_CUTS:
        result.species = "bovino"
    if result.cut == "linguica" and result.species is None:
        if "frango" in expanded:
            result.species = "frango"
        elif "bovino" in expanded or "bovina" in expanded:
            result.species = "bovino"
        else:
            result.species = "suino"
    if result.cut == "frango_inteiro" and result.species is None:
        result.species = "frango"

    if result.cut and result.species:
        result.concept = f"{result.cut.replace('_', ' ').title()} {_species_label(result.species)}"
    return result


def _expand(tokens: str) -> str:
    out: list[str] = []
    for word in tokens.split():
        out.append(ABBREVIATIONS.get(word, word))
    text = " ".join(out)
    # join contractions like "c/ osso" -> "com osso"
    text = re.sub(r"\bc\s*/\s*", "com ", text)
    text = re.sub(r"\bs\s*/\s*", "sem ", text)
    text = re.sub(r"\bp\s*/\s*", "para ", text)
    return text


def _conservation(expanded: str) -> str | None:
    if re.search(r"\b(congelad[oa]|cong|iqf|frost)\b", expanded):
        return "congelado"
    if re.search(r"\b(resfriad[oa]|resf|fresc[oa]|gelado)\b", expanded):
        return "resfriado"
    return None


def _sale_mode(folded: str) -> tuple[str | None, float | None]:
    # Fixed weight first: "1kg", "500g", "16kg", "750 g", "1,5kg".
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|quilos?|g|gr|gramas?)", folded)
    if match:
        amount = number(match.group(1))
        unit = match.group(2).lower()
        if amount is not None:
            if unit.startswith(("kg", "quilo")):
                return "peso_fixo", amount
            if unit.startswith(("g", "gr", "grama")):
                return "peso_fixo", amount / 1000
    if re.search(r"\b(por quilo|preço por quilo|quilo|a granel|granel|kg)\b", folded):
        return "kg", None
    if re.search(r"\b(bandeja|peça|peca|pacote|embalado|emb|unidade|un|pedaço)\b", folded):
        return "unidade", None
    return None, None


def _bone_state(expanded: str) -> str | None:
    if re.search(r"\b(sem osso|desossad[oa]|dessosad[oa]|s osso)\b", expanded):
        return "sem_osso"
    if re.search(r"\b(com osso|c osso|inteiro)\b", expanded):
        return "com_osso"
    return None


def _skin_state(expanded: str) -> str | None:
    if re.search(r"\b(com pele|com couro)\b", expanded):
        return "com_pele"
    if re.search(r"\b(sem pele|sem couro)\b", expanded):
        return "sem_pele"
    return None


def _presentation(expanded: str) -> str | None:
    rules = (
        ("moida", r"\bmo[ií]d[ao]\b"),
        ("cubos", r"\bcubos?\b"),
        ("fatiado", r"\bfatiad[ao]\b"),
        ("porcionado", r"\bporcionad[ao]\b"),
        ("inteiro", r"\binteir[oa]\b"),
        ("empanado", r"\bempanad[oa]\b"),
        ("desfiado", r"\bdesfiad[oa]\b"),
        ("posta", r"\bpostas?\b"),
        ("bife", r"\bbifes?\b"),
        ("peca", r"\b(peça|peca|meia peça)\b"),
    )
    for canonical, pattern in rules:
        if re.search(pattern, expanded):
            return canonical
    return None


def _seasoned(expanded: str) -> bool:
    pattern = (
        r"\b(temperad[oa]|temp|chimichurri|ao vinho|na brasa|assa facil|"
        r"assa fácil|molho|caseir[oa]|mostarda|orgânico|organico)\b"
    )
    return bool(re.search(pattern, expanded))


def _brand(expanded: str) -> str | None:
    for brand in BRANDS:
        if f" {brand} " in f" {expanded} ":
            return brand
    return None


_SPECIES_LABEL = {
    "bovino": "Bovino",
    "suino": "Suíno",
    "frango": "Frango",
    "ave": "Ave",
    "peru": "Peru",
    "peixe": "Peixe",
}


def _species_label(species: str) -> str:
    return _SPECIES_LABEL.get(species, species)
