from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..services.conversation_service import handle_message
from ..services.whatsapp_service import extract_incoming_messages, send_text_message, verify_meta_signature

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])
settings = get_settings()


@router.get("")
def verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("")
async def receive(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="Invalid Meta signature")
    payload = await request.json()
    messages = extract_incoming_messages(payload)
    processed = 0
    for item in messages:
        result = handle_message(
            db=db,
            phone=item["phone"],
            name=item.get("name"),
            text=item["text"],
            channel="whatsapp",
            external_id=item.get("external_id"),
            raw_payload=payload,
        )
        if result.get("reply") and settings.auto_reply_enabled:
            send_text_message(item["phone"], result["reply"])
        processed += 1
    return {"ok": True, "processed": processed}
