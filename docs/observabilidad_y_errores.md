# Observabilidad y errores

Este documento describe los mecanismos implementados para diagnosticar solicitudes
y fallas. El alcance y los objetivos de observabilidad del producto se definen en
los [lineamientos](lineamientos-entrega-demo.md); su cumplimiento se registra en el
[seguimiento del MVP](casos_de_uso.md). Los schemas y respuestas de cada endpoint
se consultan en [OpenAPI](../openapi/openapi.yaml) y [Postman](../postman_collection.json).

## Correlación de solicitudes

La API devuelve `X-Request-Id` en las respuestas. El cliente puede enviarlo con
entre 1 y 64 caracteres: letras ASCII, números o guiones. Si falta o su formato
es inválido, se genera un UUID. El mismo identificador aparece en los logs de la
solicitud y en el campo `requestId` de sus errores.

Para investigar una falla, conservar el identificador de la respuesta y buscar
`request_id` en los logs de la API y de los adaptadores.

## Formato de error

Los errores de negocio, validación y dependencias usan este cuerpo:

```json
{
  "code": "VALIDACION_INVALIDA",
  "message": "Parámetros inválidos: codigo.",
  "requestId": "demo-123"
}
```

El cliente debe interpretar `code` y el estado HTTP; `message` es una descripción
para personas. No se exponen credenciales, consultas ni trazas del servidor.

| HTTP | Significado | Código |
| --- | --- | --- |
| 400 | Parámetros inválidos; validación antes de consultar la base | `VALIDACION_INVALIDA` |
| 404 | Recurso inexistente | Código específico del recurso |
| 404 | Ruta inexistente | `RUTA_NO_ENCONTRADA` |
| 405 | Método no permitido para la ruta | `METODO_NO_PERMITIDO` |
| 500 | Error inesperado o consulta interna inválida | `ERROR_INTERNO` o `<FUENTE>_QUERY_FAILED` |
| 503 | Dependencia inaccesible o configuración rechazada | `<FUENTE>_UNAVAILABLE`, `_AUTHENTICATION_FAILED`, `_ACCESS_DENIED` o `_CONTEXT_UNAVAILABLE` |
| 504 | Tiempo de espera de una dependencia agotado | `<FUENTE>_TIMEOUT` |

`<FUENTE>` es `MONGODB` o `INFLUXDB`. Redis es caché opcional: sus fallas se
registran y la respuesta se obtiene de MongoDB, sin devolver códigos `REDIS_*`.

La identidad o los permisos rechazados por una base generan 503, no un error de
login del visitante. La clasificación usa tipos y códigos del driver; no publica
sus mensajes. Un timeout no identifica por sí solo si la causa es red, DNS o carga.

Una consulta válida sin resultados puede devolver 200 con una lista vacía según
su contrato. No debe usarse una respuesta vacía para ocultar una falla de la fuente.
Una respuesta reconstruida desde otra fuente o desde caché sigue las reglas de
resiliencia de la funcionalidad; por ejemplo, Redis es opcional para el fixture.

## Logs implementados

- **Solicitud HTTP:** `request_id`, método, ruta, estado HTTP y `duration_ms`.
- **Operación de adaptador:** `request_id`, dependencia, operación, resultado
  (`ok` o `error`) y `duration_ms`.
- **Falla de dependencia:** identificador, fuente, categoría y tipo de excepción.
- **Caché:** `<funcionalidad>_cache=hit` o `<funcionalidad>_cache=miss` (por ejemplo,
  `fixture_cache=miss`); una caché caída o inválida registra una advertencia.

Las duraciones HTTP y de adaptador miden tramos distintos; no deben sumarse como
si fueran operaciones independientes. Los logs no incluyen cuerpos, parámetros
de consulta, credenciales ni mensajes nativos del driver. Los errores inesperados
registran su tipo, sin devolver el detalle al consumidor.

## Salud del proceso y dependencias

| Ruta | Comprobación actual | Respuesta |
| --- | --- | --- |
| `/live` | Proceso, sin consultar bases | 200 con `{estado: alive}` |
| `/ready` | Ping de MongoDB | `{listo, estado}`; 200 si responde, 503 si falla |
| `/health` | Estado individual de MongoDB, Redis e InfluxDB | 200 con `{estado: {...}}`, incluso con fuentes `down` |

