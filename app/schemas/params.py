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

CodigoPartido = Annotated[str, Path(pattern=r"^P-[0-9]{3}$", description="Código del partido", examples=["P-001"])]
CodigoSede = Annotated[str, Path(pattern=r"^S-[0-9]{2}$", description="Código de la sede", examples=["S-04"])]
Confederacion = Annotated[
    Literal["UEFA", "CONMEBOL", "CAF", "AFC", "CONCACAF", "OFC"],
    Query(description="Confederación del equipo del goleador"),
]
LimitEventos = Annotated[int, Query(ge=1, le=200, description="Máximo de eventos a devolver")]
LimitGoleadores = Annotated[int, Query(ge=1, le=100, description="Máximo de goles a devolver")]

FechaHora = Annotated[
    str,
    Query(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", description="Hora UTC `AAAA-MM-DDThh:mm:ssZ`"),
]
Ventana = Literal["1m", "5m"]
