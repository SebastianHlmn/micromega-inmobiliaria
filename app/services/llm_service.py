from ..config import get_settings

settings = get_settings()


class LLMService:
    def __init__(self):
        self.provider = settings.llm_provider

    def rewrite(self, draft: str, context: str = "") -> str:
        if self.provider == "mock" or not settings.openai_api_key:
            return draft
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
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
