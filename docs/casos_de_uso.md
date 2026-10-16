# Casos de uso y mapa de endpoints (Hito 10)

API REST del Fixture Mundial 2030. Cada endpoint responde a un caso de uso, usa una
fuente justificada y ejecuta una operación fija: el cliente nunca envía consultas,
colecciones, tablas ni Cypher.

Los identificadores son los de cada módulo anterior, sin traducir:

| Entidad | Formato | Ejemplo | Fuente de verdad |
| ------- | ------- | ------- | ---------------- |
| Equipo | 3 letras mayúsculas | `ARG` | MongoDB (Hito 4) |
| Jugador | `<equipo>-<dorsal>` | `ARG-10` | MongoDB (Hito 4) |
| Usuario | `U` + 6 dígitos | `U000001` | MongoDB (Hito 4, `usuarios`) |
| Partido | `P-` + 3 dígitos | `P-001` | Neo4j (Hito 5) |
| Sede | `S-` + 2 dígitos | `S-04` | Neo4j (Hito 5) |
| Sesión | `SES-` + 4 dígitos | `SES-0001` | Redis (Hito 7) |
| Evento | `E-` + 4 dígitos | `E-0001` | Neo4j (Hito 5) |

## 1. Casos de uso

Consumidor de todos los casos: la aplicación cliente del Fixture (web o móvil) y quien
prueba la API desde Swagger UI o Postman. Todos los datos son sintéticos. En la columna
"Si la fuente cae", `503` siempre lleva el código `<FUENTE>_UNAVAILABLE` (sección 3).

| # | Caso de uso | Entrada | Fuente | Éxito | Si no existe | Tipo |
| - | ----------- | ------- | ------ | ----- | ------------ | ---- |
| 1 | Ver la ficha de un equipo | `codigo` | MongoDB `equipos` | 200 con la ficha | 404 `EQUIPO_NO_ENCONTRADO` | Lectura |
| 2 | Listar el plantel de un equipo, opcionalmente por posición | `equipo` (obligatorio), `posicion`, `limit`, `skip` | MongoDB `jugadores` | 200 con una página ordenada por dorsal (puede ser vacía) | Filtro sin resultados: 200 vacío. No se valida que `equipo` exista | Lectura |
| 3 | Ver un jugador | `codigo` | MongoDB `jugadores` | 200 con el jugador | 404 `JUGADOR_NO_ENCONTRADO` | Lectura |
| 4 | Ver un partido (fase, fecha, sede, equipos) | `codigo` | Neo4j | 200 con el partido | 404 `PARTIDO_NO_ENCONTRADO` | Lectura |
| 5 | Ver los eventos de un partido con sus protagonistas | `codigo`, `limit` | Neo4j | 200 con los eventos | Partido inexistente: 404 `PARTIDO_NO_ENCONTRADO`. Partido sin eventos: 200 con lista vacía | Lectura |
| 6 | Goleadores de una confederación en una sede (consulta multi-salto del Hito 5) | `codigo` (sede), `confederacion`, `limit` | Neo4j | 200 con los goleadores (puede ser vacío) | Sede inexistente: 404 `SEDE_NO_ENCONTRADA` | Lectura |
| 7 | Leer comentarios de un partido en una ventana de 5 minutos | `codigo`, `bloque`, `limit`, `cursor` | Cassandra `comentarios_feed` | 200 con la página y `siguienteCursor` | Ventana sin comentarios o partido que no existe: 200 vacío | Lectura |
| 8 | Publicar un comentario | — | Cassandra | Pendiente (sección 4) | Pendiente | Escritura |
| 9 | Consultar una sesión | `sesionId` | Redis | 200 con los datos de la sesión y su TTL restante | 404 `SESION_NO_VIGENTE` (ausente o expirada) | Lectura |
| 10 | Cerrar una sesión | `sesionId` | Redis | 204 | 204 (ya estaba cerrada) | Invalidación |
| 11 | Ver estadísticas de un partido en un intervalo | `codigo`, `desde`, `hasta`, `equipo`, `ventana` | InfluxDB `estadisticas_partido` | 200 con los puntos | Intervalo sin puntos o partido que no existe: 200 vacío | Lectura |
| 12 | Ver el estado de las dependencias | — | Todas | 200 con el estado de cada fuente (`up` o `down`) | — | Lectura |

