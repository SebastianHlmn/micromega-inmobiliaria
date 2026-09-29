import json
import re
import unicodedata
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
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

settings = get_settings()

DEFAULT_CATEGORIES = [
    {"name": "Búsqueda inicial", "slug": "busqueda_inicial", "description": "Inicio de una búsqueda de alquiler o venta.", "examples_json": ["Busco un 2 ambientes", "Quiero comprar en Palermo"], "prompt_hint": "Detectar cuando la persona comienza una búsqueda inmobiliaria.", "display_order": 10},
    {"name": "Precio y presupuesto", "slug": "precio_presupuesto", "description": "Preguntas o restricciones sobre precio, presupuesto o valores.", "examples_json": ["Hasta 800 mil", "¿Cuánto sale?", "Algo más barato"], "prompt_hint": "Incluye presupuesto máximo, precio de publicación y negociación de valor.", "display_order": 20},
    {"name": "Expensas", "slug": "expensas", "description": "Consultas sobre expensas.", "examples_json": ["¿Cuánto paga de expensas?"], "prompt_hint": "Sólo consultas vinculadas a expensas.", "display_order": 30},
    {"name": "Mascotas", "slug": "mascotas", "description": "Necesidad o consulta sobre admisión de mascotas.", "examples_json": ["Tengo un perro", "¿Acepta mascotas?"], "prompt_hint": "Detectar tanto requisito de búsqueda como pregunta sobre una propiedad.", "display_order": 40},
    {"name": "Disponibilidad", "slug": "disponibilidad", "description": "Consulta sobre si una propiedad sigue disponible.", "examples_json": ["¿Sigue disponible?", "¿Todavía lo tienen?"], "prompt_hint": "Disponibilidad concreta de una propiedad.", "display_order": 50},
    {"name": "Propiedad específica", "slug": "propiedad_especifica", "description": "Pregunta por una propiedad concreta ya mencionada o identificada.", "examples_json": ["El de Rivadavia", "MM-001", "¿Ese tiene balcón?"], "prompt_hint": "Referencias a una ficha o propiedad concreta.", "display_order": 60},
    {"name": "Visita", "slug": "visita", "description": "Intención de conocer, visitar o coordinar una propiedad.", "examples_json": ["Quiero verlo", "¿Podemos ir el jueves?", "Coordinemos una visita"], "prompt_hint": "Incluye pedido de visita y coordinación.", "display_order": 70},
    {"name": "Garantías y documentación", "slug": "garantias_documentacion", "description": "Consultas sobre requisitos, garantías o documentación.", "examples_json": ["¿Qué garantía piden?", "¿Qué papeles necesito?"], "prompt_hint": "Requisitos documentales o de garantía.", "display_order": 80},
    {"name": "Financiación", "slug": "financiacion", "description": "Consultas sobre financiación o forma de pago.", "examples_json": ["¿Se puede financiar?", "¿Aceptan cuotas?"], "prompt_hint": "Financiación, crédito o esquema de pagos.", "display_order": 90},
    {"name": "Derivación a persona", "slug": "derivacion_humano", "description": "Pedido de hablar con una persona de la inmobiliaria.", "examples_json": ["Quiero hablar con alguien", "Humano"], "prompt_hint": "Pedido explícito de atención humana.", "display_order": 100},
]

DEFAULT_STAGES = [
    ("Nuevo", "nuevo", 10, False),
    ("Calificado", "calificado", 20, False),
    ("Interesado", "interesado", 30, False),
    ("Visita solicitada", "visita_solicitada", 40, False),
    ("Visita concertada", "visita_concertada", 50, False),
    ("Seguimiento", "seguimiento", 60, False),
    ("Cerrado", "cerrado", 70, True),
    ("Descartado", "descartado", 80, True),
]


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


def ensure_management_defaults(db: Session) -> None:
    if not db.scalar(select(Category.id).limit(1)):
        for item in DEFAULT_CATEGORIES:
            db.add(Category(**item))
    if not db.scalar(select(PipelineStage.id).limit(1)):
        for name, slug, order, terminal in DEFAULT_STAGES:
            db.add(PipelineStage(name=name, slug=slug, display_order=order, is_terminal=terminal, active=True))
    db.commit()


def ensure_conversation_state(db: Session, conversation_id: int) -> ConversationState:
    state = db.scalar(select(ConversationState).where(ConversationState.conversation_id == conversation_id))
    if state:
        return state
    default_stage = db.scalar(select(PipelineStage).where(PipelineStage.slug == "nuevo").limit(1))
    state = ConversationState(conversation_id=conversation_id, stage_id=default_stage.id if default_stage else None)
    db.add(state)
    db.flush()
    return state


def set_stage(db: Session, conversation_id: int, stage_slug: str) -> ConversationState:
    state = ensure_conversation_state(db, conversation_id)
    stage = db.scalar(select(PipelineStage).where(PipelineStage.slug == stage_slug, PipelineStage.active.is_(True)))
    if not stage:
        raise ValueError(f"Etapa desconocida: {stage_slug}")
    state.stage_id = stage.id
    state.updated_at = datetime.utcnow()
    return state