El 503 de `/ready` usa su schema de salud, no el cuerpo de error de negocio.
Un ping correcto no acredita esquemas ni datos; verificar también la ruta funcional.
Redis no participa de `/ready`: es caché opcional y, si cae, la API sigue respondiendo desde MongoDB.
InfluxDB tampoco: sin él siguen funcionando fixture, grupos, playoffs, partido, eventos,
alineaciones, estadísticas finales consolidadas y acumulados del jugador. Solo las rutas
que lo usan (estadísticas en vivo y serie temporal, mapa de calor, rendimiento en vivo)
responden 503 `INFLUXDB_UNAVAILABLE`; su estado sigue informado en `/health`.

`/health`, `/ready` y el scrape de `/metrics` comparten el último resultado de cada
fuente: como mucho se hace un ping por fuente cada 15 s. Si el último resultado de
una fuente tiene 15 s o más, se vuelve a hacer ping solo de esa fuente. Así la
frecuencia de los sondeos no genera una tormenta de conexiones contra las bases; a
cambio, el estado informado puede tener hasta 15 s de atraso.

## Métricas Prometheus

`GET /metrics` expone las métricas en formato Prometheus; no forma parte del
contrato OpenAPI y no se cuenta a sí misma. Las etiquetas usan conjuntos acotados:
nunca códigos de partido, claves de caché ni rutas sin plantilla.

| Métrica | Tipo | Etiquetas | Qué mide |
| --- | --- | --- | --- |
| `api_http_requests_total` | Counter | `ruta`, `metodo`, `status` | Requests atendidos; `ruta` es la plantilla (`/equipos/{codigo}`) o `sin_ruta` |
| `api_latency_seconds` | Histogram | `ruta` | Duración del request; incluye el bucket de 0,1 s del objetivo P95 |
| `api_cache_total` | Counter | `funcionalidad`, `resultado` | Lecturas de caché. `funcionalidad`: `fixture`, `partido`, `eventos`, `alineaciones`, `posiciones`, `playoffs`, `mapa_calor`. `resultado`: `hit`, `miss` o `error` (Redis caído o contenido inválido; se responde desde MongoDB) |
| `api_dependencia_seconds` | Histogram | `fuente`, `operacion` | Duración de cada operación de adaptador; `operacion` es el método del adaptador |
| `api_dependencia_errores_total` | Counter | `fuente`, `categoria` | Fallas de adaptador, una por operación, con la categoría de la tabla de errores (`timeout`, `authentication`, `authorization`, `context`, `query`, `resolution`, `connection_refused`, `unavailable`) |
| `api_dependencia_up` | Gauge | `fuente` | 1 si el último ping respondió, 0 si no |
| `api_dependencia_en_curso` | Gauge | `fuente` | Operaciones de adaptador en curso; sube al empezar y baja al terminar, aunque falle |
| `api_pool_conexiones_en_uso` | Gauge | `fuente` | Conexiones tomadas del pool y no devueltas; solo `mongodb` |

`fuente` es `mongodb`, `redis` o `influxdb`. Las fallas de Redis absorbidas por la
caché también se cuentan en `api_dependencia_errores_total`, aunque no lleguen al cliente.

`api_dependencia_up` usa el mismo resultado compartido con `/health` y `/ready`
(un ping por fuente cada 15 s como máximo).

`api_pool_conexiones_en_uso` usa los eventos de monitoreo del pool de pymongo.
Un valor sostenido cerca del máximo del pool indica requests esperando conexión
aunque la CPU esté baja. Redis e InfluxDB no tienen esta métrica: sus clientes no
exponen las conexiones en uso con una API pública en las versiones soportadas. Para
las tres fuentes, `api_dependencia_en_curso` muestra cuántas operaciones usan o
esperan cada base: si se mantiene alta mientras sube el P99, esa base es el cuello
de botella.

## Pendiente respecto del MVP

Prometheus hace scrape de la API, de los exporters de MongoDB, Redis y node y del
`/metrics` de InfluxDB, y envía las series a Grafana Cloud con la etiqueta `entorno`.
El dashboard War Room calcula los percentiles a partir de los histogramas (ver
[observabilidad](../observabilidad/README.md)). Todavía faltan, según los lineamientos:
solicitudes por región, antigüedad del dato servido y la prueba con MongoDB detenido.

La corrida de carga en entorno `prueba` (30 usuarios, 10 req/s) dio 0 errores y P95 de
16 ms ([resultados](../carga/resultados/prueba-20261119-1648/resumen.md)). Es una carga
modesta: confirma el SLO de latencia a ese nivel, no demuestra la concurrencia objetivo
del diseño. Procedimientos y evidencia anteriores siguen en
[laboratorio](../laboratorio/README.md) y [hito-12](../hito-12/README.md).
