from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Contact, Conversation, Message, SearchProfile
from ..services.conversation_service import handle_message
from ..services.whatsapp_service import send_text_message

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


class WhatsAppTestChatIn(BaseModel):
    phone: str
    text: str
    name: str | None = None


def _normalize_whatsapp_phone(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


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


@router.get("/whatsapp/status")
def whatsapp_status():
    """Estado de configuración sin exponer credenciales."""
    return {
        "app_env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "openai_model": settings.openai_model,
        "openai_configured": bool(settings.openai_api_key),
        "whatsapp_access_token_configured": bool(settings.whatsapp_access_token),
        "whatsapp_phone_number_id_configured": bool(settings.whatsapp_phone_number_id),
        "whatsapp_graph_api_version": settings.whatsapp_graph_api_version,
        "auto_reply_enabled": settings.auto_reply_enabled,
    }


@router.post("/whatsapp/test-chat")
def whatsapp_test_chat(payload: WhatsAppTestChatIn, db: Session = Depends(get_db)):
    """Puente de desarrollo: procesa un mensaje con el motor y envía la respuesta por WhatsApp.

    Permite validar GPT + motor conversacional + salida de WhatsApp aunque Meta todavía
    no entregue mensajes reales al webhook de una app sin publicar.
    """
    if settings.app_env != "dev":
        raise HTTPException(status_code=403, detail="Disponible únicamente en APP_ENV=dev")
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Faltan WHATSAPP_ACCESS_TOKEN o WHATSAPP_PHONE_NUMBER_ID en .env",
        )

    phone = _normalize_whatsapp_phone(payload.phone)
    if len(phone) < 8:
        raise HTTPException(status_code=400, detail="Número de WhatsApp inválido")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El mensaje está vacío")

    result = handle_message(
        db=db,
        phone=phone,
        name=payload.name,
        text=text,
        channel="whatsapp-test",
    )
    reply = result.get("reply")
    if not reply:
        raise HTTPException(status_code=500, detail="El motor no generó una respuesta")

    try:
        meta_result = send_text_message(phone, reply)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Meta rechazó el envío: {exc}") from exc

    return {
        "sent": True,
        "phone": phone,
        "reply": reply,
        "conversation_id": result.get("conversation_id"),
        "profile": result.get("profile"),
        "extraction": result.get("extraction"),
        "meta": meta_result,
    }
