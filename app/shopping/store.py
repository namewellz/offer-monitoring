"""Shopping list store (manual builder on top of comparable price rows)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models_v2 import ShoppingList, ShoppingListItem


def _qty(value: Any) -> Decimal:
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError):
        qty = Decimal("1")
    return qty if qty and qty > 0 else Decimal("1")


def create_list(db: Session, name: str) -> ShoppingList:
    obj = ShoppingList(name=(name or "Nova lista").strip()[:160])
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_list(db: Session, list_id: int) -> None:
    db.execute(delete(ShoppingListItem).where(ShoppingListItem.list_id == list_id))
    db.execute(delete(ShoppingList).where(ShoppingList.id == list_id))
    db.commit()


def get_list(db: Session, list_id: int) -> ShoppingList | None:
    return db.get(ShoppingList, list_id)


def list_lists(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ShoppingList).order_by(ShoppingList.created_at.desc())
    ).scalars().all()
    out = []
    for row in rows:
        count = db.execute(
            select(ShoppingListItem.id).where(ShoppingListItem.list_id == row.id)
        ).scalars().all()
        out.append({"id": row.id, "name": row.name, "item_count": len(count)})
    return out


def add_item(
    db: Session,
    list_id: int,
    department: str,
    category: str,
    form: str,
    retailer: str | None = None,
    qty: Any = 1,
) -> dict[str, Any]:
    existing = db.execute(
        select(ShoppingListItem).where(
            ShoppingListItem.list_id == list_id,
            ShoppingListItem.department == department,
            ShoppingListItem.category == category,
            ShoppingListItem.form == form,
        )
    ).scalar_one_or_none()
    if existing is None:
        obj = ShoppingListItem(
            list_id=list_id,
            department=department,
            category=category,
            form=form,
            retailer_slug=retailer,
            qty=_qty(qty),
        )
        db.add(obj)
    else:
        obj = existing
        if retailer:
            obj.retailer_slug = retailer
        obj.qty = _qty(qty)
    db.commit()
    db.refresh(obj)
    return {
        "id": obj.id,
        "department": obj.department,
        "category": obj.category,
        "form": obj.form,
        "retailer": obj.retailer_slug,
        "qty": float(obj.qty),
    }


def update_item(
    db: Session,
    item_id: int,
    retailer: str | None = None,
    qty: Any = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    obj = db.get(ShoppingListItem, item_id)
    if obj is None:
        return None
    if retailer:
        obj.retailer_slug = retailer
    if qty is not None:
        obj.qty = _qty(qty)
    if note is not None:
        obj.note = note or None
    db.commit()
    db.refresh(obj)
    return {
        "id": obj.id,
        "department": obj.department,
        "category": obj.category,
        "form": obj.form,
        "retailer": obj.retailer_slug,
        "qty": float(obj.qty),
        "note": obj.note,
    }


def remove_item(db: Session, item_id: int) -> None:
    db.execute(delete(ShoppingListItem).where(ShoppingListItem.id == item_id))
    db.commit()


def items(db: Session, list_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ShoppingListItem)
        .where(ShoppingListItem.list_id == list_id)
        .order_by(ShoppingListItem.department, ShoppingListItem.category, ShoppingListItem.form)
    ).scalars().all()
    return [
        {
            "id": row.id,
            "department": row.department,
            "category": row.category,
            "form": row.form,
            "retailer": row.retailer_slug,
            "qty": float(row.qty),
            "note": row.note,
        }
        for row in rows
    ]
