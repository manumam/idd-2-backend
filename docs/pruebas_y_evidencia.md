# Pruebas y evidencia — Hito 10

Fecha: 2026-10-16. Entorno: Linux cloud x86_64, Python 3.12.14, Docker 28.4.0.
Dependencias exactas en `requirements.lock`. Instalación reproducible de esta
validación: `pip install -r requirements.lock`.

La suite unitaria usa TestClient ASGI en el mismo proceso y dobles de adaptadores.
Incluye una operación válida por módulo, entrada inválida antes de consultar,
ausencia, sesión expirada, dependencia inaccesible, lista vacía, límites,
paginación Cassandra, agregación temporal, DELETE repetido y OpenAPI compatible.
La suite de adaptadores controla parámetros, timeouts y traducción de errores.
La salida JUnit se conserva en `docs/evidencia/suite.xml`.

Los XML `integracion_*.xml` corresponden a requests ASGI que ejecutan drivers reales
contra contenedores locales de laboratorio. Cada test habilitado exige 200 con datos
representativos; los módulos no habilitados figuran como skipped y no son evidencia
de conectividad. La prueba de DELETE crea una sesión específica de test.

## Método reproducible

1. Configurar y cargar los servicios según `conectividad_y_configuracion.md`.
2. `python -m pytest -q --junitxml=docs/evidencia/suite_local.xml`.
3. `LIVE_MODULES=mongodb,redis python -m pytest tests/integration -v
   --junitxml=docs/evidencia/integracion_local.xml` (seleccionar las fuentes disponibles).
4. Iniciar la API y ejecutar `bash scripts/ejemplos_curl.sh` para el camino HTTP TCP.
5. Para comprobar un 503 real, detener una fuente en el laboratorio, pedir un recurso
   de ese módulo y registrar HTTP, código seguro y request ID. Restaurar la fuente.

El laboratorio sintético descartable puede prepararse con
`python scripts/preparar_lab.py --laboratorio-descartable --sources mongodb,redis`.
Este script reemplaza ARG y ARG-10 y crea SES-DEMO; no usarlo sobre los datos del grupo.
Las otras fuentes se seleccionan por `--sources` y requieren el esquema previo.
El fixture Cassandra se copió del Hito 6 del repositorio del equipo; es un modelo de
laboratorio, no una migración de datos.

## Rendimiento y límites de la evidencia

JUnit registra duración de tests incluyendo cliente ASGI, validación, transformación
y driver cuando corresponde. No es latencia HTTP externa ni throughput del sistema.
Volumen: un equipo, un jugador y muestras mínimas por módulo; concurrencia de prueba
secuencial. No se infiere capacidad para millones de usuarios ni comportamiento
multirregional. No hay benchmark productivo ni cifras de latencia presentadas como SLA.

Se intentó levantar los seis motores simultáneamente; el almacenamiento de las
imágenes agotó el disco. Se limpiaron exclusivamente contenedores/imágenes del
laboratorio y se continuó en grupos. Los fallos de infraestructura no se cuentan
como operaciones exitosas. La tabla de resultados está en `docs/evidencia/validacion.md`.

Resultado final: 66 pruebas generales aprobadas; 12 casos de integración aprobados
por tandas contra los cinco motores (8 Mongo/Redis/Neo4j, 2 Cassandra, 2 Influx).
Las omisiones de cada tanda son otros módulos, no integraciones pendientes.
