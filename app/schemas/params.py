"""Parámetros de ruta y query reutilizables, con su formato validado."""

from typing import Annotated, Literal

from fastapi import Path, Query

CodigoEquipo = Annotated[str, Path(pattern=r"^[A-Z]{3}$", description="Código FIFA del equipo", examples=["ARG"])]
CodigoJugador = Annotated[
    str, Path(pattern=r"^[A-Z]{3}-([1-9]|[1-9][0-9])$", description="`<equipo>-<dorsal>`", examples=["ARG-10"])
]

EquipoQuery = Annotated[str, Query(pattern=r"^[A-Z]{3}$", description="Código FIFA del equipo", examples=["ARG"])]
Posicion = Literal["Arquero", "Defensor", "Mediocampista", "Delantero"]
Limit = Annotated[int, Query(ge=1, le=100, description="Máximo de elementos por página")]
Skip = Annotated[int, Query(ge=0, le=1000, description="Elementos a saltear")]

SesionId = Annotated[
    str, Path(pattern=r"^SES-[A-Z0-9]{1,32}$", description="Identificador de la sesión", examples=["SES-0001"])
]
