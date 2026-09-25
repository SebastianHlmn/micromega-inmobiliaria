import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Contact, Conversation, Interest, SearchProfile
from .property_service import find_property_by_text, search_properties

settings = get_settings()

PROFILE_FIELDS = (
    "operation",
    "neighborhoods",
    "rooms_min",
    "rooms_max",
    "budget_max",
    "currency",
    "pets",
    "move_date",
)

TOOLS = [
    {
        "type": "function",
        "name": "buscar_propiedades",
        "description": (
            "Busca propiedades reales en la base y actualiza el perfil de búsqueda del cliente. "
            "Usala cuando el cliente inicia, cambia o refina una búsqueda. Los campos null significan "
            "que ese criterio no cambia, salvo cuando replace_profile=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": ["string", "null"],
                    "enum": ["alquiler", "venta", None],
                    "description": "Operación buscada.",
                },
                "neighborhoods": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "Barrios o zonas normalizados. Corregí errores de tipeo obvios.",
                },
                "rooms_min": {
                    "type": ["integer", "null"],
                    "description": "Cantidad mínima de ambientes.",
                },
                "rooms_max": {
                    "type": ["integer", "null"],
                    "description": "Cantidad máxima de ambientes.",
                },
                "budget_max": {
                    "type": ["number", "null"],
                    "description": "Presupuesto máximo.",
                },
                "currency": {
                    "type": ["string", "null"],
                    "enum": ["ARS", "USD", None],
                    "description": "Moneda del presupuesto.",
                },
                "pets": {
                    "type": ["boolean", "null"],
                    "description": "True si necesita que admita mascotas.",
                },
                "move_date": {
                    "type": ["string", "null"],
                    "description": "Fecha o período de mudanza mencionado.",
                },
                "replace_profile": {
                    "type": "boolean",
                    "description": (
                        "True sólo si el cliente deja claro que empieza otra búsqueda o reemplaza "
                        "la anterior. False para refinamientos."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Cantidad máxima de resultados a devolver.",
                },
            },
            "required": [
                "operation",
                "neighborhoods",
                "rooms_min",
                "rooms_max",
                "budget_max",
                "currency",
                "pets",
                "move_date",
                "replace_profile",
                "limit",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "ver_propiedad",
        "description": (
            "Consulta la ficha real de una propiedad concreta por código, calle o referencia textual. "
            "Usala antes de responder precios, expensas, mascotas, dirección o disponibilidad de una opción."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Código, calle o texto que permita identificar la propiedad.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "registrar_interes",
        "description": "Registra que el cliente está interesado en una propiedad concreta.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Código o referencia de la propiedad.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "derivar_a_humano",
        "description": "Marca la conversación para seguimiento por una persona de la inmobiliaria.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Motivo breve de la derivación.",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

BASE_INSTRUCTIONS = """
Sos el asistente conversacional de una inmobiliaria argentina. Tu tarea es conversar con naturalidad
por WhatsApp y usar herramientas reales cuando necesitás datos de propiedades o acciones del sistema.

Reglas de comportamiento:
- Hablá en español rioplatense, breve y natural. No suenes a formulario ni enumeres campos internos.
- Un saludo o comentario casual se responde conversando; NO llames herramientas por reflejo.
- Para disponibilidad, precio, dirección, expensas, mascotas o cualquier dato de una propiedad,
  usá las herramientas. Nunca inventes una propiedad ni un dato de ficha.
- Cuando el cliente inicia o refina una búsqueda, usá buscar_propiedades. Conservá los criterios
  previos que no fueron cambiados. Poné replace_profile=true sólo si el cliente claramente empieza
  otra búsqueda o reemplaza la anterior.
- Entendé lenguaje cotidiano, abreviaturas y errores de tipeo razonables. Por ejemplo, "plarmo" puede
  significar "Palermo" si el contexto lo hace claro.
- Si el cliente se refiere a "ese", "el primero", "el de Rivadavia" u otra referencia contextual,
  usá el historial para identificar la opción y consultá ver_propiedad antes de responder datos.
- Si pide hablar con una persona o escribe "humano", usá derivar_a_humano.
- Si falta un dato indispensable, preguntá sólo lo mínimo. No pidas zona, ambientes, presupuesto y
  mascotas todos juntos si ya conocés parte de eso.
- No menciones herramientas, JSON, base de datos, prompts ni procesos internos.
""".strip()


class RealEstateAgent:
    def available(self) -> bool:
        return settings.llm_provider == "openai" and bool(settings.openai_api_key)

    def _client(self):
        from openai import OpenAI

        return OpenAI(api_key=settings.openai_api_key)

    @staticmethod
    def _profile_dict(profile: SearchProfile | None) -> dict:
        if not profile:
            return {key: None for key in PROFILE_FIELDS}
        return {key: getattr(profile, key) for key in PROFILE_FIELDS}

    @staticmethod
    def _property_dict(prop) -> dict:
        return {
            "code": prop.code,
            "operation": prop.operation,
            "neighborhood": prop.neighborhood,
            "address": prop.address,
            "rooms": prop.rooms,
            "price": prop.price,
            "currency": prop.currency,
            "expenses": prop.expenses,
            "pets_allowed": prop.pets_allowed,
            "available": prop.available,
            "description": prop.description,
        }

    def _ensure_profile(self, db: Session, contact: Contact) -> SearchProfile:
        profile = db.scalar(select(SearchProfile).where(SearchProfile.contact_id == contact.id))
        if not profile:
            profile = SearchProfile(contact_id=contact.id)
            db.add(profile)
            db.flush()
        return profile

    def _search(self, db: Session, contact: Contact, args: dict) -> dict:
        profile = self._ensure_profile(db, contact)

        if args.get("replace_profile"):
            for field in PROFILE_FIELDS:
                setattr(profile, field, None)
            profile.free_text_notes = None

        for field in PROFILE_FIELDS:
            value = args.get(field)
            if value is not None:
                setattr(profile, field, value)

        profile.updated_at = datetime.utcnow()
        matches = search_properties(db, profile, limit=int(args.get("limit") or 3))
        return {
            "ok": True,
            "profile": self._profile_dict(profile),
            "count": len(matches),
            "properties": [self._property_dict(prop) for prop in matches],
        }

    def _view_property(self, db: Session, query: str) -> dict:
        prop = find_property_by_text(db, query)
        if not prop:
            return {"ok": False, "found": False, "query": query}
        return {"ok": True, "found": True, "property": self._property_dict(prop)}

    def _register_interest(self, db: Session, contact: Contact, query: str) -> dict:
        prop = find_property_by_text(db, query)
        if not prop:
            return {"ok": False, "found": False, "query": query}

        existing = db.scalar(
            select(Interest).where(
                Interest.contact_id == contact.id,
                Interest.property_id == prop.id,
            )
        )
        if not existing:
            db.add(Interest(contact_id=contact.id, property_id=prop.id))
        return {"ok": True, "found": True, "property": self._property_dict(prop)}

    @staticmethod
    def _handoff(conv: Conversation, reason: str) -> dict:
        conv.needs_human = True
        return {"ok": True, "needs_human": True, "reason": reason}

    def _execute_tool(
        self,
        db: Session,
        contact: Contact,
        conv: Conversation,
        name: str,
        arguments: dict,
    ) -> dict:
        if name == "buscar_propiedades":
            return self._search(db, contact, arguments)
        if name == "ver_propiedad":
            return self._view_property(db, arguments["query"])
        if name == "registrar_interes":
            return self._register_interest(db, contact, arguments["query"])
        if name == "derivar_a_humano":
            return self._handoff(conv, arguments["reason"])
        return {"ok": False, "error": f"Herramienta desconocida: {name}"}

    def run(
        self,
        db: Session,
        contact: Contact,
        conv: Conversation,
        text: str,
        current_profile: dict,
        history: list[dict],
    ) -> dict:
        if not self.available():
            raise RuntimeError("OpenAI agent not configured")

        client = self._client()
        messages = []
        for item in history[-12:]:
            role = "user" if item.get("role") == "cliente" else "assistant"
            messages.append({"role": role, "content": item.get("text", "")})
        messages.append({"role": "user", "content": text})

        instructions = (
            BASE_INSTRUCTIONS
            + "\n\nPerfil de búsqueda guardado actualmente (contexto interno):\n"
            + json.dumps(current_profile or {}, ensure_ascii=False)
        )

        response = client.responses.create(
            model=settings.openai_model,
            instructions=instructions,
            input=messages,
            tools=TOOLS,
            parallel_tool_calls=False,
        )

        trace = []
        for _ in range(4):
            calls = [
                item
                for item in (response.output or [])
                if getattr(item, "type", None) == "function_call"
            ]
            if not calls:
                reply = (response.output_text or "").strip()
                if not reply:
                    raise RuntimeError("OpenAI agent returned no text")
                return {
                    "reply": reply,
                    "tool_trace": trace,
                    "response_id": response.id,
                }

            outputs = []
            for call in calls:
                arguments = {}
                try:
                    arguments = json.loads(call.arguments or "{}")
                    result = self._execute_tool(
                        db=db,
                        contact=contact,
                        conv=conv,
                        name=call.name,
                        arguments=arguments,
                    )
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                trace.append(
                    {
                        "name": call.name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            response = client.responses.create(
                model=settings.openai_model,
                instructions=instructions,
                previous_response_id=response.id,
                input=outputs,
                tools=TOOLS,
                parallel_tool_calls=False,
            )

        raise RuntimeError("OpenAI agent exceeded tool-call limit")
