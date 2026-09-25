from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Contact, Conversation, Message, SearchProfile, Interest
from .property_service import search_properties, find_property_by_text
from .llm_service import LLMService
from ..config import get_settings

settings = get_settings()
llm = LLMService()


SEARCH_PROFILE_FIELDS = (
    "operation",
    "neighborhoods",
    "rooms_min",
    "rooms_max",
    "budget_max",
    "currency",
    "pets",
    "move_date",
)


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


def _profile_as_dict(profile: SearchProfile | None) -> dict:
    if not profile:
        return {
            "operation": None,
            "neighborhoods": None,
            "rooms_min": None,
            "rooms_max": None,
            "budget_max": None,
            "currency": None,
            "pets": None,
            "move_date": None,
        }
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


def _profile_has_data(profile: SearchProfile | None) -> bool:
    if not profile:
        return False
    data = _profile_as_dict(profile)
    return any(data.get(key) not in (None, [], "") for key in SEARCH_PROFILE_FIELDS)


def _recent_history(db: Session, conversation_id: int, limit: int = 8) -> list[dict]:
    rows = list(db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all())
    rows.reverse()
    return [
        {
            "role": "cliente" if row.direction == "inbound" else "inmobiliaria",
            "text": row.text or "",
        }
        for row in rows
        if row.text
    ]


def upsert_profile(
    db: Session,
    contact: Contact,
    text: str,
    reset: bool = False,
) -> tuple[SearchProfile, str, dict]:
    profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == contact.id))
    if not profile:
        profile = SearchProfile(contact_id=contact.id)
        db.add(profile)
        db.flush()

    if reset:
        for key in SEARCH_PROFILE_FIELDS:
            setattr(profile, key, None)
        profile.free_text_notes = None

    fields, extraction_source = llm.extract_search_fields(
        text=text,
        current_profile=_profile_as_dict(profile),
    )
    for key, value in fields.items():
        setattr(profile, key, value)

    profile.free_text_notes = ((profile.free_text_notes or "") + "\n" + text).strip()[-4000:]
    profile.updated_at = datetime.utcnow()
    return profile, extraction_source, fields


def _format_property(prop) -> str:
    pet = "admite mascotas" if prop.pets_allowed else "consultar mascotas" if prop.pets_allowed is None else "no admite mascotas"
    exp = f"; expensas aprox. {prop.currency} {prop.expenses:,.0f}" if prop.expenses else ""
    return f"{prop.code}: {prop.rooms} amb. en {prop.neighborhood}, {prop.address}. {prop.currency} {prop.price:,.0f}{exp}; {pet}."


