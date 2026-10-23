# Hito 11: laboratorio de conectividad

Alcance confirmado: MongoDB, Neo4j, Redis e InfluxDB 3. Cassandra y la ruta de comentarios fueron retiradas el 2026-10-23. IRIS no está integrado. La evidencia anterior en `docs/evidencia/` es histórica del Hito 10.

La API y el diagnóstico se ejecutan en la notebook. Docker aloja cuatro motores en una red propia, con volúmenes nombrados del proyecto `fixture2030-hito11`. Los puertos se publican únicamente en loopback. El laboratorio no usa autenticación: sus resultados no certifican rechazo de credenciales ni separación de permisos.

| Motor | Host y puerto desde Python | Puerto interno/protocolo | Contexto | Lectura |
| --- | --- | --- | --- | --- |
| MongoDB | 127.0.0.1:37017 | 27017/Mongo wire | fixture2030 | equipos ARG y jugadores |
| Neo4j | 127.0.0.1:37687 | 7687/Bolt | neo4j | partido P-001 |
| Redis | 127.0.0.1:36379 | 6379/RESP | DB 0 | sesion:SES-DEMO y TTL |
| InfluxDB 3 | 127.0.0.1:38181 | 8181/HTTP SQL | fixture2030_resumen | estadisticas_partido, ventana 2030-06-24 20:00–20:05 UTC |

Neo4j Browser usa http://127.0.0.1:37474; acceder al portal no acredita Bolt. Desde contenedores, usar el nombre del servicio y puerto interno: localhost identifica a ese contenedor.

## Preparación y ejecución

