# Fixture 2030 — Backend e Hito 11

FastAPI con capas HTTP → servicios → adaptadores para MongoDB, Neo4j,
Cassandra, Redis, InfluxDB 3 e InterSystems IRIS.

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

- [Casos de uso, rutas e identificadores](docs/casos_de_uso.md).
- [Arquitectura y adaptadores](docs/arquitectura_y_adaptadores.md).
- [Validación, errores e idempotencia](docs/contratos_y_errores.md).
- [Pruebas y evidencia disponible](docs/pruebas_y_evidencia.md).

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

Casos HTTP negativos del Hito 11: `.venv/bin/python scripts/prueba_api_negativos.py` con la API del laboratorio iniciada. Los casos de driver simulados y los casos HTTP reales se identifican en la evidencia.

## Fixture Mundial 2030 (requerimiento 1)

`GET /fixture` lista los partidos por fecha/hora UTC y código, con equipos, fase,
estado y resultado. Usa MongoDB `partidos` y Redis opcional, con
`FIXTURE_CACHE_TTL_SECONDS=5`. No requiere que Neo4j o Influx estén disponibles.
`/ready` continúa comprobando las seis fuentes del Hito 11.

El seed reproducible de 127 partidos y el escenario de tres estados están incluidos
en este backend: [guía del fixture](docs/fixture.md). El detalle
`/partidos/{codigo}` sigue usando Neo4j y todavía no incorpora los estados del listado.

## Catálogo para consultar planteles

`GET /equipos` complementa el caso 2: devuelve `{items: [{codigo, nombre}]}`
con todas las selecciones de MongoDB `equipos`, ordenadas por nombre y código
(según la colación predeterminada de MongoDB). No recibe filtros ni paginación
y es independiente del fixture. Vacío: 200 con `items: []`. Fallos MongoDB:
503/504 con los códigos comunes de dependencia. No usa caché.
El plantel se consulta con `GET /jugadores?equipo=ARG`, posición opcional y `limit`/`skip`.

## Evaluaciones de hitos (solo por pedido explícito)

El [laboratorio del Hito 11](docs/hito_11/README.md), su Compose,
`config/hito11.env.example`, `scripts/preparar_lab.py` y `scripts/cerrar_hito11.py`
son exclusivamente para reproducir esa evaluación. El entorno de `hito-12/` también
es independiente. No son el arranque de la app ni parte de los tests habituales.
No ejecutarlos para resolver falta de datos o de conexión del frontend.

## Inicialización del Mundial simulado de 64 selecciones

`scripts/cargar_jugadores.py` carga explícitamente 1.248 jugadores de 2026 (48 planteles),
sin importar resultados. `scripts/cargar_inicio_mundial.py` inicializa el catálogo
de 64 selecciones y los 127 partidos sintéticos 2030: 96 cruces de grupos definidos
y 31 eliminatorias con equipos por definir. Todos quedan próximos y sin marcador.
Los otros 16 equipos quedan sin jugadores. No se inventan rankings: `rankingFifa`
en la ficha de equipo admite `null` cuando no hay información. La carga inicial
rechaza bases con partidos existentes; nunca reinicia un torneo en curso.
Las cargas se ejecutan por pedido explícito y no forman parte del arranque ni los tests.
