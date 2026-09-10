import re

NEIGHBORHOODS = [
    "Caballito", "Villa Crespo", "Palermo", "Almagro", "Flores",
    "Belgrano", "Colegiales", "Chacarita", "Boedo", "Villa Urquiza"
]


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


def extract_search_fields(text: str) -> dict:
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

    if any(k in low for k in ["perro", "gato", "mascota"]):
        out["pets"] = True

    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    for month in months:
        if month in low:
            out["move_date"] = month
            break

    return out
