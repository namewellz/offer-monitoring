from datetime import UTC, datetime

from app.catalog.dashboard import render_catalog_dashboard


def test_catalog_dashboard_has_mobile_and_manual_update_controls() -> None:
    html = render_catalog_dashboard(
        results=[],
        product=None,
        retailer=None,
        department=None,
        direction="all",
        minimum_percent=0,
        view="all",
        total_results=0,
        page=1,
        page_size=100,
        latest_runs=[
            {
                "retailer": "São Vicente",
                "store": "São Vicente Hortolândia",
                "product_count": 100,
                "collected_at": datetime(2026, 8, 26, 12, tzinfo=UTC),
            }
        ],
    )

    assert 'name="viewport"' in html
    assert 'id="manual-update"' in html
    assert 'id="update-all-button"' in html
    assert 'id="collection-history"' in html
    assert "Forçar atualização de todas as fontes" in html
    assert 'value="sao-vicente"' in html
    assert "/static/catalog.css?v=" in html
    assert "/static/catalog.js?v=" in html
    assert "São Vicente Hortolândia" in html
    assert 'name="view"' in html
    assert 'value="all" selected' in html
    assert "Todos os produtos" in html


def test_catalog_dashboard_renders_product_without_price_change() -> None:
    html = render_catalog_dashboard(
        results=[
            {
                "product": "Cerveja sem alteração",
                "brand": "Exemplo",
                "department": "Bebidas",
                "retailer": "Mercado",
                "store": "Loja",
                "previous_price": None,
                "current_price": 4.99,
                "change_percent": None,
                "price_condition": "Preço final",
                "price_condition_type": "final",
                "observed_at": datetime(2026, 8, 26, 12, tzinfo=UTC),
            }
        ],
        product="cerveja",
        retailer=None,
        department="Bebidas",
        direction="all",
        minimum_percent=0,
        view="all",
        total_results=1,
        page=1,
        page_size=100,
        latest_runs=[],
    )

    assert "Cerveja sem alteração" in html
    assert "Sem referência" in html
    assert "R$ 4,99" in html


def test_catalog_dashboard_has_offers_tab_and_discount() -> None:
    html = render_catalog_dashboard(
        results=[
            {
                "product": "Cerveja em oferta",
                "brand": "Exemplo",
                "department": "Bebidas",
                "retailer": "Mercado",
                "store": "Loja",
                "regular_price": 10,
                "previous_price": 9,
                "current_price": 8,
                "discount": 2,
                "change_percent": -11.11,
                "price_condition": "Preço final",
                "price_condition_type": "final",
                "observed_at": datetime(2026, 8, 26, 12, tzinfo=UTC),
            }
        ],
        product=None,
        retailer=None,
        department=None,
        direction="all",
        minimum_percent=0,
        view="offers",
        total_results=1,
        page=1,
        page_size=100,
        latest_runs=[],
    )

    assert 'href="/catalog?view=offers" class="active"' in html
    assert "Preço de" in html
    assert "Oferta -20.00%" in html
