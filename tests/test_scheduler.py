from app.scheduler import CATALOG_RETAILERS, enqueue_catalogs, enqueue_sources


def test_max_atacadista_is_scheduled() -> None:
    assert "max-atacadista" in CATALOG_RETAILERS


def test_one_source_error_does_not_stop_others() -> None:
    called = []

    def enqueue(source):
        called.append(source)
        if source == "bad":
            raise RuntimeError("blocked")

    errors = enqueue_sources(["good-1", "bad", "good-2"], enqueue)
    assert called == ["good-1", "bad", "good-2"]
    assert len(errors) == 1


def test_one_catalog_error_does_not_stop_other_retailers() -> None:
    called = []

    def enqueue(retailer):
        called.append(retailer)
        if retailer == "goodbom":
            raise RuntimeError("blocked")

    errors = enqueue_catalogs(
        ("arena-atacado", "goodbom", "atacadao", "savegnago"), enqueue
    )
    assert called == ["arena-atacado", "goodbom", "atacadao", "savegnago"]
    assert len(errors) == 1
