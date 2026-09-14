from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .config import get_settings
from .db import Base, engine
from . import models  # noqa: F401
from .api.health import router as health_router
from .api.simulator import router as simulator_router
from .api.properties import router as properties_router
from .api.admin import router as admin_router
from .api.whatsapp import router as whatsapp_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.include_router(simulator_router)
app.include_router(properties_router)
app.include_router(admin_router)
app.include_router(whatsapp_router)


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "simulator": "/api/simulator/message",
        "whatsapp_webhook": "/webhooks/whatsapp",
        "privacy": "/privacy",
    }


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """Política pública mínima para el entorno de prueba de WhatsApp."""
    return """
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Política de privacidad · Micromega Inmobiliaria</title>
      <style>
        body { font-family: Arial, sans-serif; max-width: 820px; margin: 48px auto; padding: 0 22px; line-height: 1.55; color: #1f2937; }
        h1, h2 { color: #111827; }
        h1 { font-size: 2rem; margin-bottom: .3rem; }
        h2 { margin-top: 2rem; font-size: 1.15rem; }
        .muted { color: #6b7280; }
      </style>
    </head>
    <body>
      <h1>Política de privacidad</h1>
      <p class="muted">Micromega Inmobiliaria · entorno de desarrollo y prueba</p>

      <p>Micromega Inmobiliaria utiliza WhatsApp para recibir consultas inmobiliarias y responderlas mediante un sistema automatizado asistido por inteligencia artificial.</p>

      <h2>Datos tratados</h2>
      <p>Podemos procesar el número de teléfono, nombre de perfil de WhatsApp, contenido de los mensajes y preferencias inmobiliarias que la persona comunique voluntariamente, por ejemplo zona, tipo de operación, cantidad de ambientes, presupuesto o condiciones relevantes para la búsqueda.</p>

      <h2>Finalidad</h2>
      <p>Los datos se utilizan exclusivamente para mantener la conversación, interpretar la consulta, buscar opciones inmobiliarias compatibles, conservar el contexto necesario de la conversación y, cuando corresponda, derivar la consulta a una persona.</p>

      <h2>Proveedores tecnológicos</h2>
      <p>Para prestar el servicio pueden intervenir proveedores tecnológicos necesarios para la mensajería y el procesamiento automatizado, incluyendo Meta/WhatsApp y OpenAI. El contenido se comparte con estos proveedores únicamente en la medida necesaria para operar el servicio.</p>

      <h2>Conservación y seguridad</h2>
      <p>Los datos se conservan durante el tiempo necesario para operar y evaluar el servicio. Se aplican medidas razonables de seguridad y se evita utilizar la información para fines ajenos a la consulta inmobiliaria.</p>

      <h2>Venta de datos</h2>
      <p>Micromega Inmobiliaria no vende los datos personales de las personas usuarias.</p>

      <h2>Acceso, corrección o eliminación</h2>
      <p>La persona puede solicitar acceso, corrección o eliminación de la información asociada a su conversación respondiendo por el mismo canal de WhatsApp utilizado para contactar al servicio.</p>

      <h2>Cambios</h2>
      <p>Esta política puede actualizarse a medida que el servicio evolucione. La versión vigente será la publicada en esta URL.</p>

      <p class="muted">Última actualización: 14 de septiembre de 2026.</p>
    </body>
    </html>
    """
