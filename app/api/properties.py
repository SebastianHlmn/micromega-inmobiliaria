from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Property
from ..schemas import PropertyCreate

router = APIRouter(prefix="/api/properties", tags=["properties"])


@router.get("")
def list_properties(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Property).order_by(Property.id)).all())
    return [
        {
            "id": p.id,
            "code": p.code,
            "operation": p.operation,
            "neighborhood": p.neighborhood,
            "address": p.address,
            "rooms": p.rooms,
            "price": p.price,
            "currency": p.currency,
            "expenses": p.expenses,
            "pets_allowed": p.pets_allowed,
            "available": p.available,
        }
        for p in rows
    ]


@router.post("")
def create_property(req: PropertyCreate, db: Session = Depends(get_db)):
    prop = Property(**req.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return {"id": prop.id, "code": prop.code}
