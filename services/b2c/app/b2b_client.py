from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Product, SKU


@dataclass
class ReserveFailure:
    sku_id: str
    requested: int
    reason: str
    available: int | None = None


@dataclass
class B2BClient:
    """Local/fake B2B client used by B2C for catalog enrichment and inventory.

    Tests can replace the app dependency with a subclass that forces reserve/unreserve
    failures or returns custom enrichment payloads.
    """

    unavailable: bool = False
    force_reserve_failures: list[ReserveFailure] = field(default_factory=list)
    force_unreserve_fail: bool = False
    reservations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def raise_if_unavailable(self) -> None:
        if self.unavailable:
            # US-ORD-01 DoD: 503; US-CAT-01 also accepts 502/503.
            raise HTTPException(
                status_code=503,
                detail={"code": "B2B_UNAVAILABLE", "message": "B2B service unavailable"},
            )

    def enrich_skus(self, db: Session, sku_ids: list[str]) -> dict[str, dict[str, Any]]:
        self.raise_if_unavailable()
        if not sku_ids:
            return {}
        rows = db.scalars(
            select(SKU)
            .where(SKU.id.in_(sku_ids))
            .options(
                selectinload(SKU.images),
                selectinload(SKU.characteristics),
                selectinload(SKU.product).selectinload(Product.images),
            )
        ).all()
        result: dict[str, dict[str, Any]] = {}
        for sku in rows:
            product = sku.product
            image = None
            if sku.images:
                image = {
                    "id": sku.images[0].id,
                    "url": sku.images[0].url,
                    "alt": sku.images[0].alt,
                    "ordering": sku.images[0].ordering,
                    "is_main": sku.images[0].is_main,
                }
            elif product.images:
                image = {
                    "id": product.images[0].id,
                    "url": product.images[0].url,
                    "alt": product.images[0].alt,
                    "ordering": product.images[0].ordering,
                    "is_main": product.images[0].is_main,
                }
            result[sku.id] = {
                "sku_id": sku.id,
                "sku_name": sku.name,
                "sku_code": sku.sku_code or sku.id,
                "price": sku.price,
                "active_quantity": sku.active_quantity,
                "product_id": product.id,
                "product_title": product.title,
                "product_status": product.status,
                "product_deleted": product.deleted,
                "image": image,
            }
        return result

    def get_product(self, db: Session, product_id: str) -> Product | None:
        self.raise_if_unavailable()
        return db.scalar(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.images),
                selectinload(Product.characteristics),
                selectinload(Product.category),
                selectinload(Product.skus).selectinload(SKU.images),
                selectinload(Product.skus).selectinload(SKU.characteristics),
            )
        )

    def reserve(
        self,
        db: Session,
        *,
        order_id: str,
        idempotency_key: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.raise_if_unavailable()
        if self.force_reserve_failures:
            return {
                "reserved": False,
                "failed_items": [
                    {
                        "sku_id": f.sku_id,
                        "requested": f.requested,
                        "reason": f.reason,
                        **({"available": f.available} if f.available is not None else {}),
                    }
                    for f in self.force_reserve_failures
                ],
            }

        failed: list[dict[str, Any]] = []
        loaded: list[tuple[SKU, int]] = []
        for item in items:
            sku_id = str(item["sku_id"])
            qty = int(item["quantity"])
            sku = db.get(SKU, sku_id)
            if not sku or sku.deleted:
                failed.append({"sku_id": sku_id, "requested": qty, "reason": "SKU_NOT_FOUND", "available": 0})
                continue
            product = db.get(Product, sku.product_id)
            if not product or product.deleted:
                failed.append({"sku_id": sku_id, "requested": qty, "reason": "PRODUCT_DELETED", "available": 0})
                continue
            if product.status in {"BLOCKED", "HARD_BLOCKED"}:
                failed.append({"sku_id": sku_id, "requested": qty, "reason": "PRODUCT_BLOCKED", "available": 0})
                continue
            if sku.active_quantity < qty:
                reason = "OUT_OF_STOCK" if sku.active_quantity <= 0 else "INSUFFICIENT_STOCK"
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "reason": reason,
                        "available": sku.active_quantity,
                    }
                )
                continue
            loaded.append((sku, qty))

        if failed:
            return {"reserved": False, "failed_items": failed}

        reserved_items = []
        for sku, qty in loaded:
            sku.active_quantity -= qty
            sku.reserved_quantity += qty
            reserved_items.append(
                {
                    "sku_id": sku.id,
                    "reserved_quantity": qty,
                    "remaining_stock": sku.active_quantity,
                }
            )
        db.flush()
        self.reservations[order_id] = [{"sku_id": s.id, "quantity": q} for s, q in loaded]
        return {"reserved": True, "items": reserved_items, "idempotency_key": idempotency_key}

    def unreserve(self, db: Session, *, order_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        self.raise_if_unavailable()
        if self.force_unreserve_fail:
            raise HTTPException(
                status_code=503,
                detail={"code": "B2B_UNAVAILABLE", "message": "Unreserve failed"},
            )
        for item in items:
            sku = db.get(SKU, str(item["sku_id"]))
            if not sku:
                continue
            qty = int(item["quantity"])
            sku.reserved_quantity = max(0, sku.reserved_quantity - qty)
            sku.active_quantity += qty
        db.flush()
        self.reservations.pop(order_id, None)
        return {"unreserved": True, "order_id": order_id}


_default_client = B2BClient()


def get_b2b_client() -> B2BClient:
    return _default_client


def set_b2b_client(client: B2BClient) -> None:
    global _default_client
    _default_client = client
