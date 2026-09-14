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


def _meta_error_message(response: httpx.Response) -> str:
    """Devuelve el error útil de Meta sin exponer el access token."""
    try:
        data = response.json()
    except ValueError:
        body = (response.text or "").strip()
        return f"HTTP {response.status_code}: {body[:500]}" if body else f"HTTP {response.status_code}"

    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return f"HTTP {response.status_code}: {str(data)[:500]}"

    message = error.get("message") or "Error de Meta"
    details = []
    if error.get("type"):
        details.append(f"type={error['type']}")
    if error.get("code") is not None:
        details.append(f"code={error['code']}")
    if error.get("error_subcode") is not None:
        details.append(f"subcode={error['error_subcode']}")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"HTTP {response.status_code}: {message}{suffix}"


def _meta_headers() -> dict[str, str]:
    if not settings.whatsapp_access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN no está configurado")
    return {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }


def get_waba_subscriptions() -> dict:
    if not settings.whatsapp_business_account_id:
        raise RuntimeError("WHATSAPP_BUSINESS_ACCOUNT_ID no está configurado")
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
        f"{settings.whatsapp_business_account_id}/subscribed_apps"
    )
    with httpx.Client(timeout=20) as client:
        response = client.get(url, headers=_meta_headers())
        if response.is_error:
            raise RuntimeError(_meta_error_message(response))
        return response.json()


def subscribe_app_to_waba() -> dict:
    if not settings.whatsapp_business_account_id:
        raise RuntimeError("WHATSAPP_BUSINESS_ACCOUNT_ID no está configurado")
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
        f"{settings.whatsapp_business_account_id}/subscribed_apps"
    )
    with httpx.Client(timeout=20) as client:
        response = client.post(url, headers=_meta_headers())
        if response.is_error:
            raise RuntimeError(_meta_error_message(response))
        return response.json()


def send_text_message(to: str, text: str):
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return {"sent": False, "reason": "WhatsApp credentials not configured"}
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(url, headers=_meta_headers(), json=payload)
        if response.is_error:
            raise RuntimeError(_meta_error_message(response))
        return response.json()
