from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Category,
    Contact,
    Conversation,
    ConversationCategory,
    ConversationEvent,
    ConversationState,
    Interest,
    Message,
    PipelineStage,
    Property,
    SearchProfile,
    Visit,
)
from ..services.management_service import (
    dashboard_snapshot,
    ensure_conversation_state,
    ensure_management_defaults,
    record_event,
    set_stage,
    slugify,
    summarize_conversation,
)

router = APIRouter(prefix="/api/management", tags=["management"])


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    examples: list[str] = []
    prompt_hint: str | None = None
    active: bool = True
    display_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    examples: list[str] | None = None
    prompt_hint: str | None = None
    active: bool | None = None
    display_order: int | None = None


class StageUpdate(BaseModel):
    stage_slug: str


class NoteUpdate(BaseModel):
    owner_notes: str | None = None


class VisitUpdate(BaseModel):
    status: str
    visit_date: str | None = None
    notes: str | None = None


def _profile_dict(profile: SearchProfile | None) -> dict:
    if not profile:
        return {}
    return {
        "operation": profile.operation,
        "neighborhoods": profile.neighborhoods,
        "rooms_min": profile.rooms_min,
        "rooms_max": profile.rooms_max,
        "budget_max": profile.budget_max,
        "currency": profile.currency,
        "pets": profile.pets,
        "move_date": profile.move_date,
    }


def _stage_dict(db: Session, state: ConversationState | None) -> dict | None:
    if not state or not state.stage_id:
        return None
    stage = db.get(PipelineStage, state.stage_id)
    if not stage:
        return None
    return {"id": stage.id, "name": stage.name, "slug": stage.slug}


def _conversation_categories(db: Session, conversation_id: int) -> list[dict]:
    rows = db.execute(
        select(Category, ConversationCategory)
        .join(ConversationCategory, ConversationCategory.category_id == Category.id)
        .where(ConversationCategory.conversation_id == conversation_id)
        .order_by(Category.display_order, Category.name)
    ).all()
    return [
        {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "source": link.source,
        }
        for category, link in rows
    ]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    ensure_management_defaults(db)
    return dashboard_snapshot(db)


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    ensure_management_defaults(db)
    rows = list(db.scalars(select(Category).order_by(Category.display_order, Category.id)).all())
    return [
        {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "examples": row.examples_json or [],
            "prompt_hint": row.prompt_hint,
            "active": row.active,
            "display_order": row.display_order,
        }
        for row in rows
    ]


@router.post("/categories")
def create_category(req: CategoryCreate, db: Session = Depends(get_db)):
    slug = slugify(req.name)
    if db.scalar(select(Category).where(Category.slug == slug)):
        raise HTTPException(409, "Ya existe una categoría con ese nombre.")
    row = Category(
        name=req.name.strip(),
        slug=slug,
        description=req.description,
        examples_json=req.examples,
        prompt_hint=req.prompt_hint,
        active=req.active,
        display_order=req.display_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "slug": row.slug}


@router.patch("/categories/{category_id}")
def update_category(category_id: int, req: CategoryUpdate, db: Session = Depends(get_db)):
    row = db.get(Category, category_id)
    if not row:
        raise HTTPException(404, "Categoría inexistente.")
    data = req.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        row.name = data["name"].strip()
    if "description" in data:
        row.description = data["description"]
    if "examples" in data:
        row.examples_json = data["examples"]
    if "prompt_hint" in data:
        row.prompt_hint = data["prompt_hint"]
    if "active" in data:
        row.active = data["active"]
    if "display_order" in data:
        row.display_order = data["display_order"]
    db.commit()
    return {"ok": True}


@router.get("/stages")
def list_stages(db: Session = Depends(get_db)):
    ensure_management_defaults(db)
    rows = list(db.scalars(
        select(PipelineStage)
        .where(PipelineStage.active.is_(True))
        .order_by(PipelineStage.display_order, PipelineStage.id)
    ).all())
    return [
        {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "display_order": row.display_order,
            "is_terminal": row.is_terminal,
        }
        for row in rows
    ]


