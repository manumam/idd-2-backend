# Casos de uso y mapa de endpoints (vigente en Hito 11)

API REST del Fixture Mundial 2030. Cada endpoint responde a un caso de uso, usa una
fuente justificada y ejecuta una operación fija: el cliente nunca envía consultas,
colecciones, tablas ni Cypher.

Los identificadores son los de cada módulo anterior, sin traducir:

| Entidad | Formato | Ejemplo | Fuente de verdad |
| ------- | ------- | ------- | ---------------- |
| Equipo | 3 letras mayúsculas | `ARG` | MongoDB (Hito 4) |
| Jugador | `<equipo>-<dorsal>` | `ARG-10` | MongoDB (Hito 4) |
| Usuario | `U` + 6 dígitos | `U000001` | MongoDB (Hito 4, `usuarios`) |
| Partido operativo | `P-` + 3 dígitos | `P-001` | Neo4j (Hito 5) |
| Sede | `S-` + 2 dígitos | `S-04` | Neo4j (Hito 5) |
| Sesión | `SES-` + letras mayúsculas o dígitos | `SES-0001`, `SES-DEMO` | Redis (Hito 7) |
| Evento | `E-` + 4 dígitos | `E-0001` | Neo4j (Hito 5) |

## 1. Casos de uso

Consumidor de todos los casos: la aplicación cliente del Fixture (web o móvil) y quien
prueba la API desde Swagger UI o Postman. Todos los datos son sintéticos. En la columna
"Si la fuente cae", `503` distingue disponibilidad, identidad, permisos y contexto; timeout usa `504` (sección 3).

| # | Caso de uso | Entrada | Fuente | Éxito | Si no existe | Tipo |
| - | ----------- | ------- | ------ | ----- | ------------ | ---- |
| 1 | Ver la ficha de un equipo | `codigo` | MongoDB `equipos` | 200 con la ficha | 404 `EQUIPO_NO_ENCONTRADO` | Lectura |
| 2 | Listar el plantel de un equipo, opcionalmente por posición | `equipo` (obligatorio), `posicion`, `limit`, `skip` | MongoDB `jugadores` | 200 con una página ordenada por dorsal (puede ser vacía) | Filtro sin resultados: 200 vacío. No se valida que `equipo` exista | Lectura |
| 3 | Ver un jugador | `codigo` | MongoDB `jugadores` | 200 con el jugador | 404 `JUGADOR_NO_ENCONTRADO` | Lectura |
| 4 | Ver un partido (fase, fecha, sede, equipos) | `codigo` | Neo4j | 200 con el partido | 404 `PARTIDO_NO_ENCONTRADO` | Lectura |
| 5 | Ver los eventos de un partido con sus protagonistas | `codigo`, `limit` | Neo4j | 200 con los eventos | Partido inexistente: 404 `PARTIDO_NO_ENCONTRADO`. Partido sin eventos: 200 con lista vacía | Lectura |
| 6 | Goleadores de una confederación en una sede (consulta multi-salto del Hito 5) | `codigo` (sede), `confederacion`, `limit` | Neo4j | 200 con los goleadores (puede ser vacío) | Sede inexistente: 404 `SEDE_NO_ENCONTRADA` | Lectura |
| 9 | Consultar una sesión | `sesionId` | Redis | 200 con los datos de la sesión y su TTL restante | 404 `SESION_NO_VIGENTE` (ausente o expirada) | Lectura |
| 10 | Cerrar una sesión | `sesionId` | Redis | 204 | 204 (ya estaba cerrada) | Invalidación |
| 11 | Ver estadísticas de un partido en un intervalo | `codigo`, `desde`, `hasta`, `equipo`, `ventana` | InfluxDB `estadisticas_partido` | 200 con los puntos | Intervalo sin puntos o partido que no existe: 200 vacío | Lectura |
| 12 | Ver el estado de las dependencias | — | Todas | 200 con el estado de cada fuente (`up` o `down`) | — | Lectura |

Decisión sobre el caso 11: no se consulta Neo4j para comprobar que el partido
existe. Cada fuente responde por sus propios datos y el hito no exige que una request
cruce varias bases. Por eso un `P-xxx` con formato válido y sin datos devuelve 200
vacío. Si el partido sí existe y la fuente no tiene datos, el resultado es el mismo.

Decisión sobre el caso 12: `/health` es una ruta de diagnóstico propia del grupo (no
la pide el enunciado) y responde 200 aunque una fuente esté caída, marcándola `down`.
Ningún endpoint de datos esconde una caída con 200.

## 2. Mapa de endpoints

| Método | Ruta | Fuente | Caso |
| ------ | ---- | ------ | ---- |
| GET | `/equipos/{codigo}` | MongoDB | 1 |
| GET | `/jugadores` | MongoDB | 2 |
| GET | `/jugadores/{codigo}` | MongoDB | 3 |
| GET | `/partidos/{codigo}` | Neo4j | 4 |
| GET | `/partidos/{codigo}/eventos` | Neo4j | 5 |
| GET | `/sedes/{codigo}/goleadores` | Neo4j | 6 |
| GET | `/sesiones/{sesionId}` | Redis | 9 |
| DELETE | `/sesiones/{sesionId}` | Redis | 10 |
| GET | `/partidos/{codigo}/estadisticas` | InfluxDB | 11 |
| GET | `/health` | Todas | 12 |
| GET | `/live` | Ninguna | Liveness |
| GET | `/ready` | Todas | Readiness de conectividad |

Los casos 7 y 8 de comentarios se retiraron junto con Cassandra.

## 3. Reglas comunes

