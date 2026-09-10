import re
from typing import Any

NEIGHBORHOODS = [
    "Caballito", "Villa Crespo", "Palermo", "Almagro", "Flores",
    "Belgrano", "Colegiales", "Chacarita", "Boedo", "Villa Urquiza"
]

ALLOWED_FIELDS = {
    "operation",
    "neighborhoods",
    "rooms_min",
    "rooms_max",
    "budget_max",
    "currency",
    "pets",
    "move_date",
}


def _money(text: str):
    t = text.lower().replace(".", "")
    m = re.search(r"(?:hasta|máximo|maximo|presupuesto(?: de)?)\s*(?:\$|usd|u\$s)?\s*([0-9]+(?:,[0-9]+)?)\s*(mil|m)?", t)
    if not m:
        return None, None
    n = float(m.group(1).replace(",", "."))
    suffix = m.group(2)
    if suffix == "mil":
        n *= 1000
    elif suffix == "m":
        n *= 1_000_000
    currency = "USD" if "usd" in t or "u$s" in t else "ARS"
    return n, currency


def normalize_search_fields(fields: dict[str, Any] | None) -> dict:
    """Normaliza y filtra la salida de cualquier extractor antes de tocar la base."""
    if not isinstance(fields, dict):
        return {}

    out: dict[str, Any] = {}

    operation = fields.get("operation")
    if isinstance(operation, str):
        op = operation.strip().lower()
        if op in {"alquiler", "venta"}:
            out["operation"] = op

    neighborhoods = fields.get("neighborhoods")
    if isinstance(neighborhoods, list):
        cleaned = []
        seen = set()
        for item in neighborhoods:
            if not isinstance(item, str):
                continue
            value = item.strip()
            key = value.casefold()
            if value and key not in seen:
                cleaned.append(value)
                seen.add(key)
        if cleaned:
            out["neighborhoods"] = cleaned[:10]

    for key in ("rooms_min", "rooms_max"):
        value = fields.get(key)
        if isinstance(value, bool):
            continue
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 20:
            out[key] = value

    if "rooms_min" in out and "rooms_max" in out and out["rooms_min"] > out["rooms_max"]:
        out["rooms_min"], out["rooms_max"] = out["rooms_max"], out["rooms_min"]

    value = fields.get("budget_max")
    if not isinstance(value, bool):
        try:
            value = float(value)
            if value > 0:
                out["budget_max"] = value
        except (TypeError, ValueError):
            pass

    currency = fields.get("currency")
    if isinstance(currency, str):
        cur = currency.strip().upper()
        if cur in {"ARS", "USD"}:
            out["currency"] = cur

    pets = fields.get("pets")
    if isinstance(pets, bool):
        out["pets"] = pets

    move_date = fields.get("move_date")
    if isinstance(move_date, str) and move_date.strip():
        out["move_date"] = move_date.strip()[:30]

    return {k: v for k, v in out.items() if k in ALLOWED_FIELDS}


def extract_search_fields_rules(text: str) -> dict:
    """Extractor determinístico de respaldo. No requiere un modelo externo."""
    low = text.lower()
    out: dict = {}

    if "alquil" in low:
        out["operation"] = "alquiler"
    elif "compr" in low or "venta" in low:
        out["operation"] = "venta"

    barrios = [b for b in NEIGHBORHOODS if b.lower() in low]
    if barrios:
        out["neighborhoods"] = barrios

    range_m = re.search(r"([1-6])\s*(?:o|a|/|-)\s*([1-6])\s*amb", low)
    single_m = re.search(r"([1-6])\s*amb", low)
    if range_m:
        out["rooms_min"] = int(range_m.group(1))
        out["rooms_max"] = int(range_m.group(2))
    elif single_m:
        out["rooms_min"] = int(single_m.group(1))
        out["rooms_max"] = int(single_m.group(1))

    money, currency = _money(text)
    if money:
        out["budget_max"] = money
        out["currency"] = currency

    if any(k in low for k in ["no tengo mascota", "sin mascota", "sin perro", "sin gato"]):
        out["pets"] = False
    elif any(k in low for k in ["perro", "gato", "mascota"]):
        out["pets"] = True

    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    for month in months:
        if month in low:
            out["move_date"] = month
            break

    return normalize_search_fields(out)


def extract_search_fields(text: str) -> dict:
    """Compatibilidad con la V0: usa el extractor por reglas."""
    return extract_search_fields_rules(text)
