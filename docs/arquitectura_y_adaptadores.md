# Arquitectura y adaptadores

Cada router valida ruta/query con FastAPI y delega al servicio. El servicio aplica
reglas (ventanas, paginación, ausencia) y construye schemas Pydantic. El adaptador
conoce el driver, contexto, consultas fijas, límites y transformación de errores.
Ninguna ruta acepta nombres de tablas, Cypher, SQL o comandos arbitrarios.

| Fuente | Contexto y patrón de acceso | Límites y recursos |
| --- | --- | --- |
| MongoDB | `MONGO_DATABASE`; `_id` o `equipo._id`, proyecciones de campos | `limit <= 100`, `skip <= 1000`; pool de MongoClient |
| Neo4j | `NEO4J_DATABASE`; Cypher con parámetros, relaciones dirigidas | eventos <= 200, goleadores <= 100; sesión por consulta, driver compartido |
| Redis | `REDIS_DB`; clave `sesion:{sesionId}` | hash y TTL; no se expone IP/dispositivo; sin reintentos del cliente |
| InfluxDB 3 | `INFLUX_DATABASE`; SQL con parámetros por partido, tiempo y equipo | `[desde,hasta)`, 30 min crudos / 2 h agregados; 5000 puntos como protección |

`DB_TIMEOUT_SECONDS` (mayor que cero, máximo 60) controla conexión/socket en Mongo y
Redis, conexión/adquisición y consulta en Neo4j,
conexión/lectura HTTP en Influx.
No es un presupuesto único por request: una operación con varias consultas puede
acumular varios timeouts. Influx usa el timeout de Requests por fase, no un deadline
total de descarga. Los clientes/sistemas remotos pueden introducir latencia adicional.

Los adaptadores registran request ID, dependencia, operación, resultado y duración.
El middleware registra método, ruta, status y duración HTTP. No se registran queries,
parámetros, cuerpos, URIs ni mensajes del driver. Errores inesperados registran solo
su tipo. `/health` evalúa fuentes en paralelo y los recursos se cierran al detener la API.

`/live` no accede a drivers; `/ready` y `/health` consultan pings en paralelo bajo demanda. Las lecturas profundas de contexto están en el CLI, no en cada request de negocio. Ver `hito_11/health_readiness.md`.