def record_event(db: Session, conversation_id: int, event_type: str, *, contact_id: int | None = None, property_id: int | None = None, source: str = "system", metadata: dict | None = None) -> ConversationEvent:
    event = ConversationEvent(conversation_id=conversation_id, contact_id=contact_id, property_id=property_id, event_type=event_type, source=source, metadata_json=metadata)
    db.add(event)
    return event


def _fallback_category_slugs(text: str, categories: list[Category]) -> list[str]:
    lowered = text.lower()
    hits = []
    manual = {
        "busqueda_inicial": ("busco", "quiero alquilar", "quiero comprar"),
        "visita": ("visita", "verlo", "verla", "coordinar", "conocerlo", "conocerla"),
        "mascotas": ("perro", "gato", "mascota"),
        "expensas": ("expensa",),
        "precio_presupuesto": ("precio", "sale", "cuesta", "presupuesto", "barato", "caro", "mil", "usd", "dólar", "dolar"),
        "disponibilidad": ("disponible", "todavía lo tienen", "todavia lo tienen"),
        "derivacion_humano": ("humano", "persona", "asesor", "asesora"),
        "garantias_documentacion": ("garantía", "garantia", "documentación", "documentacion", "papeles", "requisitos"),
        "financiacion": ("financiar", "financiación", "financiacion", "cuotas", "crédito", "credito"),
    }
    active = {c.slug for c in categories}
    for slug, terms in manual.items():
        if slug in active and any(term in lowered for term in terms):
            hits.append(slug)
    return list(dict.fromkeys(hits))


def categorize_message(db: Session, conversation_id: int, text: str) -> list[str]:
    categories = list(db.scalars(select(Category).where(Category.active.is_(True)).order_by(Category.display_order, Category.id)).all())
    if not categories:
        return []

    slugs = []
    if settings.llm_provider == "openai" and settings.openai_api_key:
        taxonomy = [{"slug": c.slug, "name": c.name, "description": c.description, "examples": c.examples_json or [], "hint": c.prompt_hint} for c in categories]
        prompt = (
            "Clasificá el mensaje de un cliente de una inmobiliaria argentina usando exclusivamente las categorías disponibles. "
            "Puede corresponder a cero, una o varias categorías. No inventes categorías. "
            "Devolvé solamente JSON válido con forma {\"categories\":[\"slug1\",\"slug2\"]}.\n\n"
            f"Categorías:\n{json.dumps(taxonomy, ensure_ascii=False)}\n\nMensaje:\n{text}"
        )
        try:
            from openai import OpenAI
            response = OpenAI(api_key=settings.openai_api_key).responses.create(model=settings.openai_model, input=prompt)
            raw = (response.output_text or "").strip()
            parsed = json.loads(raw)
            allowed = {c.slug for c in categories}
            slugs = [slug for slug in parsed.get("categories", []) if isinstance(slug, str) and slug in allowed]
        except Exception:
            slugs = _fallback_category_slugs(text, categories)
    else:
        slugs = _fallback_category_slugs(text, categories)

    by_slug = {c.slug: c for c in categories}
    for slug in dict.fromkeys(slugs):
        category = by_slug[slug]
        existing = db.scalar(select(ConversationCategory).where(ConversationCategory.conversation_id == conversation_id, ConversationCategory.category_id == category.id))
        if not existing:
            db.add(ConversationCategory(conversation_id=conversation_id, category_id=category.id, source="automatic"))
    return list(dict.fromkeys(slugs))


def record_agent_trace(db: Session, conversation: Conversation, contact: Contact, trace: list[dict]) -> None:
    ensure_conversation_state(db, conversation.id)
    for item in trace:
        name = item.get("name")
        args = item.get("arguments") or {}
        result = item.get("result") or {}

        if name == "buscar_propiedades":
            event_type = "search_started" if args.get("replace_profile") else "search_refined"
            record_event(db, conversation.id, event_type, contact_id=contact.id, source="agent", metadata={"criteria": args, "result_count": result.get("count"), "property_codes": [p.get("code") for p in result.get("properties", [])]})
            state = ensure_conversation_state(db, conversation.id)
            if state.stage_id:
                current = db.get(PipelineStage, state.stage_id)
                if current and current.slug == "nuevo":
                    set_stage(db, conversation.id, "calificado")

        elif name == "ver_propiedad":
            prop_data = result.get("property") or {}
            prop = db.scalar(select(Property).where(Property.code == prop_data.get("code"))) if prop_data else None
            record_event(db, conversation.id, "property_question", contact_id=contact.id, property_id=prop.id if prop else None, source="agent", metadata={"query": args.get("query"), "property_code": prop_data.get("code")})

        elif name == "registrar_interes":
            prop_data = result.get("property") or {}
            prop = db.scalar(select(Property).where(Property.code == prop_data.get("code"))) if prop_data else None
            record_event(db, conversation.id, "interest_registered", contact_id=contact.id, property_id=prop.id if prop else None, source="agent", metadata={"property_code": prop_data.get("code")})
            set_stage(db, conversation.id, "interesado")

        elif name == "registrar_visita":
            prop_data = result.get("property") or {}
            prop = db.scalar(select(Property).where(Property.code == prop_data.get("code"))) if prop_data else None
            record_event(db, conversation.id, "visit_requested", contact_id=contact.id, property_id=prop.id if prop else None, source="agent", metadata={"property_code": prop_data.get("code"), "requested_date": args.get("date_text")})
            set_stage(db, conversation.id, "visita_solicitada")

        elif name == "derivar_a_humano":
            record_event(db, conversation.id, "handoff", contact_id=contact.id, source="agent", metadata={"reason": args.get("reason")})


