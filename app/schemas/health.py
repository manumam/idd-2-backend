from typing import Dict, Literal

from pydantic import BaseModel

Estado = Literal["up", "down"]


class HealthResponse(BaseModel):
    estado: Dict[str, Estado]
