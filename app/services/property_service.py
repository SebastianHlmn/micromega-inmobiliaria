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
        if profile.pets is True:
            stmt = stmt.where(Property.pets_allowed.is_(True))
    return list(db.scalars(stmt.limit(limit)).all())


def find_property_by_text(db: Session, text: str):
    lowered = text.lower()
    props = list(db.scalars(select(Property).where(Property.available.is_(True))).all())
    for prop in props:
        if prop.code.lower() in lowered:
            return prop
        if prop.address.lower() in lowered:
            return prop
        street_token = prop.address.split()[0].lower()
        if len(street_token) > 4 and street_token in lowered:
            return prop
    return None
