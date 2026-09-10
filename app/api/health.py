from fastapi import APIRouter
from ..config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
def health():
    return {"app": settings.app_name, "status": "ok", "env": settings.app_env}
