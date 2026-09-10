from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Contact, Conversation, Message, SearchProfile, Interest
from .extraction_service import extract_search_fields
from .property_service import search_properties, find_property_by_text
from .llm_service import LLMService
from ..config import get_settings

settings = get_settings()
llm = LLMService()


def get_or_create_contact(db: Session, phone: str, name: str | None = None) -> Contact:
    contact = db.scalar(select(Contact).where(Contact.phone == phone))
    if not contact:
        contact = Contact(phone=phone, name=name)
        db.add(contact)
        db.flush()
    elif name and not contact.name:
        contact.name = name
    return contact


def get_or_create_conversation(db: Session, contact: Contact) -> Conversation:
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.contact_id == contact.id, Conversation.status == "open")
        .order_by(Conversation.id.desc())
    )
    if not conv:
        conv = Conversation(contact_id=contact.id)
        db.add(conv)
        db.flush()
    return conv


def upsert_profile(db: Session, contact: Contact, text: str) -> SearchProfile:
    profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == contact.id))
    if not profile:
        profile = SearchProfile(contact_id=contact.id)
        db.add(profile)
        db.flush()

    fields = extract_search_fields(text)
    for key, value in fields.items():
        setattr(profile, key, value)
    profile.free_text_notes = ((profile.free_text_notes or "") + "\n" + text).strip()[-4000:]
    profile.updated_at = datetime.utcnow()
    return profile


def _format_property(prop) -> str:
    pet = "admite mascotas" if prop.pets_allowed else "consultar mascotas" if prop.pets_allowed is None else "no admite mascotas"
    exp = f"; expensas aprox. {prop.currency} {prop.expenses:,.0f}" if prop.expenses else ""
    return f"{prop.code}: {prop.rooms} amb. en {prop.neighborhood}, {prop.address}. {prop.currency} {prop.price:,.0f}{exp}; {pet}."


def handle_message(
    db: Session,
    phone: str,
    text: str,
    name: str | None = None,
    channel: str = "simulator",
    external_id: str | None = None,
    raw_payload: dict | None = None,
):
    contact = get_or_create_contact(db, phone, name)
    conv = get_or_create_conversation(db, contact)

    if external_id:
        existing = db.scalar(select(Message).where(Message.external_id == external_id))
        if existing:
            return {"duplicate": True, "reply": None, "conversation_id": conv.id}

    db.add(Message(
        conversation_id=conv.id,
        direction="inbound",
        channel=channel,
        external_id=external_id,
        text=text,
        raw_payload=raw_payload,
    ))

    profile = upsert_profile(db, contact, text)

    if settings.human_handoff_keyword.lower() in text.lower():
        conv.needs_human = True
        draft = "Te paso con una persona de la inmobiliaria. Ya dejo esta conversación marcada para seguimiento."
    else:
        mentioned = find_property_by_text(db, text)
        if mentioned:
            existing_interest = db.scalar(
                select(Interest).where(
                    Interest.contact_id == contact.id,
                    Interest.property_id == mentioned.id,
                )
            )
            if not existing_interest:
                db.add(Interest(contact_id=contact.id, property_id=mentioned.id))
            draft = "Sí, tengo esta propiedad registrada: " + _format_property(mentioned)
            if mentioned.pets_allowed is True and any(k in text.lower() for k in ["perro", "gato", "mascota"]):
                draft += " En la ficha figura que admite mascotas."
            draft += " Si querés, busco alternativas compatibles con lo que estás buscando."
        else:
            matches = search_properties(db, profile, limit=3)
            if matches:
                lines = "\n".join(f"• {_format_property(p)}" for p in matches)
                draft = "Con lo que me contaste, encontré estas opciones disponibles:\n" + lines
            else:
                draft = (
                    "Registré lo que estás buscando, pero no encontré una coincidencia clara en la base demo. "
                    "Podés decirme zona, cantidad de ambientes, presupuesto y si necesitás que admita mascotas."
                )

    reply = llm.rewrite(draft, context=f"Cliente: {name or phone}; mensaje: {text}")
    db.add(Message(
        conversation_id=conv.id,
        direction="outbound",
        channel=channel,
        text=reply,
    ))
    db.commit()
    return {
        "duplicate": False,
        "reply": reply,
        "conversation_id": conv.id,
        "contact_id": contact.id,
        "profile": {
            "operation": profile.operation,
            "neighborhoods": profile.neighborhoods,
            "rooms_min": profile.rooms_min,
            "rooms_max": profile.rooms_max,
            "budget_max": profile.budget_max,
            "currency": profile.currency,
            "pets": profile.pets,
            "move_date": profile.move_date,
        },
    }
