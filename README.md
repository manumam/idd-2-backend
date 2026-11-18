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

Requisitos: Python 3.12 y acceso a las bases de las rutas que se utilicen; Docker
Compose si se ejecutan esas bases en contenedores. La API no crea ni borra bases al iniciar.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock  # versiones verificadas; requirements.txt define mínimos
[ -f .env ] || cp .env.example .env
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

### Configuración local

Usar `.venv` y `.env` desde la raíz del backend. Las variables exportadas tienen
prioridad sobre el archivo. `scripts/iniciar_api.sh` respeta `API_HOST` y `API_PORT`;
el frontend debe usar el mismo destino en `API_PROXY_TARGET`.

| Variables | Configuración local habitual |
| --- | --- |
| `MONGO_URI`, `MONGO_DATABASE` | `mongodb://127.0.0.1:27018`, `fixture2030` |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | `127.0.0.1`, `6380`, `0` |
| `INFLUX_URL`, `INFLUX_DATABASE` | `http://127.0.0.1:8181`, `fixture2030_resumen` |
| `DB_TIMEOUT_SECONDS` | `5` |

Los puertos deben coincidir con `.env` y los mappings de Compose. Influx admite
`INFLUX_TOKEN` o el archivo local `.influxdb3-token`. Las variables de las rutas
históricas están en `.env.example`; no son nuevas dependencias del MVP.
No versionar credenciales ni sobrescribir configuraciones locales existentes.

Antes de iniciar bases, revisar contenedores existentes y puertos libres. No usar
bases de otro proyecto ni detener sus contenedores. Desde otro contenedor,
`localhost` identifica ese contenedor: usar el nombre del servicio y puerto interno.
Si existe un proxy HTTP, incluir `localhost,127.0.0.1` en `NO_PROXY` para conexiones
locales. `/live` verifica el proceso; comprobar datos mediante las rutas funcionales,
ya que un ping de salud no garantiza que existan esquemas ni datos.

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
- [Observabilidad y errores](docs/observabilidad_y_errores.md).
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

El dataset de 127 partidos y el escenario de tres estados están incluidos en
`data/fixture/`: CSV, calendario UTC, escenario y validador. Los datos son sintéticos.
El detalle `/partidos/{codigo}` sigue usando Neo4j y todavía no incorpora los estados
del listado; esa migración figura en el seguimiento del MVP.

### Caché del fixture actual

Cache-Aside con clave `fixture:v1:todos` y TTL configurable entre 1 y 3600 segundos.
Un fallo de Redis permite reconstruir desde MongoDB; una caché válida permite
responder con MongoDB inaccesible. Sin caché válida, el fallo de MongoDB se informa
con los códigos de error de la API. Un fallo al guardar caché no invalida la lectura.

Los cargadores intentan invalidar la caché. La futura ingesta debe invocar
`app.services.fixture_service.invalidar_fixture` después de confirmar cambios.
El TTL limita la antigüedad cuando falla la invalidación; no hay transacción
distribuida ni garantía de lectura monótona.

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

## Carga de datos

Las cargas requieren un pedido explícito y se ejecutan desde la raíz del backend,
con las bases de desarrollo del proyecto. No forman parte del arranque ni de los
tests. Usar el mismo `.env` que la API; nunca sustituir una base sin datos por la de
otro proyecto ni iniciar el laboratorio como alternativa.

### Inicializar un Mundial sin partidos disputados

`scripts/cargar_jugadores.py` carga explícitamente 1.248 jugadores de 2026 (48 planteles),
sin importar resultados. `scripts/cargar_inicio_mundial.py` inicializa el catálogo
de 64 selecciones y los 127 partidos sintéticos 2030: 96 cruces de grupos definidos
y 31 eliminatorias con equipos por definir. Todos quedan próximos y sin marcador.
Los otros 16 equipos quedan sin jugadores. No se inventan rankings: `rankingFifa`
en la ficha de equipo admite `null` cuando no hay información. La carga inicial
rechaza bases con partidos existentes; nunca reinicia un torneo en curso.
Las cargas se ejecutan por pedido explícito y no forman parte del arranque ni los tests.

Primero se puede validar sin acceder a las bases:

```bash
.venv/bin/python scripts/cargar_jugadores.py --solo-validar
.venv/bin/python scripts/cargar_inicio_mundial.py --solo-validar
```

Cuando se solicite la carga inicial:

```bash
.venv/bin/python scripts/cargar_jugadores.py
.venv/bin/python scripts/cargar_inicio_mundial.py
```

El inicializador conserva fichas existentes y deja las plazas eliminatorias sin resolver.

### Cargar o actualizar el fixture versionado

