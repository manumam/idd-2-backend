"""Vista SQL del árbol de objetos persistentes del Hito 9, en el namespace configurado."""

from contextlib import contextmanager, suppress
from math import ceil

from app.adapters.base import BaseAdapter
from app.core.observability import observe
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError


class IrisAdapter(BaseAdapter):
    @contextmanager
    def _cursor(self):
        connection = None
        cursor = None
        try:
            import iris.dbapi
            connection = iris.dbapi.connect(
                hostname=settings.iris_host, port=settings.iris_port,
                namespace=settings.iris_namespace, username=settings.iris_user,
                password=settings.iris_password, timeout=ceil(settings.db_timeout_seconds),
                sharedmemory=False, autoCommit=True,
            )
            cursor = connection.cursor()
            cursor.setQueryTimeout(ceil(settings.db_timeout_seconds))
            yield cursor
        except Exception as exc:
            raise DatabaseUnavailableError("IRIS", exc) from exc
        finally:
            if cursor is not None:
                with suppress(Exception):
                    cursor.close()
            if connection is not None:
                with suppress(Exception):
                    connection.close()

    @observe("IRIS")
    def find_partido(self, id: int, limit: int, skip: int) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT ID, Codigo, Estado FROM Fixture.Partido WHERE ID = ?", [id])
            fila = cursor.fetchone()
            if fila is None:
                return None
            partido = {"id": str(fila[0]), "codigo": fila[1], "estado": fila[2]}
            # Solo el límite numérico validado se incorpora al SQL; la identidad se enlaza.
            cursor.execute(
                f"SELECT TOP {int(limit + skip)} ID, Tipo, Minuto, Partido "
                "FROM Fixture.Evento WHERE Partido = ? ORDER BY ID", [id],
            )
            partido["eventos"] = [
                {"id": str(e[0]), "tipo": e[1], "minuto": e[2], "partidoId": str(e[3])}
                for e in list(cursor.fetchall())[skip:]
            ]
            return partido

    @observe("IRIS")
    def ping(self) -> bool:
        with self._cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True

    def close(self) -> None:
        """Cada operación cierra su conexión; no se comparte entre threads."""


iris_adapter = IrisAdapter()
