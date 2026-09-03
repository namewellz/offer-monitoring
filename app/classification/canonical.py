"""Canonical Açougue categories.

Two concerns:
- ``CANONICAL_CATEGORIES``: the controlled vocabulary sent to the LLM so it
  answers with a fixed set of names (no more "Acém"/"Acém Bovino"/"Acém em
  Cubos" drift). Extend/curate freely.
- ``llm_category_labels``: DB overrides mapping each raw label the model already
  produced to the canonical display name. Editing it (via the "Categorias"
  screen) fixes/merges categories without re-running the model.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models_v2 import LlmCategoryLabel, LlmClassification


def _fold_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


_SPECIES_ASCII = {
    "bovino", "bovina", "suino", "suina", "frango", "peru", "peixe", "ave",
    "boi", "porco", "cordeiro", "pato", "chester", "galinha", "leitao",
}
_CONNECTORS = {"a", "de", "da", "do", "em", "com", "e", "as", "os", "das", "dos"}
_SKIP_STRIP_HEAD = _SPECIES_ASCII | {"empanado", "empanada", "milanesa", "inteiro"}
# Species must be KEPT for these heads (e.g. Picanha Suína != Picanha bovina).
_KEEP_SPECIES_HEAD = {"picanha"}
# Head synonyms (Barriga Suína == Panceta).
_HEAD_ALIAS = {"barriga": "Panceta"}


def normalize_category(name: str) -> str:
    """Deterministic, conservative cleanup used to seed canonical names.

    Only removes *redundant* leading qualifiers (Bife/Miúdo/Recorte/Espetinho
    when a clear head follows) and a *final* bovine/porcine species adjective
    ("Acém Bovino" -> "Acém"). Detection runs on the ascii-folded text but the
    original spelling/case of what stays is preserved. Ambiguous cases are left
    untouched (the reviewer fixes on the panel).
    """
    original = " ".join(name.split())
    if not original:
        return original
    folded = _fold_ascii(original)

    start = 0
    for prefix in ("recorte de ", "recorte ", "miudo ", "bife de ", "bife "):
        if folded.startswith(prefix):
            rest = folded[len(prefix):].strip()
            first = rest.split()[0] if rest.split() else ""
            if first and first not in _SKIP_STRIP_HEAD and first not in _CONNECTORS:
                start = len(prefix)
                break

    tail = folded[start:]
    # strip sale-form words (they are their own price row: fatiado/cubos/moída/desfiado/posta)
    while True:
        match = re.search(
            r"(?:\s+(?:em cubos|cubos|fatiad[oa]|desfiad[oa]|postas?|moid[oa]))+$",
            tail,
        )
        if not match:
            break
        tail = tail[: match.start()]
    # strip a FINAL redundant bovine/porcine species word (unless the head needs
    # its species, e.g. Picanha Suína must stay separate from beef Picanha)
    head = tail.split()[0].lower() if tail.split() else ""
    if head not in _KEEP_SPECIES_HEAD:
        tail = re.sub(r"\s+(bovino|bovina|suino|suina)$", "", tail)

    end = start + len(tail)
    kept = original[start:end].strip()
    kept_folded = _fold_ascii(kept)
    if not kept or (len(kept_folded.split()) <= 1 and kept_folded in _SPECIES_ASCII):
        return original
    kept = " ".join(kept.split())
    # head aliases (Barriga Suína == Panceta)
    tokens = kept.split()
    if tokens and _fold_ascii(tokens[0]) in _HEAD_ALIAS:
        tokens[0] = _HEAD_ALIAS[_fold_ascii(tokens[0])]
        kept = " ".join(tokens)
    return kept

# Curated closed vocabulary used to steer the LLM (and shown on the screen).
CANONICAL_CATEGORIES: tuple[str, ...] = (
    "Alcatra", "Ancho", "Aranha", "Acém", "Bacon", "Bisteca Suína",
    "Bucho", "Capa de Filé", "Carne Bovina Salgada", "Carne Moída",
    "Carne Seca", "Carne Suína Salgada", "Carré Suíno", "Charque",
    "Contra-filé", "Copa Lombo", "Coração Bovina", "Coração de Frango",
    "Costela Bovina", "Costela de Cordeiro", "Costela Suína", "Coxão Duro",
    "Coxão Mole", "Cupim", "Entranha", "Figado Bovino", "Figado de Frango",
    "Filé de Frango", "Filé de Peixe", "Filé Mignon", "Fraldinha",
    "Frango a Passarinho", "Frango Caipira", "Frango Inteiro", "Lagarto",
    "Linguiça Calabresa", "Linguiça Cuiabana", "Linguiça Defumada",
    "Linguiça de Frango", "Linguiça Fininha", "Linguiça Mista",
    "Linguiça Paio", "Linguiça Pernil", "Linguiça Portuguesa",
    "Linguiça Suína", "Linguiça Toscana", "Linguiça Vegana", "Lombo Suíno",
    "Maminha", "Moela", "Músculo", "Paleta Suína", "Panceta", "Papada",
    "Patinho", "Peito de Frango", "Peito de Peru Defumado", "Peito Bovina",
    "Pernil Suíno", "Picanha", "Presunto Fatiado", "Pulmão", "Rabo Suíno",
    "Salsicha", "Sassami", "Sobrecoxa de Frango", "Asa de Frango",
    "Coxa de Frango", "Coxinha da Asa", "Bacalhau", "Camarão",
    "Filé de Peixe Branco", "Peixe Inteiro", "Salmão", "Tilápia",
    # extras em uso (majors) para sugestões/fallback
    "Hambúrguer", "Hambúrguer Bovino", "Hambúrguer de Frango", "Hambúrguer Misto",
    "Coxa/Sobrecoxa de Frango", "Peixe (filé inteiro)", "Sardinha", "Mortadela",
    "Mortadela Defumada", "Mortadela de Frango", "Lombo Canadense", "Lombo Cozido",
    "Peito de Frango Defumado", "Moela de Frango", "Pé Suíno", "Pé de Frango",
    "Filezinho Sassami", "Filezinho de Frango", "Paleta Bovina", "Picanha Suína",
    "Steak de Frango", "Panceta Suína", "Isca de Frango", "Fígado de Frango",
    "Barriga Suína", "Paio", "Bucho", "Almôndega Bovina", "Almôndega Mista",
    "Músculo Bovino", "Patê de Peito de Peru", "Embutido de Lombo", "Espetinho Bovino",
    "Salame", "Salame Italiano", "Fiambre", "Orelha Suína", "Mocotó", "Rabada Bovina",
    "Língua Bovina", "Kibe", "Jerked Beef", "Fígado Bovino", "Bisteca Bovina",
    "Ponta de Peito Bovina", "Alcatra Suína", "Maminha Bovina", "Costelinha Suína",
    "Rabo Suíno", "Toucinho", "Suã Suíno", "Chuleta", "Osso Buco",
    "Pernil de Cordeiro", "Frango Desfiado", "Frango Temperado", "Iscas de Peixe",
    "Peixe Salgado", "Bife Bovino", "Bife Ancho", "Miolo de Alcatra",
)


# --- Departamento --------------------------------------------------------------
#
# O mesmo motor classifica vários departamentos (Açougue hoje; Mercearia,
# Bebidas, Frios e Laticínios primeiro). Cada departamento tem seu próprio
# vocabulário canônico (llm_category_labels.department) e suas classificações
# (llm_classifications.department). As funções abaixo aceitam ``department`` e
# usam "Açougue" como padrão para não quebrar telas/scripts existentes.


def department_code(department: str) -> str:
    """Slug simples do departamento (ex.: 'Frios e Laticínios' -> 'frios_e_laticinios')."""
    return _fold_ascii(department or "").replace(" ", "_") or "outros"


def reject_token(department: str) -> str:
    """Token que a LLM deve usar para 'não é deste departamento'."""
    if department == "Açougue":
        return "NAO_CARNE"
    return "NAO_" + department_code(department).upper()


def department_seed(department: str) -> tuple[str, ...]:
    """Vocabulário inicial (curado) de um departamento, usado como fallback."""
    return DEPARTMENT_SEEDS.get(department) or ()


# Vocabulários canônicos iniciais por departamento (curados; o painel refina).
DEPARTMENT_SEEDS: dict[str, tuple[str, ...]] = {
    "Açougue": CANONICAL_CATEGORIES,
    "Mercearia": (
        # cereais, grãos e farinhas
        "Arroz", "Arroz Integral", "Arroz Parboilizado", "Feijão Carioca",
        "Feijão Preto", "Feijão de Corda", "Lentilha", "Grão de Bico",
        "Ervilha Seca", "Soja", "Milho de Pipoca", "Canjica", "Quinoa",
        "Aveia", "Granola", "Farinha de Trigo", "Farinha de Mandioca",
        "Farinha de Milho", "Fubá", "Polvilho Doce", "Polvilho Azedo",
        "Farinha de Rosca", "Farinha Láctea", "Amido de Milho", "Cuscuz",
        "Farofa Pronta", "Farinha de Arroz",
        # massas
        "Macarrão", "Macarrão Instantâneo", "Macarrão de Sêmola",
        "Talharim", "Penne", "Macarrão para Salada", "Nhoque", "Rondelli",
        # açúcar e adoçantes
        "Açúcar Cristal", "Açúcar Refinado", "Açúcar Mascavo",
        "Açúcar Demerara", "Adoçante",
        # café, chá e achocolatados
        "Café Torrado e Moído", "Café Solúvel", "Café em Cápsulas",
        "Cappuccino", "Chá Preto", "Chá de Ervas", "Chá Mate", "Chá Verde",
        "Achocolatado em Pó", "Chocolate em Pó", "Chocolate Quente",
        # óleos, vinagres, sal e temperos
        "Óleo de Soja", "Óleo de Girassol", "Óleo de Canola", "Azeite de Oliva",
        "Vinagre", "Vinagre Balsâmico", "Sal Refinado", "Sal Grosso",
        "Sal Marinho", "Açafrão", "Orégano", "Pimenta-do-Reino", "Páprica",
        "Canela em Pó", "Cominho", "Curry", "Tempero Completo",
        "Tempero de Alho", "Alho Triturado", "Caldo de Galinha",
        "Caldo de Carne", "Caldo de Legumes", "Pimenta Calabresa",
        "Catchup", "Mostarda", "Maionese", "Molho Shoyu", "Molho Inglês",
        "Molho de Pimenta", "Molho de Tomate", "Extrato de Tomate",
        "Tomate Pelado", "Molho Branco", "Molho de Alho", "Molho de Salada",
        "Tempero Pronto", "Especiarias",
        # conservas e enlatados
        "Azeitona", "Palmito", "Milho Verde em Conserva",
        "Ervilha em Conserva", "Seleta de Legumes", "Atum em Lata",
        "Sardinha em Lata", "Cogumelos em Conserva", "Feijoada Pronta",
        "Legumes em Conserva", "Molho de Tomate com Pedaços",
        # biscoitos e snacks
        "Biscoito Recheado", "Biscoito de Polvilho", "Biscoito Cream Cracker",
        "Biscoito Água e Sal", "Biscoito Maizena", "Biscoito Wafer",
        "Biscoito de Leite", "Salgadinho de Milho", "Batata Chips",
        "Amendoim Torrado", "Amendoim Japonês", "Castanha de Caju",
        "Pipoca de Micro-ondas", "Torrada", "Mistura para Pipoca",
        # matinais e confeitaria em pó
        "Cereal Matinal", "Mingau", "Mistura para Bolo", "Fermento em Pó",
        "Fermento Biológico", "Essência de Baunilha", "Coco Ralado",
        "Gelatina em Pó", "Sopa Instantânea", "Creme de Cebola",
        "Molho para Salada",
    ),
    "Bebidas": (
        "Cerveja Pilsen", "Cerveja Premium", "Cerveja Artesanal",
        "Cerveja Sem Álcool", "Cerveja Malzbier", "Chopp", "Vinho Tinto",
        "Vinho Branco", "Vinho Rosé", "Vinho de Mesa", "Espumante",
        "Prosecco", "Champagne", "Whisky", "Vodca", "Cachaça", "Gin",
        "Rum", "Tequila", "Conhaque", "Licor", "Energético", "Isotônico",
        "Água com Gás", "Água Mineral", "Água de Coco", "Água Tônica",
        "Refrigerante Cola", "Refrigerante Guaraná", "Refrigerante Laranja",
        "Refrigerante Limão", "Refrigerante Soda", "Refrigerante Zero",
        "Refrigerante de Uva", "Suco de Fruta", "Suco Integral",
        "Suco em Pó", "Néctar", "Bebida de Soja", "Chá Gelado",
        "Chá Pronto", "Mate", "Kombucha", "Bebida Láctea", "Bitter",
        "Cerveja Importada", "Água Saborizada",
    ),
    "Frios e Laticínios": (
        "Leite Integral", "Leite Desnatado", "Leite Semidesnatado",
        "Leite Zero Lactose", "Leite em Pó", "Leite Fermentado",
        "Iogurte Natural", "Iogurte de Frutas", "Iogurte Grego",
        "Iogurte Zero Lactose", "Bebida Láctea", "Petit Suisse",
        "Requeijão", "Manteiga", "Manteiga sem Sal", "Margarina",
        "Margarina Light", "Creme de Leite", "Creme de Leite Fresco",
        "Queijo Muçarela", "Queijo Prato", "Queijo Parmesão",
        "Queijo Parmesão Ralado", "Queijo Minas Frescal",
        "Queijo Minas Padrão", "Queijo Coalho", "Queijo Provolone",
        "Queijo Gorgonzola", "Queijo Brie", "Queijo Camembert",
        "Queijo Cottage", "Queijo Ricota", "Queijo Colonial",
        "Queijo Suíço", "Queijo Cheddar", "Queijo Fundido",
        "Queijo de Búfala", "Queijo Ralado", "Presunto", "Presunto Cozido",
        "Presunto de Peru", "Mortadela", "Mortadela Defumada", "Salame",
        "Salame Italiano", "Peito de Peru", "Peito de Peru Defumado",
        "Blanquet de Peru", "Lombo Canadense", "Queijo Processado",
    ),
}


def seed_categories(db: Session, department: str = "Açougue") -> int:
    """Insert distinct accepted categories (from LLM runs) as editable labels.

    New labels default canonical = label; existing entries are untouched so user
    overrides survive new classification runs. Scoped to ``department``.
    """
    labels = db.execute(
        select(LlmClassification.line_key)
        .where(
            LlmClassification.decision == "accept",
            LlmClassification.department == department,
            LlmClassification.line_key.notin_(("reject", "NAO_CARNE")),
        )
        .distinct()
    ).scalars().all()
    existing = set(
        db.execute(
            select(LlmCategoryLabel.label).where(
                LlmCategoryLabel.department == department
            )
        ).scalars().all()
    )
    added = 0
    for label in labels:
        if label and label not in existing:
            canonical = normalize_category(label) or label
            db.add(
                LlmCategoryLabel(
                    label=label, canonical=canonical, department=department
                )
            )
            added += 1
    if added:
        db.commit()
    return added


def canonical_map(db: Session, department: str = "Açougue") -> dict[str, str]:
    """label -> canonical (defaults to label when absent), scoped to department."""
    rows = db.execute(
        select(LlmCategoryLabel.label, LlmCategoryLabel.canonical).where(
            LlmCategoryLabel.department == department
        )
    ).all()
    return {label: canonical for label, canonical in rows}


def distinct_canonicals(db: Session, department: str = "Açougue") -> list[str]:
    """Canonical names in use for a department (after merges/renames)."""
    rows = db.execute(
        select(LlmCategoryLabel.canonical)
        .where(LlmCategoryLabel.department == department)
        .distinct()
        .order_by(LlmCategoryLabel.canonical)
    ).scalars().all()
    return [name for name in rows if name]


def prompt_canonical_names(db: Session, department: str = "Açougue") -> list[str]:
    """Vocabulary sent to the LLM for a department = canonical names from panel.

    Editing/merging categories in the panel changes the next classification run
    with no code changes. Falls back to the curated seed when empty.
    """
    names = distinct_canonicals(db, department=department)
    return names or list(department_seed(department))


def category_counts(db: Session, department: str = "Açougue") -> list[dict[str, Any]]:
    """Raw labels in use (accepted) for a department, with item count."""
    rows = db.execute(
        select(
            LlmClassification.line_key.label("label"),
            func.count().label("n"),
        )
        .where(
            LlmClassification.decision == "accept",
            LlmClassification.department == department,
            LlmClassification.line_key.notin_(("reject", "NAO_CARNE")),
        )
        .group_by(LlmClassification.line_key)
        .order_by(func.count().desc())
    ).all()
    overrides = canonical_map(db, department=department)
    return [
        {
            "label": label,
            "canonical": overrides.get(label, label),
            "count": n,
        }
        for label, n in rows
    ]


def set_canonicals(
    db: Session, updates: list[dict[str, Any]], department: str = "Açougue"
) -> dict[str, int]:
    """Upsert canonical for the given labels (department-scoped). Returns counts."""
    created = updated = 0
    for update in updates:
        label = (update.get("label") or "").strip()
        canonical = (update.get("canonical") or label).strip() or label
        if not label:
            continue
        existing = db.execute(
            select(LlmCategoryLabel).where(
                LlmCategoryLabel.department == department,
                LlmCategoryLabel.label == label,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                LlmCategoryLabel(
                    label=label, canonical=canonical, department=department
                )
            )
            created += 1
        elif existing.canonical != canonical:
            existing.canonical = canonical
            updated += 1
    db.commit()
    return {"created": created, "updated": updated}


def normalize_all(
    db: Session, department: str = "Açougue", commit: bool = True
) -> dict[str, Any]:
    """Preview or apply canonical normalization over stored labels of a department.

    With ``commit=False`` returns the mapping without writing, for review.
    """
    rows = db.execute(
        select(LlmCategoryLabel).where(
            LlmCategoryLabel.department == department
        )
    ).scalars().all()
    plan: dict[str, str] = {}
    for row in rows:
        normalized = normalize_category(row.label)
        if normalized and normalized != row.canonical:
            plan[row.label] = normalized
    if commit and plan:
        for row in rows:
            target = plan.get(row.label)
            if target:
                row.canonical = target
        db.commit()
    return {"labels": len(rows), "changed": len(plan), "plan": plan}
