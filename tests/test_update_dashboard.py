from datetime import UTC, datetime

from app.catalog.update_dashboard import render_update_dashboard


def test_update_dashboard_groups_failures_by_source_and_lists_each_page() -> None:
    html = render_update_dashboard(
        [
            {
                "slug": "savegnago",
                "name": "Savegnago",
                "latest_product_count": 14500,
                "latest_priced_product_count": 12000,
                "latest_collected_at": datetime(2026, 8, 29, 12, tzinfo=UTC),
                "executions": [
                    {
                        "status": "PARTIAL_SUCCESS",
                        "occurred_at": datetime(2026, 8, 29, 12, tzinfo=UTC),
                        "product_count": 14500,
                        "priced_product_count": 12000,
                        "errors": [
                            {"scope": "category=10 page=2", "error": "HTTP 500"},
                            {"scope": "category=11 page=4", "error": "timeout"},
                        ],
                    }
                ],
            }
        ]
    )

    assert "14.500 itens na última coleta" in html
    assert "category=10 page=2" in html
    assert "category=11 page=4" in html
    assert "HTTP 500" in html
    assert "Parcial" in html
