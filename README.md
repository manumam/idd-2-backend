# Fixture 2030 — Backend

API del Mundial 2030. El MVP usa MongoDB para partidos y eventos, Redis para
caché e InfluxDB para series temporales. Los [lineamientos](docs/lineamientos-entrega-demo.md),
[casos de uso](docs/casos-de-uso-fixture.md) y [modelo técnico](docs/modelo-tecnico-demo.md)
definen el alcance; el [seguimiento](docs/casos_de_uso.md) registra lo implementado y pendiente.

La API actual todavía conserva adaptadores y rutas de Neo4j, Cassandra, sesiones
e IRIS que deben migrarse o retirarse. Su existencia no modifica el alcance del MVP.
Consultar el [índice de documentación](docs/README.md).

El arranque de la aplicación, los tests habituales y las evaluaciones de hitos son
procedimientos separados. Las instrucciones para agentes están en [AGENTS.md](AGENTS.md).

## Instalar e iniciar

Requisitos: Python 3.12, acceso a los motores de los hitos 4 a 9 y Docker Compose
si se ejecutan esas bases en contenedores. La API no crea ni borra bases al iniciar.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock  # versiones verificadas; requirements.txt define mínimos
cp .env.example .env
# Editar .env con las conexiones y credenciales locales, sin versionarlo.
python scripts/verificar_conectividad.py
bash scripts/iniciar_api.sh
```

Swagger UI: <http://localhost:8000/docs>. Contrato dinámico:
<http://localhost:8000/openapi.json>. Copia versionada:
[openapi/openapi.yaml](openapi/openapi.yaml).

La colección de Postman está en [postman_collection.json](postman_collection.json).
Importala desde **Import → File**; la variable `baseUrl` apunta por defecto a
`http://localhost:8000`.

Para fixture y planteles, iniciar las bases normales del proyecto:

```bash
docker compose up -d mongo redis
bash scripts/iniciar_api.sh
```

MongoDB se publica solo en loopback en `MONGO_PORT` (27018 por defecto);
`MONGO_URI` en `.env` debe usar el mismo puerto. Se conserva el volumen
`fixture2030_fixture2030_data`. Redis usa `REDIS_PORT` (6380 por defecto).
Estas dos bases no requieren otro clon ni ejecutan cargas de datos al iniciar.

Los montajes para importar MongoDB son opcionales, mediante
`docker-compose.imports.yaml` y `TP_DATA_DIR` (por defecto `../idd-2-tp`).
Los otros motores todavía usan scripts y datos del repositorio de hitos anteriores.
Ver [conectividad y configuración](docs/conectividad_y_configuracion.md).

## Probar y reproducir

```bash
bash scripts/ejecutar_pruebas.sh       # suite sin motores, integra contratos ASGI y dobles de drivers
bash scripts/ejemplos_curl.sh          # requests HTTP reales contra la API iniciada
python scripts/exportar_openapi.py    # regenerar contrato después de cambiar rutas/schemas
```

La suite normal solo recolecta `tests/unit` y no inicia motores ni cargas. Para
probar fuentes reales, seleccionar explícitamente `tests/integration` y usar bases
dedicadas para pruebas, con datos representativos:

```bash
LIVE_MODULES=mongodb,neo4j,cassandra,redis,influxdb,iris IRIS_TEST_ID=1 \
  python -m pytest tests/integration -v
```

Se puede seleccionar un subconjunto en `LIVE_MODULES`. Los tests habilitados fallan
si la fuente cae o no devuelve los datos esperados. Ver [tests/README.md](tests/README.md).

## Contrato y decisiones

- [Seguimiento de los casos del MVP](docs/casos_de_uso.md).
- [Rutas e identificadores de la API actual](docs/api_actual.md).
- [Arquitectura y adaptadores](docs/arquitectura_y_adaptadores.md).
- [Validación, errores e idempotencia](docs/contratos_y_errores.md).
- [Pruebas y evidencia disponible](laboratorio/pruebas_y_evidencia.md).

Cassandra vuelve a exponer el feed de comentarios de solo lectura. IRIS recupera la vista de partidos y eventos por ID persistente (`/objetos/partidos/{id}`). Ver `tests/fixtures/README.md` para cargar sus esquemas. IRIS se levanta por separado; sus credenciales y namespace se configuran con `IRIS_*`.
La única mutación HTTP es invalidar una sesión (DELETE idempotente).

`/live` comprueba el proceso sin consultar motores. `/ready` devuelve 200 si todas las fuentes responden a su ping o 503 si alguna falla. `/health` devuelve 200 con `up/down` por fuente aun si alguna está caída. Los endpoints
de datos responden 503 ante una dependencia inaccesible o con identidad/permisos/contexto rechazados, y 504 ante timeout. Los detalles del driver no
se publican en respuestas ni logs.

## Detener

Ctrl+C detiene Uvicorn y cierra los adaptadores. Desde el backend, `docker compose stop`
detiene las bases y conserva los datos. No se necesita eliminar volúmenes.

## Alcance de validación

Las pruebas con dobles verifican contratos y errores, pero no prueban conectividad.
La evidencia separa esas pruebas de las ejecutadas contra motores reales. No se
presentan cifras de capacidad productiva ni se afirma validación de fuentes no ejecutadas.

La práctica de laboratorio y su evidencia están en [laboratorio/](laboratorio/README.md).

## Fixture Mundial 2030 (requerimiento 1)

`GET /fixture` lista los partidos por fecha/hora UTC y código, con equipos, fase,
estado y resultado. Usa MongoDB `partidos` y Redis opcional, con
`FIXTURE_CACHE_TTL_SECONDS=5`. No requiere que Neo4j o Influx estén disponibles.
`/ready` continúa comprobando las seis fuentes del Hito 11.

El seed reproducible de 127 partidos y el escenario de tres estados están incluidos
en este backend: [guía del fixture](docs/fixture.md). El detalle
`/partidos/{codigo}` sigue usando Neo4j y todavía no incorpora los estados del listado.

## Catálogo para consultar planteles

`GET /equipos` complementa la consulta de planteles: devuelve `{items: [{codigo, nombre}]}`
con todas las selecciones de MongoDB `equipos`, ordenadas por nombre y código
(según la colación predeterminada de MongoDB). No recibe filtros ni paginación
y es independiente del fixture. Vacío: 200 con `items: []`. Fallos MongoDB:
503/504 con los códigos comunes de dependencia. No usa caché.
El plantel se consulta con `GET /jugadores?equipo=ARG`, posición opcional y `limit`/`skip`.

## Laboratorio

Procedimientos, planes y evidencia se conservan fuera de `docs/`, en
[laboratorio/](laboratorio/README.md) y [hito-12/](hito-12/README.md).
Solo se ejecutan por pedido explícito; no forman parte del arranque ni de los tests habituales.

## Inicialización del Mundial simulado de 64 selecciones

`scripts/cargar_jugadores.py` carga explícitamente 1.248 jugadores de 2026 (48 planteles),
sin importar resultados. `scripts/cargar_inicio_mundial.py` inicializa el catálogo
de 64 selecciones y los 127 partidos sintéticos 2030: 96 cruces de grupos definidos
y 31 eliminatorias con equipos por definir. Todos quedan próximos y sin marcador.
Los otros 16 equipos quedan sin jugadores. No se inventan rankings: `rankingFifa`
en la ficha de equipo admite `null` cuando no hay información. La carga inicial
rechaza bases con partidos existentes; nunca reinicia un torneo en curso.
Las cargas se ejecutan por pedido explícito y no forman parte del arranque ni los tests.
