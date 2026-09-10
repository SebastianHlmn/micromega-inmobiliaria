import hashlib
import hmac
import httpx
from ..config import get_settings

settings = get_settings()


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.meta_app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.meta_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    received = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, received)


def extract_incoming_messages(payload: dict) -> list[dict]:
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            name_by_wa = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in contacts
            }
            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue
                wa_id = msg.get("from")
                out.append({
                    "phone": wa_id,
                    "name": name_by_wa.get(wa_id),
                    "text": (msg.get("text") or {}).get("body", ""),
                    "external_id": msg.get("id"),
                    "raw": msg,
                })
    return out


def send_text_message(to: str, text: str):
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return {"sent": False, "reason": "WhatsApp credentials not configured"}
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    with httpx.Client(timeout=20) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()
