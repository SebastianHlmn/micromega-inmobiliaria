from contextlib import asynccontextmanager
from fastapi import FastAPI
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
    }