def _property_from_recent_context(db: Session, text: str, history: list[dict]):
    mentioned = find_property_by_text(db, text)
    if mentioned:
        return mentioned
    for item in reversed(history):
        mentioned = find_property_by_text(db, item.get("text", ""))
        if mentioned:
            return mentioned
    return None


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

    # El historial y el perfil se leen antes de incorporar el mensaje actual.
    # Primero entendemos qué está haciendo el cliente; recién después decidimos si buscar.
    history = _recent_history(db, conv.id)
    profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == contact.id))
    profile_before = _profile_as_dict(profile)

    db.add(Message(
        conversation_id=conv.id,
        direction="inbound",
        channel=channel,
        external_id=external_id,
        text=text,
        raw_payload=raw_payload,
    ))

    # Camino principal: un único agente conversacional decide cuándo hablar y cuándo
    # usar herramientas reales. La lógica anterior queda debajo como respaldo si OpenAI falla.
    if agent.available():
        try:
            agent_result = agent.run(
                db=db,
                contact=contact,
                conv=conv,
                text=text,
                current_profile=profile_before,
                history=history,
            )
            reply = agent_result["reply"]
            profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == contact.id))

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
                "intent": {
                    "name": "agent",
                    "source": "openai_tools",
                },
                "profile": _profile_as_dict(profile),
                "extraction": {
                    "source": None,
                    "fields_from_current_message": {},
                },
                "agent": {
                    "response_id": agent_result.get("response_id"),
                    "tools": [
                        item.get("name")
                        for item in agent_result.get("tool_trace", [])
                    ],
                },
            }
        except Exception as exc:
            print(f"[OpenAI agent] fallback to legacy flow: {exc}", flush=True)

    intent, intent_source = llm.classify_intent(
        text=text,
        current_profile=profile_before,
        history=history,
    )
    if settings.human_handoff_keyword.lower() in text.lower():
        intent = "handoff"
        intent_source = "keyword"

    extraction_source = None
    extracted_fields: dict = {}

    if intent == "handoff":
        conv.needs_human = True
        draft = "Te paso con una persona de la inmobiliaria. Ya dejo esta conversación marcada para seguimiento."
        reply = llm.rewrite(draft, context=f"Intención: handoff; cliente: {name or phone}; mensaje: {text}")

    elif intent == "greeting":
        fallback = (
            "¡Hola! ¿Cómo va? Tengo presente la búsqueda que veníamos viendo. "
            "Si querés, seguimos desde ahí o cambiamos lo que necesites."
            if _profile_has_data(profile)
            else "¡Hola! ¿Cómo va? Contame qué estás buscando y vemos opciones."
        )
        reply = llm.conversational_reply(
            text=text,
            guidance=(
                "Respondé al saludo o cortesía de forma natural. No listes propiedades ni hagas una búsqueda. "
                "Si existe una búsqueda previa, podés mencionar brevemente que la tenés presente y ofrecer continuarla."
            ),
            fallback=fallback,
            current_profile=profile_before,
            history=history,
        )

    elif intent == "property_question":
        mentioned = _property_from_recent_context(db, text, history)
        if mentioned:
            existing_interest = db.scalar(
                select(Interest).where(
                    Interest.contact_id == contact.id,
                    Interest.property_id == mentioned.id,
                )
            )
            if not existing_interest:
                db.add(Interest(contact_id=contact.id, property_id=mentioned.id))
            draft = "La propiedad a la que se refiere el cliente es: " + _format_property(mentioned)
            draft += " Respondé únicamente lo que pueda sostenerse con esa ficha y con la pregunta actual."
            reply = llm.rewrite(
                draft,
                context=f"Intención: property_question; cliente: {name or phone}; mensaje: {text}; historial: {history}",
            )
        else:
            reply = llm.conversational_reply(
                text=text,
                guidance=(
                    "El cliente parece preguntar por una propiedad concreta, pero no pudimos identificarla con seguridad. "
                    "Pedile una referencia breve (código, calle o cuál de las opciones) sin inventar información."
                ),
                fallback="¿A cuál de las propiedades te referís? Si me decís el código o la calle, te digo lo que figura en la ficha.",
                current_profile=profile_before,
                history=history,
            )

    elif intent in {"new_search", "refine_search"}:
        profile, extraction_source, extracted_fields = upsert_profile(
            db=db,
            contact=contact,
            text=text,
            reset=(intent == "new_search"),
        )
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
            if mentioned.pets_allowed is True and profile.pets is True:
                draft += " En la ficha figura que admite mascotas."
            draft += " Si querés, busco alternativas compatibles con lo que estás buscando."
        else:
            matches = search_properties(db, profile, limit=3)
            if matches:
                lines = "\n".join(f"• {_format_property(p)}" for p in matches)
                draft = "Con esos criterios, encontré estas opciones disponibles:\n" + lines
            else:
                draft = (
                    "Actualicé lo que estás buscando, pero no encontré una coincidencia clara en la base demo. "
                    "Pedí sólo el dato que realmente falte o sugerí cambiar algún criterio, sin inventar propiedades."
                )
        reply = llm.rewrite(
            draft,
            context=(
                f"Intención: {intent}; cliente: {name or phone}; mensaje: {text}; "
                f"perfil actualizado: {_profile_as_dict(profile)}"
            ),
        )

    else:  # general_question
        reply = llm.conversational_reply(
            text=text,
            guidance=(
                "Respondé a la consulta o comentario de manera conversacional usando sólo el contexto disponible. "
                "No listes propiedades ni ejecutes una búsqueda salvo que el cliente lo pida explícitamente. "
                "Si la consulta requiere un dato que no está disponible, decilo y pedí la aclaración mínima."
            ),
            fallback="Te leo. Si querés, seguimos con la búsqueda o decime qué necesitás saber.",
            current_profile=profile_before,
            history=history,
        )

    # Puede haberse creado o actualizado recién en una rama de búsqueda.
    profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == contact.id))

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
        "intent": {
            "name": intent,
            "source": intent_source,
        },
        "profile": _profile_as_dict(profile),
        "extraction": {
            "source": extraction_source,
            "fields_from_current_message": extracted_fields,
        },
    }