Decisión sobre los casos 7 y 11: no se consulta Neo4j para comprobar que el partido
existe. Cada fuente responde por sus propios datos y el hito no exige que una request
cruce varias bases. Por eso un `P-xxx` con formato válido y sin datos devuelve 200
vacío. Si el partido sí existe y la fuente no tiene datos, el resultado es el mismo.

Decisión sobre el caso 12: `/health` es una ruta de diagnóstico propia del grupo (no
la pide el enunciado) y responde 200 aunque una fuente esté caída, marcándola `down`.
Ningún endpoint de datos esconde una caída con 200.

IRIS (Hito 9) queda fuera: es una demostración aislada y no es fuente de verdad de
ninguna entidad. Se documenta como fuente no incluida en la API.

## 2. Mapa de endpoints

| Método | Ruta | Fuente | Caso |
| ------ | ---- | ------ | ---- |
| GET | `/equipos/{codigo}` | MongoDB | 1 |
| GET | `/jugadores` | MongoDB | 2 |
| GET | `/jugadores/{codigo}` | MongoDB | 3 |
| GET | `/partidos/{codigo}` | Neo4j | 4 |
| GET | `/partidos/{codigo}/eventos` | Neo4j | 5 |
| GET | `/sedes/{codigo}/goleadores` | Neo4j | 6 |
| GET | `/partidos/{codigo}/comentarios` | Cassandra | 7 |
| GET | `/sesiones/{sesionId}` | Redis | 9 |
| DELETE | `/sesiones/{sesionId}` | Redis | 10 |
| GET | `/partidos/{codigo}/estadisticas` | InfluxDB | 11 |
| GET | `/health` | Todas | 12 |

El caso 8 (`POST /partidos/{codigo}/comentarios`) se agrega al mapa cuando se defina.

## 3. Reglas comunes

- **Validación antes de consultar.** Formato de cada identificador (tabla de arriba),
  fechas con formato `AAAA-MM-DDThh:mm:ssZ` en hora UTC, `desde` anterior a `hasta`,
  `limit` entre 1 y un máximo fijo (100), `skip` entre 0 y 1000. Una entrada inválida devuelve 400 sin tocar la base.
- **Ausencia vs. vacío vs. caída.** Un recurso inexistente es 404. Una consulta válida
  sin resultados es 200 con lista vacía. Una dependencia caída o lenta es 503; nunca
  se devuelve una lista vacía para esconder una falla.
- **Formato de error único:** `{ "code", "message", "requestId" }`. No incluye
  credenciales, consultas ni trazas.

| HTTP | `code` | Cuándo |
| ---- | ------ | ------ |
| 400 | `VALIDACION_INVALIDA` | Parámetro de ruta, query o cuerpo ausente o con formato incorrecto |
| 404 | `EQUIPO_NO_ENCONTRADO`, `JUGADOR_NO_ENCONTRADO`, `PARTIDO_NO_ENCONTRADO`, `SEDE_NO_ENCONTRADA`, `SESION_NO_VIGENTE` | Recurso inexistente |
| 404 | `RUTA_NO_ENCONTRADA` | La ruta no existe en la API |
| 405 | `METODO_NO_PERMITIDO` | La ruta existe pero no admite ese método |
| 4xx | `ERROR_HTTP` | Otro error HTTP del framework no contemplado arriba |
| 409 | — | Reservado para conflictos de negocio. Ningún endpoint actual lo produce (la escritura del caso 8 está pendiente) |
| 500 | `ERROR_INTERNO` | Error inesperado; el detalle queda solo en los logs |
| 503 | `MONGODB_UNAVAILABLE`, `NEO4J_UNAVAILABLE`, `CASSANDRA_UNAVAILABLE`, `REDIS_UNAVAILABLE`, `INFLUXDB_UNAVAILABLE` | Fuente caída o con timeout |

