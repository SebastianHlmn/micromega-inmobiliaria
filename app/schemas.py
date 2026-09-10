from pydantic import BaseModel, Field


class SimulateMessageRequest(BaseModel):
    phone: str = Field(default="+5491100000000")
    name: str | None = "Cliente demo"
    text: str


class PropertyCreate(BaseModel):
    code: str
    operation: str
    neighborhood: str
    address: str
    rooms: int
    price: float
    currency: str = "ARS"
    expenses: float | None = None
    pets_allowed: bool | None = None
    available: bool = True
    description: str | None = None