- **Validación antes de consultar.** Formato de cada identificador (tabla de arriba),
  fechas con formato `AAAA-MM-DDThh:mm:ssZ` en hora UTC, `desde` anterior a `hasta`,
  `limit` entre 1 y un máximo fijo (100), `skip` entre 0 y 1000. Una entrada inválida devuelve 400 sin tocar la base.
- **Ausencia vs. vacío vs. caída.** Un recurso inexistente es 404. Una consulta válida
  sin resultados es 200 con lista vacía. Una dependencia caída es 503 y un timeout es 504; nunca
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
| 409 | — | Reservado para conflictos de negocio. Ningún endpoint actual lo produce (no se implementa el caso 8) |
| 500 | `ERROR_INTERNO` | Error inesperado; el detalle queda solo en los logs |
| 503 | `MONGODB_UNAVAILABLE`, `NEO4J_UNAVAILABLE`, `REDIS_UNAVAILABLE`, `INFLUXDB_UNAVAILABLE` | Fuente caída; identidad, permisos o contexto rechazados |

- **Identificador de request.** Encabezado `X-Request-Id` (nombre elegido por el grupo,
  el enunciado solo pide un identificador de request o correlación). Se genera si el
  cliente no lo envía, vuelve en el encabezado de respuesta y como `requestId` en los errores, y aparece en cada
  línea de log.
- **Límites y paginación.** MongoDB: `limit` y `skip`. Neo4j: `LIMIT` en cada consulta (eventos: 1 a 200, por defecto 50; goleadores: 1 a 100, por defecto 50).
  InfluxDB limita el intervalo y devuelve hasta 5.000 filas por consulta.
- **Respuestas con proyección.** Cada endpoint devuelve solo los campos de la sección 5;
  no se devuelven documentos internos completos.

## 4. Decisiones de alcance y límites

1. **Retiro de Cassandra.** En Hito 11 se elimina el módulo de comentarios y su ruta HTTP por decisión del equipo.
3. **InfluxDB.** La API lee `estadisticas_partido` de la base `fixture2030_resumen`
   (un punto cada 5 s por equipo). Sin `ventana` devuelve puntos crudos y el intervalo
   máximo es de 30 minutos; con `ventana` (`1m` o `5m`) el máximo es de 2 horas. `desde`
   es inclusivo y `hasta` exclusivo, con formato `AAAA-MM-DDThh:mm:ssZ` en hora UTC.
   Las ventanas se alinean al reloj (minuto o múltiplo de 5), no a `desde`: si `desde` no
   está alineado, la primera ventana es parcial. `equipo` filtra por el tag `equipo_id`. La sede no es entrada (Influx documenta
   `S-01` a `S-16`; Neo4j tiene hasta `S-20`). Un tope de 5.000 filas por consulta
   protege la respuesta.
4. **Timeout de consulta en Neo4j.** Cada Cypher usa `Query(timeout=DB_TIMEOUT_SECONDS)`;
   también hay límite de conexión y adquisición. Una request puede ejecutar varias
   consultas: el timeout no es un presupuesto total HTTP.

## 5. Respuestas por caso

| Caso | Campos |
| ---- | ------ |
| 1 | `codigo`, `nombre`, `confederacion`, `grupo`, `rankingFifa`, `directorTecnico` (puede ser `null`), `anfitrion` |
| 2 | `items[]` con `codigo`, `nombre`, `apellido`, `dorsal`, `posicion`, `equipo` (`codigo`, `nombre`); `limit`, `skip` |
| 3 | los de `items[]` del caso 2, más `fechaNacimiento`, `club` y `capitan` (estos dos pueden ser `null`) |
| 4 | `codigo`, `fase`, `grupo` (`null` fuera de la fase de grupos), `fecha`, `sede` (`codigo`, `nombre`, `ciudad`), `local`, `visitante` (`codigo`, `nombre`) |
| 5 | `partido` (código), `items[]` con `codigo` (`E-0001`), `tipo`, `minuto`, `protagonistas[]` (`jugador` con `codigo` y `nombre`, `rol`) |
| 6 | `sede` (código), `confederacion`, `items[]` con `jugador` (`codigo`, `nombre`), `equipo` (`codigo`, `nombre`), `partido` (código), `minuto` |
| 9 | `sesionId`, `usuarioId`, `nombreUsuario`, `rol`, `idioma`, `ultimoAcceso`, `acciones`, `ttlSegundos` (todos menos `sesionId` pueden ser `null` si el hash no los tiene; `ttlSegundos` es `null` si la clave no vence; no se exponen `ubicacion`, `dispositivo`, `ip_publica` ni `tipo_conexion`) |
| 11 | `partido`, `desde`, `hasta`, `ventana`, `items[]` con `hora`, `equipo` (código, tag `equipo_id`), `posesionPct`, `tiros` y `pasesIntervalo`. Con `ventana`, cada medida se agrega según su tipo: promedio de `posesion_pct`, máximo de `tiros_acumulados` y suma de `pases_intervalo` (nunca `SUM` sobre las dos primeras) |
| 12 | `estado` por fuente: `mongodb`, `neo4j`, `redis`, `influxdb` |

Los nombres exactos de los campos quedan fijados en el contrato OpenAPI, que debe
coincidir con esta tabla.

En Hito 11, un timeout de dependencia devuelve 504 `<FUENTE>_TIMEOUT`. Los códigos 503 distinguen UNAVAILABLE, AUTHENTICATION_FAILED, ACCESS_DENIED y CONTEXT_UNAVAILABLE. Ver `contratos_y_errores.md`.
