import json
import re

from ..config import get_settings
from .extraction_service import extract_search_fields_rules, normalize_search_fields

settings = get_settings()


ALLOWED_INTENTS = {
    "greeting",
    "new_search",
    "refine_search",
    "property_question",
    "general_question",
    "handoff",
}


class LLMService:
    def __init__(self):
        self.provider = settings.llm_provider

    def _openai_client(self):
        from openai import OpenAI
        return OpenAI(api_key=settings.openai_api_key)

    @staticmethod
    def _has_profile_data(current_profile: dict | None) -> bool:
        if not current_profile:
            return False
        return any(
            current_profile.get(key) not in (None, [], "")
            for key in (
                "operation",
                "neighborhoods",
                "rooms_min",
                "rooms_max",
                "budget_max",
                "currency",
                "pets",
                "move_date",
            )
        )

    def _classify_intent_rules(self, text: str, current_profile: dict | None = None) -> str:
        """Respaldo simple cuando el LLM no está disponible.

        No intenta resolver toda la conversación: sólo evita que saludos y preguntas
        contextuales disparen una búsqueda inmobiliaria por defecto.
        """
        lowered = re.sub(r"\s+", " ", text.lower().strip())

        if settings.human_handoff_keyword.lower() in lowered:
            return "handoff"

        search_terms = (
            "alquil", "compr", "venta", "ambiente", "amb ", "monoamb",
            "presupuesto", "hasta ", "usd", "dólar", "dolar", "mascota",
            "perro", "gato", "barrio", "zona", "algo por", "más barato",
            "mas barato", "más grande", "mas grande", "más chico", "mas chico",
        )
        property_question_terms = (
            "esa propiedad", "ese depto", "ese departamento", "esa casa",
            "el de ", "la de ", "expensas", "admite", "acepta", "disponible",
            "dirección", "direccion", "precio", "metros", "m2", "balcón", "balcon",
        )
        greeting_terms = (
            "hola", "buen día", "buen dia", "buenas", "buenas tardes",
            "buenas noches", "cómo va", "como va", "cómo estás", "como estas",
            "cómo te va", "como te va",
        )

        if any(term in lowered for term in property_question_terms) and (
            "?" in text or not any(term in lowered for term in ("busco", "quiero", "necesito"))
        ):
            return "property_question"

        has_search_term = any(term in lowered for term in search_terms)
        if any(term in lowered for term in greeting_terms) and not has_search_term and len(lowered) < 100:
            return "greeting"

        if has_search_term or any(term in lowered for term in ("busco", "quiero", "necesito", "tenés algo", "tenes algo")):
            explicit_new = any(
                term in lowered
                for term in ("otra búsqueda", "otra busqueda", "nueva búsqueda", "nueva busqueda", "arranquemos de nuevo")
            )
            if explicit_new or not self._has_profile_data(current_profile):
                return "new_search"
            return "refine_search"

        return "general_question"

    def classify_intent(
        self,
        text: str,
        current_profile: dict | None = None,
        history: list[dict] | None = None,
    ) -> tuple[str, str]:
        """Clasifica qué está haciendo el cliente antes de ejecutar acciones.

        Esto evita el patrón anterior en el que cualquier mensaje, incluso "hola",
        terminaba reutilizando el perfil previo y lanzando una búsqueda de propiedades.
        """
        fallback = self._classify_intent_rules(text, current_profile)
        if self.provider != "openai" or not settings.openai_api_key:
            return fallback, "rules"

        prompt = f"""
Sos el clasificador de intención de un chatbot inmobiliario argentino.
No respondas al cliente. Elegí UNA sola intención para el mensaje actual teniendo en cuenta
el perfil ya guardado y, cuando sirva, el historial reciente.

Intenciones permitidas:
- greeting: saludo, cortesía o charla breve sin pedido inmobiliario nuevo.
- new_search: inicia claramente una búsqueda nueva o reemplaza la búsqueda anterior.
- refine_search: agrega, cambia o restringe criterios de una búsqueda ya existente.
- property_question: pregunta por una propiedad concreta o por una opción mencionada antes.
- general_question: consulta conversacional que no requiere ejecutar una búsqueda nueva.
- handoff: pide hablar con una persona/humano de la inmobiliaria.

Criterios importantes:
1. "Hola", "¿cómo va?" o similares deben ser greeting aunque exista un perfil previo.
2. "¿Y algo por Villa Crespo?", "¿más barato?" o "con balcón" son refine_search si ya había búsqueda.
3. "¿Ese de Rivadavia admite perro?" o "¿cuánto paga de expensas?" son property_question.
4. Un saludo no debe transformarse en búsqueda sólo porque exista un perfil guardado.
5. No inventes intención inmobiliaria cuando el mensaje no la expresa.

Perfil actual:
{json.dumps(current_profile or {}, ensure_ascii=False)}

Historial reciente:
{json.dumps(history or [], ensure_ascii=False)}

Mensaje actual:
{text}

Devolvé exclusivamente JSON válido con esta forma:
{{"intent":"greeting"}}
""".strip()

        try:
            client = self._openai_client()
            response = client.responses.create(model=settings.openai_model, input=prompt)
            raw = (response.output_text or "").strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lstrip().startswith("json"):
                    raw = raw.lstrip()[4:].lstrip()
            parsed = json.loads(raw)
            intent = str(parsed.get("intent", "")).strip()
            if intent in ALLOWED_INTENTS:
                return intent, "openai"
        except Exception:
            pass
        return fallback, "rules_fallback"

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

    def conversational_reply(
        self,
        text: str,
        guidance: str,
        fallback: str,
        current_profile: dict | None = None,
        history: list[dict] | None = None,
    ) -> str:
        """Genera una respuesta conversacional cuando no corresponde buscar propiedades."""
        if self.provider != "openai" or not settings.openai_api_key:
            return fallback
        try:
            client = self._openai_client()
            response = client.responses.create(
                model=settings.openai_model,
                input=(
                    "Sos el chatbot de una inmobiliaria argentina. Respondé en español rioplatense, "
                    "natural, breve y sin tono de formulario. No inventes propiedades, precios, "
                    "disponibilidad ni datos que no estén en el contexto. No ejecutes ni simules una búsqueda. "
                    "Si hay una búsqueda previa, podés reconocerla sin repetirla mecánicamente.\n\n"
                    f"Objetivo para esta respuesta: {guidance}\n"
                    f"Perfil guardado: {json.dumps(current_profile or {}, ensure_ascii=False)}\n"
                    f"Historial reciente: {json.dumps(history or [], ensure_ascii=False)}\n"
                    f"Mensaje actual del cliente: {text}"
                ),
            )
            return response.output_text.strip() or fallback
        except Exception:
            return fallback

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