def summarize_conversation(db: Session, conversation_id: int) -> str:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise ValueError("Conversación inexistente")
    contact = db.get(Contact, conversation.contact_id)
    profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == conversation.contact_id))
    messages = list(db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)).all())
    transcript = [{"role": "cliente" if m.direction == "inbound" else "inmobiliaria", "text": m.text or ""} for m in messages[-30:]]
    profile_data = {
        "operation": profile.operation if profile else None,
        "neighborhoods": profile.neighborhoods if profile else None,
        "rooms_min": profile.rooms_min if profile else None,
        "rooms_max": profile.rooms_max if profile else None,
        "budget_max": profile.budget_max if profile else None,
        "currency": profile.currency if profile else None,
        "pets": profile.pets if profile else None,
        "move_date": profile.move_date if profile else None,
    }
    fallback = f"Contacto {(contact.name or contact.phone) if contact else conversation.contact_id}. Búsqueda: {profile_data}. {len(messages)} mensajes registrados."
    summary = fallback
    if settings.llm_provider == "openai" and settings.openai_api_key and transcript:
        try:
            from openai import OpenAI
            response = OpenAI(api_key=settings.openai_api_key).responses.create(
                model=settings.openai_model,
                input=(
                    "Resumí esta conversación inmobiliaria en 2 o 3 frases para un panel interno. "
                    "Indicá qué busca, propiedades mencionadas, preguntas relevantes y próximo paso comercial si surge explícitamente. "
                    "No inventes información.\n\n"
                    f"Perfil estructurado: {json.dumps(profile_data, ensure_ascii=False)}\n"
                    f"Conversación: {json.dumps(transcript, ensure_ascii=False)}"
                ),
            )
            summary = (response.output_text or "").strip() or fallback
        except Exception:
            summary = fallback

    state = ensure_conversation_state(db, conversation_id)
    state.summary = summary
    state.updated_at = datetime.utcnow()
    db.commit()
    return summary


def dashboard_snapshot(db: Session) -> dict:
    total_conversations = db.scalar(select(func.count(Conversation.id))) or 0
    total_contacts = db.scalar(select(func.count(Contact.id))) or 0
    inbound_messages = db.scalar(select(func.count(Message.id)).where(Message.direction == "inbound")) or 0
    total_interests = db.scalar(select(func.count(Interest.id))) or 0
    visit_requests = db.scalar(select(func.count(ConversationEvent.id)).where(ConversationEvent.event_type == "visit_requested")) or 0
    scheduled_visits = db.scalar(select(func.count(Visit.id)).where(Visit.status == "scheduled")) or 0
    handoffs = db.scalar(select(func.count(Conversation.id)).where(Conversation.needs_human.is_(True))) or 0

    category_rows = db.execute(
        select(Category.name, func.count(ConversationCategory.id))
        .join(ConversationCategory, ConversationCategory.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(func.count(ConversationCategory.id).desc())
    ).all()

    neighborhood_counter = Counter()
    for neighborhoods in db.scalars(select(SearchProfile.neighborhoods).where(SearchProfile.neighborhoods.is_not(None))).all():
        for neighborhood in neighborhoods or []:
            neighborhood_counter[neighborhood] += 1

    property_rows = db.execute(
        select(Property.code, Property.address, func.count(Interest.id))
        .join(Interest, Interest.property_id == Property.id)
        .group_by(Property.id, Property.code, Property.address)
        .order_by(func.count(Interest.id).desc())
        .limit(10)
    ).all()

    stage_rows = db.execute(
        select(PipelineStage.name, PipelineStage.slug, func.count(ConversationState.id))
        .outerjoin(ConversationState, ConversationState.stage_id == PipelineStage.id)
        .where(PipelineStage.active.is_(True))
        .group_by(PipelineStage.id, PipelineStage.name, PipelineStage.slug, PipelineStage.display_order)
        .order_by(PipelineStage.display_order)
    ).all()

    return {
        "totals": {
            "conversations": total_conversations,
            "contacts": total_contacts,
            "inbound_messages": inbound_messages,
            "interests": total_interests,
            "visit_requests": visit_requests,
            "scheduled_visits": scheduled_visits,
            "handoffs": handoffs,
        },
        "categories": [{"name": name, "count": count} for name, count in category_rows],
        "neighborhoods": [{"name": name, "count": count} for name, count in neighborhood_counter.most_common(10)],
        "properties": [{"code": code, "address": address, "interests": count} for code, address, count in property_rows],
        "funnel": [{"name": name, "slug": slug, "count": count} for name, slug, count in stage_rows],
    }
