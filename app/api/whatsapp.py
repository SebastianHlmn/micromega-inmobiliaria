from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..services.conversation_service import handle_message
from ..services.whatsapp_service import extract_incoming_messages, send_text_message, verify_meta_signature

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])
settings = get_settings()


def _last4(value: str | None) -> str:
    if not value:
        return "?"
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def _extract_statuses(payload: dict) -> list[dict]:
    statuses: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []) or []:
                statuses.append(status)
    return statuses


def _meta_result_summary(meta_result: object) -> str:
    """Resume la respuesta de Meta sin imprimir tokens ni números completos."""
    if not isinstance(meta_result, dict):
        return f"type={type(meta_result).__name__}"

    keys = ",".join(sorted(str(k) for k in meta_result.keys()))
    parts = [f"keys={keys}"]

    contacts = meta_result.get("contacts") or []
    if contacts and isinstance(contacts[0], dict):
        first = contacts[0]
        parts.append(f"contact_input={_last4(first.get('input'))}")
        parts.append(f"contact_wa_id={_last4(first.get('wa_id'))}")

    messages = meta_result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        parts.append(f"message_id={messages[0].get('id')}")

    if "success" in meta_result:
        parts.append(f"success={meta_result.get('success')}")

    return " ".join(parts)


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

    # Los estados llegan en webhooks separados del mensaje entrante.
    # Los mostramos sin datos sensibles para poder diagnosticar entrega real.
    for status in _extract_statuses(payload):
        errors = status.get("errors") or []
        error_text = ""
        if errors:
            first = errors[0] if isinstance(errors[0], dict) else {}
            error_text = (
                f" error_code={first.get('code')}"
                f" error_title={first.get('title')}"
                f" error_message={first.get('message')}"
            )
        print(
            "[WhatsApp status]"
            f" status={status.get('status')}"
            f" recipient={_last4(status.get('recipient_id'))}"
            f" message_id={status.get('id')}"
            f"{error_text}",
            flush=True,
        )

    messages = extract_incoming_messages(payload)
    processed = 0
    replies_accepted = 0
    reply_errors = 0

    for item in messages:
        print(
            "[WhatsApp inbound]"
            f" from={_last4(item.get('phone'))}"
            f" text={item.get('text', '')[:120]!r}",
            flush=True,
        )

        result = handle_message(
            db=db,
            phone=item["phone"],
            name=item.get("name"),
            text=item["text"],
            channel="whatsapp",
            external_id=item.get("external_id"),
            raw_payload=payload,
        )

        reply = result.get("reply")
        if reply and settings.auto_reply_enabled:
            try:
                meta_result = send_text_message(item["phone"], reply)
                replies_accepted += 1
                print(
                    "[WhatsApp outbound]"
                    f" accepted=True to={_last4(item.get('phone'))}"
                    f" {_meta_result_summary(meta_result)}",
                    flush=True,
                )
            except Exception as exc:
                reply_errors += 1
                print(
                    "[WhatsApp outbound]"
                    f" accepted=False to={_last4(item.get('phone'))}"
                    f" error={exc}",
                    flush=True,
                )
        elif not reply:
            print("[WhatsApp outbound] skipped: motor sin reply", flush=True)
        elif not settings.auto_reply_enabled:
            print("[WhatsApp outbound] skipped: AUTO_REPLY_ENABLED=false", flush=True)

        processed += 1

    # Respondemos 200 aunque falle la salida, para evitar que Meta reintente el mensaje entrante.
    return {
        "ok": True,
        "processed": processed,
        "replies_accepted": replies_accepted,
        "reply_errors": reply_errors,
    }
