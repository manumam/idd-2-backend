# Validación ejecutada — 2026-10-16

Linux cloud x86_64; Python 3.12.14; Docker 28.4.0; versiones Python exactas en
`requirements.lock`. Requests ASGI con drivers reales hacia puertos publicados en
loopback. Fixtures sintéticos mínimos, cargados con `scripts/preparar_lab.py`;
esquema Cassandra en `tests/fixtures`, copiados del repositorio de
hitos anteriores del equipo.

| Comando / configuración | Resultado | Evidencia |
| --- | --- | --- |
| `python -m pytest -q` (sin LIVE_MODULES) | 66 passed, 13 skipped; incluye conexión rechazada real, integración omitida explícitamente | `suite.xml` |
| `LIVE_MODULES=mongodb,redis,neo4j python -m pytest tests/integration -q` | 8 passed, 5 skipped | `integracion_mongo_redis_neo4j.xml` |
| `CASSANDRA_HOSTS=127.0.0.1 LIVE_MODULES=cassandra python -m pytest tests/integration -q` | 2 passed, 11 skipped; lectura y cursor con dos comentarios | `integracion_cassandra.xml` |
| `NO_PROXY=127.0.0.1,localhost LIVE_MODULES=influxdb python -m pytest tests/integration -q` | 2 passed, 11 skipped; puntos y agregado de 1 minuto | `integracion_influx.xml` |

Imágenes de laboratorio: `mongo:7`, `redis:7`, `neo4j:5-community`, `cassandra:5`,
`influxdb:3-core`. Son tags de laboratorio; no se afirma que sean inmutables.
Mongo publicó 27017, Redis 6380, Neo4j 7687, Cassandra 9042 e Influx 8181 en
127.0.0.1. Neo4j sin autenticación y servicios aislados de laboratorio; no es
configuración productiva. Los servicios originales del grupo no fueron modificados.

Hubo intentos iniciales fallidos por disco lleno al descargar todos los motores,
por Cassandra todavía arrancando y por un proxy heredado que interceptaba HTTP
local hacia Influx. Se liberó espacio y se validaron motores por grupos; se añadió
NO_PROXY para loopback. También se corrigió una ejecución que coincidió con el
apagado del contenedor Cassandra y se repitió después de restaurarlo. Solo los XML
finales aprobados se presentan como evidencia de éxito.

La prueba real de falla usa Redis en 127.0.0.1:1 con timeout 0.2 s y cliente sin
reintentos: obtiene 503 REDIS_UNAVAILABLE con request ID. No sustituye el driver.
Las pruebas de otras fallas de dependencia usan dobles y están identificadas como tales.

No se mide capacidad productiva. Los tiempos JUnit incluyen toda la ejecución del
test y el entorno es de almacenamiento y memoria compartidos.



`http_tcp.json` registra seis requests TCP reales a Uvicorn en localhost:8000:
equipo, jugador, sesión, validación 400, OpenAPI y Swagger UI. Encabezado
X-Request-Id=tcp-hito10. No contiene cuerpos ni credenciales.
