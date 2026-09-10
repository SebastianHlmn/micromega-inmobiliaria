from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas import SimulateMessageRequest
from ..services.conversation_service import handle_message

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


@router.post("/message")
def simulate(req: SimulateMessageRequest, db: Session = Depends(get_db)):
    return handle_message(
        db=db,
        phone=req.phone,
        name=req.name,
        text=req.text,
        channel="simulator",
    )