@router.get("/conversations")
def list_conversations(limit: int = 100, db: Session = Depends(get_db)):
    ensure_management_defaults(db)
    conversations = list(db.scalars(
        select(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(min(max(limit, 1), 500))
    ).all())

    result = []
    for conv in conversations:
        contact = db.get(Contact, conv.contact_id)
        state = ensure_conversation_state(db, conv.id)
        profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == conv.contact_id))
        last_message = db.scalar(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .limit(1)
        )
        message_count = db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        ) or 0
        result.append({
            "id": conv.id,
            "status": conv.status,
            "needs_human": conv.needs_human,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "contact": {
                "id": contact.id if contact else None,
                "name": contact.name if contact else None,
                "phone": contact.phone if contact else None,
            },
            "stage": _stage_dict(db, state),
            "summary": state.summary,
            "profile": _profile_dict(profile),
            "categories": _conversation_categories(db, conv.id),
            "last_message": last_message.text if last_message else None,
            "last_message_at": last_message.created_at.isoformat() if last_message else None,
            "message_count": message_count,
        })
    db.commit()
    return result


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: int, db: Session = Depends(get_db)):
    ensure_management_defaults(db)
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversación inexistente.")
    contact = db.get(Contact, conv.contact_id)
    state = ensure_conversation_state(db, conv.id)
    profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == conv.contact_id))

    messages = list(db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id)
    ).all())
    events = list(db.scalars(
        select(ConversationEvent)
        .where(ConversationEvent.conversation_id == conv.id)
        .order_by(ConversationEvent.id)
    ).all())
    interests = db.execute(
        select(Interest, Property)
        .join(Property, Property.id == Interest.property_id)
        .where(Interest.contact_id == conv.contact_id)
        .order_by(Interest.id.desc())
    ).all()
    visits = db.execute(
        select(Visit, Property)
        .join(Property, Property.id == Visit.property_id)
        .where(Visit.contact_id == conv.contact_id)
        .order_by(Visit.id.desc())
    ).all()

    db.commit()
    return {
        "id": conv.id,
        "status": conv.status,
        "needs_human": conv.needs_human,
        "contact": {
            "id": contact.id if contact else None,
            "name": contact.name if contact else None,
            "phone": contact.phone if contact else None,
        },
        "stage": _stage_dict(db, state),
        "summary": state.summary,
        "owner_notes": state.owner_notes,
        "profile": _profile_dict(profile),
        "categories": _conversation_categories(db, conv.id),
        "messages": [
            {
                "id": m.id,
                "direction": m.direction,
                "channel": m.channel,
                "text": m.text,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "source": e.source,
                "metadata": e.metadata_json,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "interests": [
            {
                "id": interest.id,
                "status": interest.status,
                "property": {
                    "id": prop.id,
                    "code": prop.code,
                    "address": prop.address,
                    "neighborhood": prop.neighborhood,
                },
                "created_at": interest.created_at.isoformat(),
            }
            for interest, prop in interests
        ],
        "visits": [
            {
                "id": visit.id,
                "status": visit.status,
                "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
                "notes": visit.notes,
                "property": {
                    "id": prop.id,
                    "code": prop.code,
                    "address": prop.address,
                },
                "created_at": visit.created_at.isoformat(),
            }
            for visit, prop in visits
        ],
    }


@router.post("/conversations/{conversation_id}/summary")
def generate_summary(conversation_id: int, db: Session = Depends(get_db)):
    try:
        summary = summarize_conversation(db, conversation_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"summary": summary}


@router.patch("/conversations/{conversation_id}/stage")
def update_stage(conversation_id: int, req: StageUpdate, db: Session = Depends(get_db)):
    if not db.get(Conversation, conversation_id):
        raise HTTPException(404, "Conversación inexistente.")
    try:
        state = set_stage(db, conversation_id, req.stage_slug)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    record_event(db, conversation_id, "stage_changed", source="manual", metadata={"stage": req.stage_slug})
    db.commit()
    return {"ok": True, "stage": _stage_dict(db, state)}


@router.patch("/conversations/{conversation_id}/notes")
def update_notes(conversation_id: int, req: NoteUpdate, db: Session = Depends(get_db)):
    if not db.get(Conversation, conversation_id):
        raise HTTPException(404, "Conversación inexistente.")
    state = ensure_conversation_state(db, conversation_id)
    state.owner_notes = req.owner_notes
    state.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/visits")
def list_visits(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Visit, Contact, Property)
        .join(Contact, Contact.id == Visit.contact_id)
        .join(Property, Property.id == Visit.property_id)
        .order_by(Visit.id.desc())
    ).all()
    return [
        {
            "id": visit.id,
            "status": visit.status,
            "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
            "notes": visit.notes,
            "contact": {"id": contact.id, "name": contact.name, "phone": contact.phone},
            "property": {"id": prop.id, "code": prop.code, "address": prop.address},
        }
        for visit, contact, prop in rows
    ]


@router.patch("/visits/{visit_id}")
def update_visit(visit_id: int, req: VisitUpdate, db: Session = Depends(get_db)):
    visit = db.get(Visit, visit_id)
    if not visit:
        raise HTTPException(404, "Visita inexistente.")
    allowed = {"requested", "proposed", "scheduled", "completed", "cancelled"}
    if req.status not in allowed:
        raise HTTPException(400, "Estado de visita inválido.")
    visit.status = req.status
    if req.visit_date:
        try:
            visit.visit_date = datetime.strptime(req.visit_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "visit_date debe tener formato YYYY-MM-DD.")
    if req.notes is not None:
        visit.notes = req.notes

    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.contact_id == visit.contact_id)
        .order_by(Conversation.id.desc())
        .limit(1)
    )
    if conversation:
        if req.status == "scheduled":
            set_stage(db, conversation.id, "visita_concertada")
            record_event(db, conversation.id, "visit_scheduled", contact_id=visit.contact_id, property_id=visit.property_id, source="manual")
        elif req.status == "completed":
            set_stage(db, conversation.id, "seguimiento")
            record_event(db, conversation.id, "visit_completed", contact_id=visit.contact_id, property_id=visit.property_id, source="manual")
    db.commit()
    return {"ok": True}
