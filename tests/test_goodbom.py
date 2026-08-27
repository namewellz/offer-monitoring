from pathlib import Path

import pytest

from app.core.exceptions import ParserChangedError
from app.providers.goodbom import GoodBomProvider


def test_parses_original_src_assets() -> None:
    html = Path("tests/fixtures/goodbom/monte_mor.html").read_text()
    pages = GoodBomProvider.parse_pages(html, "https://institucional.goodbom.com.br/current/")
    assert [page.page_number for page in pages] == [1, 2]
    assert (
        pages[0].url == "https://institucional.goodbom.com.br/tabloides/assets/monte-mor/page-1.jpg"
    )
    assert pages[1].url == "https://cdn.goodbom.example/page-2.jpg"


def test_parser_change_is_explicit() -> None:
    with pytest.raises(ParserChangedError):
        GoodBomProvider.parse_pages("<html></html>", "https://example.test")
