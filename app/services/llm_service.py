import json

from ..config import get_settings
from .extraction_service import extract_search_fields_rules, normalize_search_fields

settings = get_settings()


class LLMService:
    def __init__(self):
        self.provider = settings.llm_provider

    def _openai_client(self):
        from openai import OpenAI
        return OpenAI(api_key=settings.openai_api_key)

    def extract_search_fields(self, text: str, current_profile: dict | None = None) -> tuple[dict, str]:
        """Interpreta el mensaje como una actualización del perfil de búsqueda.

        Devuelve (campos_normalizados, fuente). Si no hay LLM configurado o falla,
        usa el extractor determinístico de respaldo.
        """
        if self.provider != "openai" or not settings.openai_api_key:
            return extract_search_fields_rules(text), "rules"

        current_profile = current_profile or {}
        prompt = f"""
Sos un extractor de información para una inmobiliaria argentina.
Tu tarea NO es responder al cliente: sólo interpretar qué datos de su búsqueda inmobiliaria
quedan establecidos o modificados por el mensaje actual.

Perfil actual del contacto:
{json.dumps(current_profile, ensure_ascii=False)}

Mensaje actual:
{text}

Devolvé exclusivamente un objeto JSON válido, sin markdown ni explicación.
Sólo se permiten estas claves:
- operation: "alquiler" o "venta"
- neighborhoods: lista de barrios o zonas
- rooms_min: entero
- rooms_max: entero
- budget_max: número
- currency: "ARS" o "USD"
- pets: booleano; true si necesita/admite buscar con mascota, false si expresa que no tiene o no necesita condición de mascotas
- move_date: texto breve con la fecha o período mencionado

Reglas:
1. No inventes datos ni completes por costumbre inmobiliaria.
2. Interpretá lenguaje cotidiano, abreviaturas y expresiones rioplatenses.
3. El resultado representa ACTUALIZACIONES para aplicar al perfil actual.
4. Si el mensaje agrega una zona a las ya buscadas (por ejemplo "también Palermo"), neighborhoods debe contener la lista resultante completa.
5. Si restringe la zona (por ejemplo "mejor solo Palermo"), devolvé sólo esa zona.
6. Si dice un rango de ambientes, separalo en rooms_min y rooms_max.
7. Normalizá importes: "800 mil" = 800000; "1,2 millones" = 1200000.
8. Un símbolo $ sin otra indicación se interpreta como ARS; USD, dólares o U$S como USD.
9. Si el mensaje no aporta ni cambia ningún dato de búsqueda, devolvé {{}}.
""".strip()

        try:
            client = self._openai_client()
            response = client.responses.create(
                model=settings.openai_model,
                input=prompt,
            )
            raw = (response.output_text or "").strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lstrip().startswith("json"):
                    raw = raw.lstrip()[4:].lstrip()
            parsed = json.loads(raw)
            return normalize_search_fields(parsed), "openai"
        except Exception:
            return extract_search_fields_rules(text), "rules_fallback"

    def rewrite(self, draft: str, context: str = "") -> str:
        if self.provider != "openai" or not settings.openai_api_key:
            return draft
        try:
            client = self._openai_client()
            response = client.responses.create(
                model=settings.openai_model,
                input=(
                    "Sos la capa de redacción de una inmobiliaria. No inventes datos. "
                    "Conservá cifras, disponibilidad y condiciones tal como aparecen en el borrador. "
                    "Respondé en español rioplatense, breve y natural.\n\n"
                    f"Contexto: {context}\nBorrador: {draft}"
                ),
            )
            return response.output_text.strip() or draft
        except Exception:
            return draft
