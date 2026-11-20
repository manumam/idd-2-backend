# Fixture 2030 — Backend

API del Mundial 2030. El MVP usa MongoDB para partidos y eventos, Redis para
caché e InfluxDB para series temporales. Los [lineamientos](docs/lineamientos-entrega-demo.md),
[casos de uso](docs/casos-de-uso-fixture.md) y [modelo técnico](docs/modelo-tecnico-demo.md)
definen el alcance; el [seguimiento](docs/casos_de_uso.md) registra lo implementado y pendiente.

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

Redis es una instancia dedicada a caché: solo guarda copias reconstruibles desde
MongoDB o InfluxDB. Por eso usa `--maxmemory 256mb` con `--maxmemory-policy allkeys-lru`:
al llegar al límite desaloja (evicción) las claves usadas hace más tiempo, tengan o
no TTL, y conserva las que se están leyendo, como las del partido en vivo. Las
políticas `volatile-*` solo desalojan claves con TTL y, si no hay ninguna, se
comportan como `noeviction` (rechazan escrituras nuevas). La expiración por TTL
sigue acotando la antigüedad de cada clave; la evicción solo actúa por falta de
memoria. Redis no persiste (sin AOF y con `--save ""`, sin snapshots RDB) porque
es una caché reconstruible: tras un reinicio casi todas las claves ya habrían
vencido, y persistir no convierte a Redis en fuente de verdad (Clase 8). Estos
cambios se aplican al recrear el contenedor de Redis (`docker compose up -d redis`);
un contenedor ya iniciado conserva la configuración anterior.

`docker-compose.yaml` define MongoDB, Redis e InfluxDB. Los montajes para importar
MongoDB son opcionales, mediante `docker-compose.imports.yaml` y `TP_DATA_DIR`
(por defecto `../idd-2-tp`). InfluxDB todavía monta scripts del repositorio de hitos
anteriores. Los volúmenes locales de Neo4j y Cassandra que ya existan no se borran;
pueden eliminarse manualmente si ya no se necesitan.

### Configuración local

Usar `.venv` y `.env` desde la raíz del backend. Las variables exportadas tienen
prioridad sobre el archivo. `scripts/iniciar_api.sh` respeta `API_HOST` y `API_PORT`;
el frontend debe usar el mismo destino en `API_PROXY_TARGET`.