Requisitos: Python 3.12, Docker con Compose y acceso al daemon; puertos 37017, 37474, 37687, 36379, 38181 y 18001 libres. Desde la raíz del backend:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/cerrar_hito11.py
```

Este comando inicia el laboratorio, espera a que respondan los protocolos, carga fixtures, inicia una API temporal en 18001, ejecuta diagnósticos/casos negativos/falla recuperable/tests y registra versiones y evidencia. Detiene su API al terminar y conserva motores y volúmenes. Se puede repetir sin borrar datos. `--puerto-api` permite elegir otro puerto para la API temporal. No ejecutarlo simultáneamente con otra evaluación que dependa del Redis de este laboratorio.

Si falta Docker o una dependencia Python, instalarla antes de ejecutar; la ausencia de herramienta es una prueba no ejecutada, no un motor caído. Las CLI mongosh/cypher-shell/redis-cli no son requisito: las lecturas usan los drivers Python del backend. Si la descarga de imágenes falla o los motores no arrancan dentro del plazo, corregir la preparación y repetir; no presentar ese intento como evidencia de conectividad.

Las versiones observadas y digests están en `evidencia/versiones.json`. Los tags Docker no son inmutables: para reproducir exactamente esas imágenes usar sus RepoDigests en el Compose, respetando la arquitectura registrada.

### Ejecución manual

Desde la raíz del backend, con dependencias de `requirements.lock` instaladas:

```bash
docker compose -f docker-compose.hito11.yaml up -d
set -a
source config/hito11.env.example
set +a
.venv/bin/python scripts/evaluar_conectividad.py --modo clientes
# Esperar inicialización si alguna fuente todavía no acepta consultas.
.venv/bin/python scripts/preparar_lab.py --laboratorio-descartable --sources mongodb,neo4j,redis,influxdb
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18000
```

En otra terminal, volver a cargar las variables del ejemplo y ejecutar:

```bash
.venv/bin/python scripts/evaluar_conectividad.py --salida docs/hito_11/evidencia/completo.json
.venv/bin/python scripts/evaluar_conectividad.py --modo tcp --producto redis
LIVE_MODULES=mongodb,neo4j,redis,influxdb .venv/bin/python -m pytest tests/integration -q
```

Los modos son `completo`, `configuracion` (incluye resolución), `tcp`, `clientes` y `api`. Los drivers Python son los clientes nativos utilizados. El diagnóstico es de solo lectura; la preparación escribe exclusivamente fixtures del laboratorio. El código de salida es 1 si alguna prueba falla o queda degradada, 0 si todas las ejecutadas pasan.

## Interpretación y limitaciones actuales

Cada resultado registra fecha UTC, producto, capa, duración y estado. TCP solo demuestra un listener; ping no demuestra el acceso a los datos. Identidad, autorización y contexto se comprueban conjuntamente en la lectura y no se certifican de forma independiente. Fallos no reconocidos permanecen sin clasificar, con un siguiente paso de diagnóstico. Una clave ausente no permite distinguir por sí sola expiración y falta de carga.

`disponible` significa que la prueba puntual pasó; `degradado`, que la lectura o ruta no satisface el caso; `no_disponible`, que falló la prueba. Para la matriz final, conservar `no probado` o `desconocido` en pruebas no ejecutadas o sin evidencia suficiente. SKIP nunca equivale a caída.

`/health` conserva 200 y up/down por motor. Ejecuta pings en paralelo bajo demanda y no certifica readiness de datos. `/live` y `/ready` están implementados; ver [health y readiness](health_readiness.md). El timeout por operación es 3 segundos en este entorno; no es un deadline total de request para operaciones de varias consultas.

No publicar URI con credenciales, mensajes crudos de drivers ni cuerpos con datos personales. Los JSON del CLI guardan resúmenes, no cuerpos. Los logs de la API permiten correlacionar request ID, dependencia, operación, resultado y duración.

## Falla y recuperación

Con la API activa y la sesión cargada, guardar una prueba Redis inicial. Detener únicamente Redis con `docker compose -f docker-compose.hito11.yaml stop redis`, repetir la prueba y verificar el 503 en GET de sesión. Restaurar siempre con `docker compose -f docker-compose.hito11.yaml start redis`, incluso si una prueba falla, y registrar el resultado recuperado. Conservar volúmenes y comparar TTL: una sesión puede expirar naturalmente.

Para finalizar el laboratorio usar `docker compose -f docker-compose.hito11.yaml stop`. No eliminar bases ni volúmenes para probar una falla.

## Evidencia ejecutada

Ver [matriz de conectividad](matriz_de_conectividad.md). La falla Redis ya se ejecutó y puede repetirse con `.venv/bin/python scripts/prueba_falla_redis.py`, después de cargar los fixtures e iniciar la API en 18000. El script restaura Redis en un bloque finally.

## Casos HTTP negativos y clasificación

Con la API del laboratorio activa, ejecutar:

```bash
.venv/bin/python scripts/prueba_api_negativos.py
```

El script no cambia configuraciones de los motores ni incorpora rutas de prueba a la API. Verifica mediante HTTP TCP real: equipo inexistente (404), lista sin jugadores (200 vacía), validación (400), ruta inexistente (404) y API inaccesible sobre un puerto local reservado sin listener (sin status HTTP).

En ASGI se inyectan excepciones de driver para verificar timeout (504), autenticación (503), autorización (503), contexto (503), consulta inválida (500) y error interno inesperado (500). Son simulaciones identificadas explícitamente; no acreditan credenciales/ACL reales del laboratorio. La detención real de Redis tiene su evidencia independiente.

Resultados: `evidencia/api_negativos.json`; logs de simulaciones: `api_negativos.log`; logs del servidor HTTP real: `api_cierre.log`. Los request IDs relacionan cada respuesta con los logs. El caso API inaccesible no tiene request ID de servidor porque ningún servidor recibió la solicitud. Los tiempos de las simulaciones prueban la traducción de la excepción, no la duración real de un timeout de motor. El script sale con código 1 si un caso no coincide con lo esperado.

El contrato público mantiene `code`, `message` y `requestId`; agrega códigos de error diferenciados y 504. OpenAPI y Postman incluyen las respuestas vigentes. Ver `../contratos_y_errores.md` para los criterios y límites de clasificación.
