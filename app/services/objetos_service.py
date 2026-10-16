from app.adapters import iris_adapter
from app.core.exceptions import ResourceNotFoundError
from app.schemas.objetos import PartidoObjeto


def obtener_partido(id: int, limit: int, skip: int) -> PartidoObjeto:
    objeto = iris_adapter.find_partido(id, limit, skip)
    if objeto is None:
        raise ResourceNotFoundError("OBJETO_NO_ENCONTRADO", "No existe el partido de demostración en IRIS.")
    return PartidoObjeto(**objeto, limit=limit, skip=skip)
