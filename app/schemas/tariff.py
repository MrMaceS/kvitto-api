from pydantic import BaseModel


class TariffOut(BaseModel):
    id: int
    title: str
    price: int  # в копейках

    model_config = {"from_attributes": True}