El cargador del fixture es una alternativa para reproducir el dataset incluido:
valida antes de escribir y hace upserts por código, sin borrar colecciones.
La carga normal preserva estados y resultados existentes.

```bash
.venv/bin/python scripts/cargar_fixture.py --solo-validar
# Solo cuando se solicite cargar o actualizar los datos:
.venv/bin/python scripts/cargar_fixture.py
```

Este cargador usa `.env` por defecto, admite `--env-file` y respeta las variables
exportadas. No necesita otro clon ni Neo4j. Reproduce una instantánea; no es un
simulador que haga avanzar el torneo.

### Reemplazar explícitamente estados y resultados

Solo ante un pedido de reinicio, `--reiniciar-escenario` permite reemplazarlos:

```bash
# Aplicar los estados iniciales del calendario (todos próximos):
.venv/bin/python scripts/cargar_fixture.py --reiniciar-escenario

# Aplicar el escenario de ejemplo con próximos, en vivo y finalizados:
.venv/bin/python scripts/cargar_fixture.py --reiniciar-escenario \
  --escenario data/fixture/fixture-escenario-demo.json
```

Estas operaciones reemplazan marcadores existentes. La carga normal no lo hace.

## Grupos y posiciones (requerimiento 3)

`GET /grupos` lista los grupos y sus reglas. `GET /grupos/A/posiciones` devuelve
PJ, PG, PE, PP, GF, GC, DG, puntos, orden y partidos del grupo. Solo cuentan
resultados finalizados; los goles de tanda se excluyen. Desempates de la demo:
puntos, diferencia de gol, goles a favor y orden explícito del dataset.
`completa` requiere todos los cruces entre participantes finalizados.
Redis es opcional; la clave versionada por contenido evita reutilizar tablas
anteriores después de cierres, correcciones o cambios de reglas.

La sección **Grupos** del frontend permite seleccionar un grupo y desplegar sus
partidos, con actualización cada 15 segundos y estados de carga, vacío y error.
La ficha central del encuentro sigue perteneciendo al requisito 5.

Preparación explícita (fuera del arranque; no ejecutada como parte de este cambio):

```bash
.venv/bin/python scripts/cargar_grupos.py --solo-validar
.venv/bin/python scripts/cargar_grupos.py
```

La carga valida que el catálogo MongoDB coincida con el dataset versionado de
64 selecciones/16 grupos. Inserta únicamente grupos ausentes y crea un índice
por grupo/fase/fecha/código; conserva grupos existentes, equipos y resultados.
Requiere la configuración normal `.env` o variables exportadas. Comprobar que
`MONGO_URI` apunte al MongoDB **del proyecto** (puerto habitual 27018), nunca a
una base de otro proyecto. Reiniciar la API con `bash scripts/iniciar_api.sh`
para incorporar las rutas nuevas; el script no usa recarga automática.

Verificación local: tests unitarios de clasificación, contrato HTTP y fallos de
fuentes, validación del dataset, tests del frontend y compilación TypeScript/Vite.
Estos controles no sustituyen la comprobación con MongoDB/Redis reales.

### Cuadro de playoffs (caso 4)

`GET /playoffs` devuelve las cinco rondas y 31 cruces, con origen de plazas,
participantes resueltos, resultados, ganador, siguiente encuentro y
`requiere_revision`. Sin cuadro cargado responde `{"items": []}`.

La carga es explícita y aditiva; no se ejecuta al arrancar ni modifica partidos:

```bash
.venv/bin/python scripts/cargar_playoffs.py --solo-validar
# Con MongoDB del proyecto correctamente configurado y fixture/grupos cargados:
.venv/bin/python scripts/cargar_playoffs.py
```

Las reglas de `data/fixture/cruces.json` clasifican los dos primeros de cada grupo,
con cruces A1–B2, B1–A2, etc.; no representan un reglamento oficial de 2030.
El cuadro se recalcula desde MongoDB y se cachea por versión de todas sus entradas
en Redis opcional. Los grupos incompletos conservan la descripción de sus plazas.
Los resultados con participantes obsoletos o sin desempate válido requieren revisión
y no propagan ganador. El escritor de resultados debe registrar ambos equipos;
GET no sobrescribe resultados ni asigna participantes en el fixture persistido.

En el frontend: `/playoffs.html`; cada cruce abre un resumen navegable del encuentro.
El detalle completo del caso 5 sigue pendiente. Tests locales: resolución completa,
penales, cierres, correcciones en cascada, dependencias inválidas y fallos de caché.
La validación con motores reales requiere `.env` apuntando al MongoDB del proyecto
(27018 por defecto); no conectar al MongoDB de otro proyecto en 27017.
