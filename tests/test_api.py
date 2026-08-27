from app.main import item_or_404


def test_item_or_404_returns_existing_item() -> None:
    value = object()
    assert item_or_404(value, "Thing") is value