- **Identificador de request.** Encabezado `X-Request-Id` (nombre elegido por el grupo,
  el enunciado solo pide un identificador de request o correlación). Se genera si el
  cliente no lo envía, vuelve en la respuesta como `requestId` y aparece en cada
  línea de log.
- **Límites y paginación.** MongoDB: `limit` y `skip`. Neo4j: `LIMIT` en cada consulta.
  Cassandra: `limit` y cursor sobre la partición. InfluxDB: intervalo máximo y tope de
  puntos por respuesta.
- **Respuestas con proyección.** Cada endpoint devuelve solo los campos de la sección 5;
  no se devuelven documentos internos completos.

## 4. Decisiones abiertas

1. **Caso 8, escribir un comentario.** La tabla del Hito 6 mantiene el comentario en
   varias tablas y contadores. Antes de implementarlo hay que definir qué tablas
   escribe, qué pasa si el partido o el usuario no existen, y cómo se comporta una
   escritura repetida (el enunciado exige documentarlo y probarlo). Hasta entonces el
   endpoint no existe.
2. **Cassandra, ventana y cursor.** Se pagina dentro de la partición `(partido_id,
   bloque_temporal)` usando `comentario_id` (clave de clustering) como cursor. El
   cliente indica el `bloque`: un instante UTC múltiplo de 5 minutos (si no lo es,
   400). No se consulta entre ventanas.
3. **InfluxDB.** El máximo de intervalo, el máximo de puntos y los valores de `ventana`
   se fijan al leer los datos reales cargados. `equipo` filtra por el tag `equipo_id`.
   La sede no es entrada (Influx documenta `S-01` a `S-16`; Neo4j tiene hasta `S-20`).

## 5. Respuestas por caso

| Caso | Campos |
| ---- | ------ |
| 1 | `codigo`, `nombre`, `confederacion`, `grupo`, `rankingFifa`, `directorTecnico` (puede ser `null`), `anfitrion` |
| 2 | `items[]` con `codigo`, `nombre`, `apellido`, `dorsal`, `posicion`, `equipo` (`codigo`, `nombre`); `limit`, `skip` |
| 3 | los de `items[]` del caso 2, más `fechaNacimiento`, `club` y `capitan` (estos dos pueden ser `null`) |
| 4 | `codigo`, `fase`, `grupo` (`null` fuera de la fase de grupos), `fecha`, `sede` (`codigo`, `nombre`, `ciudad`), `local`, `visitante` (`codigo`, `nombre`) |
| 5 | `partido` (código), `items[]` con `codigo` (`E-0001`), `tipo`, `minuto`, `protagonistas[]` (`jugador` con `codigo` y `nombre`, `rol`) |
| 6 | `sede` (código), `confederacion`, `items[]` con `jugador` (`codigo`, `nombre`), `equipo` (`codigo`, `nombre`), `partido` (código), `minuto` |
| 7 | `partido`, `bloque`, `items[]` con `comentarioId`, `usuarioId`, `nombreUsuario`, `idioma`, `texto`, `estadoModeracion`; `siguienteCursor` (`null` si no hay más) |
| 9 | `sesionId`, `usuarioId`, `nombreUsuario`, `rol`, `idioma`, `ultimoAcceso`, `acciones`, `ttlSegundos` (no se exponen `ubicacion`, `dispositivo`, `ip_publica` ni `tipo_conexion`) |
| 11 | `partido`, `desde`, `hasta`, `ventana`, `items[]` con `hora`, `equipo` (código, tag `equipo_id`), `posesionPct`, `tiros` y `pasesIntervalo`. Con `ventana`, cada medida se agrega según su tipo: promedio de `posesion_pct`, máximo de `tiros_acumulados` y suma de `pases_intervalo` (nunca `SUM` sobre las dos primeras) |
| 12 | `estado` por fuente: `mongodb`, `neo4j`, `cassandra`, `redis`, `influxdb` |

Los nombres exactos de los campos quedan fijados en el contrato OpenAPI, que debe
coincidir con esta tabla.
