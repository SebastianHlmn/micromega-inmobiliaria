import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Property, SearchProfile


def search_properties(db: Session, profile: SearchProfile | None, limit: int = 5):
    stmt = select(Property).where(Property.available.is_(True))
    if profile:
        if profile.operation:
            stmt = stmt.where(Property.operation == profile.operation)
        if profile.neighborhoods:
            stmt = stmt.where(Property.neighborhood.in_(profile.neighborhoods))
        if profile.rooms_min:
            stmt = stmt.where(Property.rooms >= profile.rooms_min)
        if profile.rooms_max:
            stmt = stmt.where(Property.rooms <= profile.rooms_max)
        if profile.budget_max:
            stmt = stmt.where(Property.price <= profile.budget_max)
        if profile.currency:
            stmt = stmt.where(Property.currency == profile.currency)
        if profile.pets is True:
            stmt = stmt.where(Property.pets_allowed.is_(True))
    return list(db.scalars(stmt.limit(limit)).all())


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-záéíóúüñ0-9]+", (value or "").lower())
        if len(token) >= 4
    }


def find_property_by_text(db: Session, text: str):
    lowered = (text or "").lower()
    query_tokens = _tokens(lowered)
    props = list(db.scalars(select(Property).where(Property.available.is_(True))).all())

    for prop in props:
        if prop.code.lower() in lowered:
            return prop
        if prop.address.lower() in lowered:
            return prop

        address_tokens = _tokens(prop.address)
        if query_tokens and address_tokens.intersection(query_tokens):
            return prop

    return None
