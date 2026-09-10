from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Contact, Conversation, Message, SearchProfile

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/leads")
def leads(db: Session = Depends(get_db)):
    contacts = list(db.scalars(select(Contact).order_by(Contact.id.desc())).all())
    result = []
    for c in contacts:
        profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == c.id))
        conv = db.scalar(select(Conversation).where(Conversation.contact_id == c.id).order_by(Conversation.id.desc()))
        result.append({
            "id": c.id,
            "phone": c.phone,
            "name": c.name,
            "needs_human": bool(conv.needs_human) if conv else False,
            "profile": {
                "operation": profile.operation if profile else None,
                "neighborhoods": profile.neighborhoods if profile else None,
                "rooms_min": profile.rooms_min if profile else None,
                "rooms_max": profile.rooms_max if profile else None,
                "budget_max": profile.budget_max if profile else None,
                "currency": profile.currency if profile else None,
                "pets": profile.pets if profile else None,
                "move_date": profile.move_date if profile else None,
            }
        })
    return result


@router.get("/conversation/{conversation_id}")
def conversation(conversation_id: int, db: Session = Depends(get_db)):
    rows = list(db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id)
    ).all())
    return [{
        "id": m.id,
        "direction": m.direction,
        "channel": m.channel,
        "text": m.text,
        "created_at": m.created_at,
    } for m in rows]
