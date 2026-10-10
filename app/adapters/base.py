"""Contrato base para adaptadores NoSQL.

Garantiza que todos los adaptadores ofrezcan una interfaz consistente
para verificar disponibilidad y liberar conexiones (RNF1, RNF5).
"""

from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Clase base abstracta para adaptadores de bases de datos."""

    @abstractmethod
    def ping(self) -> bool:
        """Verifica la conectividad activa contra el motor.

        Devuelve True si responde correctamente.
        Lanza DatabaseUnavailableError si la base está caída o hace timeout.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Cierra conexiones o libera el pool de recursos."""
        pass