| Variables | Configuración local habitual |
| --- | --- |
| `MONGO_URI`, `MONGO_DATABASE` | `mongodb://127.0.0.1:27018`, `fixture2030` |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | `127.0.0.1`, `6380`, `0` |
| `INFLUX_URL`, `INFLUX_DATABASE`, `INFLUX_DATABASE_EN_VIVO` | `http://127.0.0.1:8181`, `fixture2030_resumen`, `fixture2030_en_vivo` |
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
LIVE_MODULES=mongodb,influxdb python -m pytest tests/integration -v
```

Se puede seleccionar un subconjunto en `LIVE_MODULES`. Los tests habilitados fallan
si la fuente cae o no devuelve los datos esperados. Ver [tests/README.md](tests/README.md).

## Contrato y decisiones

- [Seguimiento de los casos del MVP](docs/casos_de_uso.md).
- [Observabilidad y errores](docs/observabilidad_y_errores.md).
- [Monitoreo con Prometheus y Grafana Cloud](observabilidad/README.md).
- [Pruebas y evidencia disponible](laboratorio/pruebas_y_evidencia.md).

`/live` comprueba el proceso sin consultar motores. `/ready` devuelve 200 si MongoDB e InfluxDB responden a su ping o 503 si alguno falla; Redis es caché opcional y no se evalúa. `/health` devuelve 200 con `up/down` para MongoDB, Redis e InfluxDB aun si alguna está caída. Ambas reusan el último ping de cada fuente durante 15 s, así que el estado puede tener hasta 15 s de atraso. Los endpoints
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
`FIXTURE_CACHE_TTL_SECONDS=5`. No requiere que InfluxDB esté disponible.

El dataset de 127 partidos y el escenario de tres estados están incluidos en
`data/fixture/`: CSV, calendario UTC, escenario y validador. Los datos son sintéticos.
El detalle `GET /partidos/{codigo}` usa MongoDB y Redis opcional. Devuelve
`fecha_hora` UTC, sede, equipos, fase/grupo, estado, resultado con tanda separada y
`reloj` (período, minuto absoluto de juego y adicional). Conserva `fecha` como fecha UTC.
El reloj es una instantánea persistida, sin extrapolar desde el horario; `null`
significa que aún no fue informado. Representa entretiempo, pausas, prórroga y tanda.
La ingesta/simulador que lo avance automáticamente sigue pendiente (caso 7).
La ficha `/partido.html?codigo=P-001` del frontend se abre desde fixture, grupos y
playoffs y se actualiza cada 15 s mientras está visible, hasta finalizar.
Los cruces reutilizan la resolución del cuadro; los resultados con participantes
obsoletos no se muestran como propios y llevan `requiere_revision`.

El detalle usa Cache-Aside con clave `partido:v2:{codigo}`: lee Redis primero; ante
miss consulta MongoDB (y el cuadro en eliminatorias) y guarda con
`FIXTURE_CACHE_TTL_SECONDS`. Un hit no consulta MongoDB. Redis caído o contenido
inválido no bloquean la lectura. Ver [invalidación](#invalidación-de-partido-eventos-alineaciones-posiciones-y-cuadro).
El validador de `data/fixture/partidos-validator.json` admite `reloj` opcional.
La carga explícita de fixture aplica ese validador y conserva reloj/estado/resultado
existentes; solo `--reiniciar-escenario` los reemplaza. No se migra ni carga al arrancar.
Una base creada con el validador anterior requiere aplicar explícitamente el nuevo
validador antes de escribir el campo `reloj`; la lectura sigue funcionando sin él.

### Caché del fixture actual

Cache-Aside con clave `fixture:v1:todos` y TTL configurable entre 1 y 3600 segundos.
Un fallo de Redis permite reconstruir desde MongoDB; una caché válida permite
responder con MongoDB inaccesible. Sin caché válida, el fallo de MongoDB se informa
con los códigos de error de la API. Un fallo al guardar caché no invalida la lectura.

Los cargadores intentan invalidar la caché. La futura ingesta debe invocar
`app.services.fixture_service.invalidar_fixture` después de confirmar cambios.
El TTL limita la antigüedad cuando falla la invalidación; no hay transacción
distribuida ni garantía de lectura monótona.

### Invalidación de partido, eventos, alineaciones, posiciones y cuadro

Detalle, eventos, alineaciones, posiciones y cuadro usan el mismo Cache-Aside y TTL
del fixture, con claves derivadas solo de la solicitud:

| Ruta | Clave |
| --- | --- |
| `GET /partidos/{codigo}` | `partido:v2:{codigo}` |
| `GET /partidos/{codigo}/eventos` | `eventos:v2:{codigo}:{limit}:{skip}` |
| `GET /partidos/{codigo}/alineaciones` | `alineaciones:v2:{codigo}` |
| `GET /grupos/{id}/posiciones` | `grupos:v2:{id}` |
| `GET /playoffs` | `playoffs:v2:todos` |

Redis no sabe qué cambió en MongoDB: la aplicación borra las claves después de cada
escritura confirmada. Un tick del simulador (`aplicar_tick`) invalida el fixture y
`cache_partidos.invalidar_resultado`: detalle, alineaciones y todas las páginas de
eventos del partido (`SCAN` con `eventos:v2:{codigo}:*` + `DEL`), posiciones de su
grupo, el cuadro y las claves de todos los cruces eliminatorios, porque un resultado
puede cambiar sus participantes. Las cargas de fixture, grupos y cuadro borran con
`SCAN` los cinco namespaces; la de alineaciones borra las claves de sus partidos.
Las claves `v1` anteriores vencen por TTL. Una escritura directa en MongoDB, sin
estos escritores, se ve recién al vencer el TTL.

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
Redis es opcional, con Cache-Aside en `grupos:v2:{id}`; cierres, correcciones y
cargas de grupos invalidan la tabla ([detalle](#invalidación-de-partido-eventos-alineaciones-posiciones-y-cuadro)).

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
El cuadro se calcula desde MongoDB ante un miss y se cachea en `playoffs:v2:todos`
con Redis opcional; cualquier resultado o carga lo invalida. Los grupos incompletos conservan la descripción de sus plazas.
Los resultados con participantes obsoletos o sin desempate válido requieren revisión
y no propagan ganador. El escritor de resultados debe registrar ambos equipos;
GET no sobrescribe resultados ni asigna participantes en el fixture persistido.

En el frontend: `/playoffs.html`; cada tarjeta abre la ficha central del encuentro.
`?partido=P-097` conserva el resumen navegable del camino.
El detalle central del caso 5 está implementado en `/partido.html?codigo=…`,
con sede, reloj persistido opcional y enlace al camino del cruce. Tests locales: resolución completa,
penales, cierres, correcciones en cascada, dependencias inválidas y fallos de caché.
La validación con motores reales requiere `.env` apuntando al MongoDB del proyecto
(27018 por defecto); no conectar al MongoDB de otro proyecto en 27017.

## Alineaciones (caso 6)

`GET /partidos/{codigo}/alineaciones` consulta titulares y suplentes desde MongoDB,
con Redis opcional (`alineaciones:v2:{codigo}`). El frontend las muestra dentro del partido y conserva el contexto
al abrir una ficha de jugador. La carga por encuentro es explícita y conserva las
convocatorias existentes salvo `--reemplazar`; no se ejecuta durante el arranque.
Ver [contrato, carga y límites con el caso 9](docs/alineaciones.md).

Para probar con Argentina, el seed `scripts/cargar_alineaciones_argentina.py` carga
convocatorias simuladas de once titulares y quince suplentes en P-002, P-051 y P-083.
Requiere el fixture y sus 26 jugadores existentes. Conserva alineaciones y resultados
y no se ejecuta durante el arranque. Ver [instrucciones](docs/alineaciones.md).

Las alineaciones admiten una formación opcional con arquero y líneas de titulares.
La página muestra el esquema sobre una cancha y permite alternar equipo. El seed
de Argentina incorpora un 4–3–3 simulado; ver [modelo y orientación](docs/alineaciones.md).

## Cronología del partido (caso 7)

`GET /partidos/{codigo}/eventos?limit=50&skip=0` lee eventos embebidos en MongoDB,
con caché Redis opcional (`eventos:v2:{codigo}:{limit}:{skip}`); ya no depende de Neo4j. Devuelve goles,
autogoles, tarjetas y cambios con equipo, minuto/adicional y protagonistas,
además de `total`, `siguiente_skip`, `estado`, `resultado` y `reloj`. El frontend
actualiza cronología y marcador cada cinco segundos y conserva el histórico al
finalizar, con Nothing Design oscuro.

El simulador `scripts/simular_partido.py` genera planes desde catálogos existentes
y los reproduce únicamente mediante ejecución explícita. No carga datos al
arrancar ni reinicia escenarios. Ver [contrato, uso y límites](docs/eventos.md).

## Mapa de calor de un jugador (caso 10)

`GET /partidos/{codigo}/mapa-calor?jugador_id=ARG-10&desde_minuto=0&hasta_minuto=45`
devuelve cuántas muestras de posición del jugador caen en cada celda de 5 × 5 m
(cancha de 105 × 68 m, 21 × 14 celdas) y una intensidad de 0 a 1 relativa a la
celda más ocupada; las celdas sin muestras se omiten. InfluxDB calcula la celda
y cuenta: no se promedian coordenadas.

- Minutos desde el inicio del tracking del partido, inicio inclusivo y fin
  exclusivo, entre 0 y 120. Sin rango: desde 0 hasta el minuto del reloj + 1
  (120 si no hay reloj). `desde_minuto ≥ hasta_minuto` o fuera de 0–120: 400.
- El inicio es `inicio_tracking` del partido en MongoDB si existe (UTC, lo
  registra la simulación) o, si no, `fecha_hora` del calendario (datos precargados).
- En vivo lee `tracking_jugador` de `fixture2030_en_vivo` (`fuente: en_vivo`).
  Finalizado suma `ocupacion_jugador_minuto` de `fixture2030_resumen` por celda,
  con las ventanas que empiezan dentro del rango (`fuente: historico`); si el partido
  todavía no se materializó, usa el crudo mientras exista (`fuente: en_vivo`).
  Partido próximo: 200 con celdas vacías, sin consultar InfluxDB.
- Partido inexistente o jugador ajeno a las dos selecciones: 404. InfluxDB caído: 503;
  timeout: 504.
- Cache-Aside en Redis con clave `mapa_calor:v2:{partido}:{jugador}:{desde}:{hasta}`
  (`todo` si falta un límite): TTL 5 s si `fuente: en_vivo` (el polling del front) y
  1 h si `historico`. El partido próximo no se cachea. Redis caído o contenido
  inválido: se calcula igual. La materialización borra `mapa_calor:v2:{partido}:*`.
## Comparación de equipos (caso 8)

`GET /partidos/{codigo}/estadisticas` sin fechas compara posesión, tiros, pases,
goles y tarjetas. Combina MongoDB e Influx en vivo y lee los finales consolidados
desde MongoDB, con caché Redis opcional y estados explícitos. Con `desde` y `hasta`
conserva la serie temporal histórica. El detalle del frontend incorpora «Cara a cara»
con actualización cada cinco segundos y Nothing Design oscuro.

El plan de `scripts/simular_estadisticas.py` permite seed final o reproducción
acelerada de un partido próximo: usa catálogos existentes, cinco eventos ficticios
y 2.162 muestras temporales; termina 2–0 para el local. Crear/validar el plan no
cambia datos deportivos. Ejecutarlo requiere autorizar el partido concreto; no
reinicia encuentros ni borra datos. Ver [comandos, límites y cierre](docs/estadisticas.md).
El seed final autorizado de P-001 fue verificado con MongoDB e Influx propios
y a través del proxy del frontend: 2–0, cinco eventos y estadísticas completas.
La lectura final funcionó con Influx detenido y Redis inaccesible en un lector
aislado. La reproducción en vivo se cubre con adaptadores en memoria; no se
presenta como ejecución real.

Influx del caso 8 puede iniciarse sin `idd-2-tp` con
`docker compose -f docker-compose.estadisticas.yaml up -d` y
`.venv/bin/python scripts/preparar_influx_local.py`. Usa volumen propio y token
local, conserva la configuración anterior en una copia privada y no carga datos
deportivos. Ver [configuración y verificación](docs/estadisticas.md).

### Tracking y estadísticas del caso 8

El simulador `simular_estadisticas.py` escribe posesión, tiros acumulados y cantidades de pases por intervalo en `estadisticas_partido`; los eventos deportivos se guardan en MongoDB. No genera posiciones ni trayectorias de jugadores o pelota. Para un mapa de calor con contenido se necesita una carga de tracking independiente y, para conservarlo, materializar la ocupación antes de que venza el crudo. Sin muestras, tabla o base de tracking creada, el mapa devuelve 200 con `celdas: []`; no inventa posiciones. Los fallos de autenticación, permisos, conexión y consultas inválidas siguen devolviendo errores.

Para la demo, `scripts/simular_en_vivo.py` reutiliza ese plan y avanza MongoDB e Influx al mismo ritmo
(factor 10: 90 minutos en unos 9): escribe tracking de jugadores y pelota a 1 Hz anclado en
`inicio_tracking`, las muestras del caso 8 y la actividad de usuarios. Solo se ejecuta explícitamente
y no es reanudable. Ver [comandos, anclaje y límites](docs/simulador_en_vivo.md).
Para la demo desde el front, `POST /demo/simulacion` lo lanza como proceso aparte y
`GET /demo/simulacion` informa su estado y el próximo partido simulable.
Ver [desde el front](docs/simulador_en_vivo.md#desde-el-front).

## Rendimiento individual (caso 9)

`GET /partidos/{codigo}/jugadores/{jugador_codigo}/estadisticas` consulta goles,
asistencias, tarjetas, distancia en metros y velocidad máxima en km/h. Durante el
vivo combina eventos MongoDB y tracking confirmado de InfluxDB a 1 Hz; los finales
consolidados se leen solo desde MongoDB. `GET /jugadores/{codigo}/estadisticas`
agrega por encuentro sin doble conteo y sin leer Influx. La velocidad conserva el
máximo; distancias y contadores se suman. Una métrica incompleta queda null.

La ficha desde las alineaciones conserva el partido, muestra rendimiento y
acumulados con Nothing Design oscuro y refresca cada cinco segundos durante el
vivo/cierre pendiente. Redis es opcional, con TTL de cinco segundos y claves
versionadas por entradas. Los escritores deportivos invalidan también rendimiento
y acumulados; los cargadores generales borran esos namespaces con `SCAN`.

`INFLUX_TRACKING_DATABASE=fixture2030_en_vivo` selecciona la base de tracking;
`INFLUX_DATABASE` sigue seleccionando las estadísticas de equipos. El registro de
cobertura, la actualización del validador de una base existente y la consolidación
son operaciones explícitas con `scripts/consolidar_jugadores.py`; no cargan tracking
ni se ejecutan al arrancar. Los resúmenes individuales se publican por generación
completa mediante CAS, con huella para invalidar correcciones. Ver
[contratos, comandos y límites](docs/rendimiento.md). Tests locales y lectura
deportiva real de URU-21/P-001 por proxy verificados; la ejecución del cierre
físico con motores reales sigue pendiente.
