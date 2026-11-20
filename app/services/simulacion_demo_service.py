"""Demo: lanza scripts/simular_en_vivo.py como proceso aparte e informa su estado."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.adapters import mongo_adapter
from app.config.settings import settings
from app.core.exceptions import BaseAppException, ResourceNotFoundError
from app.schemas.alineaciones import Alineaciones
from app.schemas.simulacion import SimulacionEstado

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simular_en_vivo.py"
ESPERA_PLAN_SEG = 60
ESPERA_CIERRE_SEG = 10


def motivo_no_simulable(documento: dict) -> str | None:
    """Condiciones del simulador en vivo para empezar; las comparte con esta API."""
    if documento.get("estadisticas_control") or documento.get("inicio_tracking"):
        return "El partido ya tuvo una simulación: restaurarlo o elegir otro próximo"
    if documento.get("estado") != "proximo" or documento.get("eventos") or documento.get("resultado"):
        return "Elegir un partido próximo sin resultados ni eventos"
    if not documento.get("local") or not documento.get("visitante"):
        return "Elegir un partido próximo con ambas selecciones definidas"
    return None


def motivo_sin_alineaciones(documento: dict) -> str | None:
    # Sin alineaciones no hay tracking: la demo mostraría un mapa de calor vacío.
    try:
        alineaciones = Alineaciones.model_validate(documento.get("alineaciones") or {})
    except ValidationError:
        return "Las alineaciones del partido son inválidas"
    cargadas = {lado: getattr(alineaciones, lado) for lado in ("local", "visitante") if getattr(alineaciones, lado)}
    if not cargadas:
        return "El partido no tiene alineaciones cargadas"
    if any(a.equipo.codigo != documento[lado]["codigo"] for lado, a in cargadas.items()):
        return "Una alineación no corresponde a la selección del partido"
    return None


class PlanNoCreado(Exception):
    pass


class ProcesoSimulador:
    def __init__(self, proceso: subprocess.Popen, salida: Path, errores: Path):
        self._proceso = proceso
        self._salida = salida
        self._errores = errores

    def codigo_salida(self) -> int | None:
        return self._proceso.poll()

    def lineas_salida(self) -> list[str]:
        return _leer_lineas(self._salida)

    def ultima_linea_error(self) -> str | None:
        return next(reversed(_leer_lineas(self._errores)), None)

    def detener(self) -> None:
        if self._proceso.poll() is not None:
            return
        # SIGINT: el script lo atrapa, informa el corte y cierra sus conexiones.
        self._proceso.send_signal(signal.SIGINT)
        try:
            self._proceso.wait(ESPERA_CIERRE_SEG)
        except subprocess.TimeoutExpired:
            self._proceso.kill()
            self._proceso.wait()


def _leer_lineas(archivo: Path) -> list[str]:
    try:
        return [linea for linea in archivo.read_text().splitlines() if linea.strip()]
    except FileNotFoundError:
        return []


class LanzadorSimulador:
    """Mismo intérprete, entorno y directorio que la API: el proceso usa las bases configuradas."""

    def _comando(self, *argumentos) -> list[str]:
        return [sys.executable, "-u", str(SCRIPT), *argumentos]

    def iniciar(self, partido: str, factor: float, directorio: Path) -> ProcesoSimulador:
        plan = directorio / f"plan-{partido}.json"
        try:
            creado = subprocess.run(self._comando(str(plan), "--crear-plan", partido), cwd=ROOT,
                                    env=os.environ.copy(), capture_output=True, text=True, timeout=ESPERA_PLAN_SEG)
        except subprocess.TimeoutExpired as exc:
            raise PlanNoCreado("El simulador no generó el plan a tiempo") from exc
        if creado.returncode != 0:
            raise PlanNoCreado("El simulador rechazó el partido al generar el plan")
        salida, errores = directorio / "salida.log", directorio / "errores.log"
        with salida.open("w") as stdout, errores.open("w") as stderr:
            proceso = subprocess.Popen(self._comando(str(plan), "--factor", str(factor)), cwd=ROOT,
                                       env=os.environ.copy(), stdout=stdout, stderr=stderr)
        return ProcesoSimulador(proceso, salida, errores)


def _segundo_de_juego(lineas: list[str]) -> int | None:
    segundo = None
    for linea in lineas:
        try:
            dato = json.loads(linea)
        except ValueError:
            continue
        if isinstance(dato, dict) and isinstance(dato.get("segundo_de_juego"), int):
            segundo = dato["segundo_de_juego"]
    return segundo


def _error(status: int, code: str, message: str) -> BaseAppException:
    return BaseAppException(code=code, message=message, status_code=status)


class SimulacionDemo:
    """Una simulación por proceso de la API; la consulta no espera al simulador."""

    def __init__(self, lanzador=None):
        self.lanzador = lanzador or LanzadorSimulador()
        self._lanzando = threading.Lock()
        self._proceso = None
        self._directorio = None
        self._partido = None
        self._factor = None
        self._iniciada_en = None

    def _en_curso(self) -> bool:
        return self._proceso is not None and self._proceso.codigo_salida() is None

    def estado(self) -> SimulacionEstado:
        proceso = self._proceso
        codigo = proceso.codigo_salida() if proceso else None
        error = None
        if proceso and codigo not in (None, 0):
            detalle = proceso.ultima_linea_error()
            error = f"El simulador terminó con código {codigo}" + (f": {detalle}" if detalle else "")
        return SimulacionEstado(
            habilitada=settings.demo_simulacion_habilitada,
            en_curso=proceso is not None and codigo is None,
            partido=self._partido,
            factor=self._factor,
            segundo_de_juego=_segundo_de_juego(proceso.lineas_salida()) if proceso else None,
            iniciada_en=self._iniciada_en,
            finalizada=codigo == 0,
            error=error,
        )

    def iniciar(self, partido: str, factor: float) -> SimulacionEstado:
        if not settings.demo_simulacion_habilitada:
            raise _error(403, "DEMO_DESHABILITADA", "La simulación desde la API está deshabilitada.")
        if not self._lanzando.acquire(blocking=False):
            raise _error(409, "SIMULACION_EN_CURSO", "Ya hay una simulación en curso.")
        try:
            if self._en_curso():
                raise _error(409, "SIMULACION_EN_CURSO", "Ya hay una simulación en curso.")
            documento = mongo_adapter.find_estadisticas(partido)
            if documento is None:
                raise ResourceNotFoundError("PARTIDO_NO_ENCONTRADO", f"No existe el partido '{partido}'.")
            motivo = motivo_no_simulable(documento) or motivo_sin_alineaciones(documento)
            if motivo:
                raise _error(409, "PARTIDO_NO_SIMULABLE", motivo + ".")
            self._limpiar()
            directorio = tempfile.TemporaryDirectory(prefix="simulacion-demo-")
            try:
                proceso = self.lanzador.iniciar(partido, factor, Path(directorio.name))
            except PlanNoCreado as exc:
                directorio.cleanup()
                raise _error(409, "PARTIDO_NO_SIMULABLE", f"{exc}.") from exc
            self._proceso, self._directorio = proceso, directorio
            self._partido, self._factor = partido, factor
            self._iniciada_en = datetime.now(timezone.utc).replace(microsecond=0)
        finally:
            self._lanzando.release()
        return self.estado()

    def _limpiar(self) -> None:
        if self._directorio is not None:
            self._directorio.cleanup()
            self._directorio = None

    def detener(self) -> None:
        if self._proceso is not None:
            self._proceso.detener()
        self._limpiar()


simulacion_demo = SimulacionDemo()


def estado_simulacion() -> SimulacionEstado:
    return simulacion_demo.estado()


def iniciar_simulacion(partido: str, factor: float) -> SimulacionEstado:
    return simulacion_demo.iniciar(partido, factor)


def detener_simulacion() -> None:
    simulacion_demo.detener()
