from typing import Dict, Literal

from pydantic import BaseModel

Estado = Literal["up", "down"]


class HealthResponse(BaseModel):
    estado: Dict[str, Estado]


class LivenessResponse(BaseModel):
    estado: Literal['alive'] = 'alive'


class ReadinessResponse(HealthResponse):
    listo: bool
