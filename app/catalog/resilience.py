from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def collection_issue(scope: str, error: BaseException) -> dict[str, str]:
    message = str(error).strip() or error.__class__.__name__
    return {"scope": scope, "error": f"{error.__class__.__name__}: {message}"}


def successful_results(
    scopes: Sequence[str], results: Sequence[Any], errors: list[dict[str, str]]
) -> list[Any]:
    successful = []
    for scope, result in zip(scopes, results, strict=True):
        if isinstance(result, BaseException):
            errors.append(collection_issue(scope, result))
        else:
            successful.append(result)
    return successful


def collection_metadata(errors: Iterable[dict[str, str]]) -> dict[str, Any]:
    collected = list(errors)
    return {
        "collection_status": "PARTIAL_SUCCESS" if collected else "SUCCESS",
        "collection_errors": collected,
    }


def require_products(products: Sequence[Any], errors: Sequence[dict[str, str]]) -> None:
    if products:
        return
    detail = errors[0]["error"] if errors else "no products returned"
    raise RuntimeError(f"Catalog collection produced no usable products: {detail}")
