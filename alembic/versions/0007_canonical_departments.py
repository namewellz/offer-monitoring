"""Add a canonical department to catalog products."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_canonical_departments"
down_revision: str | None = "0006_catalog_offer_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_products",
        sa.Column("department", sa.String(length=80), nullable=False, server_default="Outros"),
    )
    op.create_index("ix_catalog_products_department", "catalog_products", ["department"])

    # A first backfill makes existing data useful immediately. Every subsequent
    # collection applies the richer Python taxonomy, including product-name fallback.
    source = "translate(lower(coalesce(categories::text, '')), 'áàâãéêíóôõúüç', 'aaaaeeiooouuc')"
    name = "translate(lower(coalesce(name, '')), 'áàâãéêíóôõúüç', 'aaaaeeiooouuc')"
    op.execute(
        sa.text(
            f"""
            UPDATE catalog_products SET department = CASE
              WHEN {source} ~ 'peixaria|pescado|frutos do mar' THEN 'Peixaria'
              WHEN {source} ~ 'acougue|carnes|bovino|suino|aves' THEN 'Açougue'
              WHEN {source} ~ 'bebida|cerveja|vinho|destilado|coca cola' THEN 'Bebidas'
              WHEN {source} ~ 'higiene|beleza|perfumaria|cuidados pessoais|fralda' THEN 'Higiene'
              WHEN {source} ~ 'limpeza|lavanderia' THEN 'Limpeza'
              WHEN {source} ~ 'hortifruti|frutas|verduras|legumes' THEN 'Hortifruti'
              WHEN {source} ~ 'frios|laticinio|queijo|iogurte' THEN 'Frios e Laticínios'
              WHEN {source} ~ 'congelado|perecivel industrializado|swift' THEN 'Congelados'
              WHEN {source} ~ 'padaria|panificacao|confeitaria' THEN 'Padaria'
              WHEN {source} ~ 'pet shop|mundo pet|animais' THEN 'Pet Shop'
              WHEN {source} ~ 'saudavel|organico|natural' THEN 'Saudáveis e Orgânicos'
              WHEN {source} ~ 'doces|sobremesas|chocolate|sorvete' THEN 'Doces e Sobremesas'
              WHEN {source} ~ 'bazar|utilidades|magazine|eletro|papelaria|esporte e lazer|brinquedo|vestuario|roupas e calcados|descartaveis e embalagens|automotivo|jardinagem|flores e plantas' THEN 'Bazar e Utilidades'
              WHEN {source} ~ 'mercearia|alimentos|biscoito|salgadinho|massas|graos|cereais' THEN 'Mercearia'
              WHEN {name} ~ 'cupim|picanha|alcatra|costela|fraldinha|bovino|suino|frango|linguica' THEN 'Açougue'
              WHEN {name} ~ 'cerveja|refrigerante|suco|agua mineral|vinho|whisky|vodka' THEN 'Bebidas'
              WHEN {name} ~ 'shampoo|sabonete|desodorante|creme dental|papel higienico|fralda|absorvente' THEN 'Higiene'
              WHEN {name} ~ 'detergente|desinfetante|amaciante|sabao em po|agua sanitaria|limpador' THEN 'Limpeza'
              ELSE 'Outros'
            END
            """
        )
    )

    # Flyer offers already have a category column; normalize populated records
    # to the same vocabulary without changing their schema.
    offer_category = "translate(lower(coalesce(category, '')), 'áàâãéêíóôõúüç', 'aaaaeeiooouuc')"
    offer_name = "translate(lower(coalesce(normalized_name, raw_name, '')), 'áàâãéêíóôõúüç', 'aaaaeeiooouuc')"
    op.execute(
        sa.text(
            f"""
            UPDATE product_offers SET category = CASE
              WHEN {offer_category} ~ 'peixaria|pescado|peixe' THEN 'Peixaria'
              WHEN {offer_category} ~ 'acougue|carne|bovino|suino|aves' OR {offer_name} ~ 'cupim|picanha|alcatra|costela|fraldinha|bovino|suino|frango|linguica' THEN 'Açougue'
              WHEN {offer_category} ~ 'bebida' OR {offer_name} ~ 'cerveja|refrigerante|suco|agua mineral|vinho|whisky|vodka' THEN 'Bebidas'
              WHEN {offer_category} ~ 'higiene|beleza|perfumaria' OR {offer_name} ~ 'shampoo|sabonete|desodorante|creme dental|papel higienico|fralda|absorvente' THEN 'Higiene'
              WHEN {offer_category} ~ 'limpeza' OR {offer_name} ~ 'detergente|desinfetante|amaciante|sabao em po|agua sanitaria|limpador' THEN 'Limpeza'
              WHEN {offer_category} ~ 'hortifruti|frutas|verduras|legumes' THEN 'Hortifruti'
              WHEN {offer_category} ~ 'frios|laticinio' THEN 'Frios e Laticínios'
              WHEN {offer_category} ~ 'congelado' THEN 'Congelados'
              WHEN {offer_category} ~ 'padaria' THEN 'Padaria'
              WHEN {offer_category} ~ 'pet' THEN 'Pet Shop'
              WHEN {offer_category} ~ 'doce|sobremesa' THEN 'Doces e Sobremesas'
              WHEN {offer_category} ~ 'bazar|utilidades' THEN 'Bazar e Utilidades'
              WHEN {offer_category} ~ 'mercearia' THEN 'Mercearia'
              ELSE 'Outros'
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_products_department", table_name="catalog_products")
    op.drop_column("catalog_products", "department")
