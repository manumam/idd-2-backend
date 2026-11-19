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
- **Caché del fixture:** `fixture_cache=hit` o `fixture_cache=miss`.

Las duraciones HTTP y de adaptador miden tramos distintos; no deben sumarse como
si fueran operaciones independientes. Los logs no incluyen cuerpos, parámetros
de consulta, credenciales ni mensajes nativos del driver. Los errores inesperados
registran su tipo, sin devolver el detalle al consumidor.

## Salud del proceso y dependencias

| Ruta | Comprobación actual | Respuesta |
| --- | --- | --- |
| `/live` | Proceso, sin consultar bases | 200 con `{estado: alive}` |
| `/ready` | Ping de MongoDB e InfluxDB | `{listo, estado}`; 200 si ambas responden, 503 si alguna falla |
| `/health` | Estado individual de MongoDB, Redis e InfluxDB | 200 con `{estado: {...}}`, incluso con fuentes `down` |

El 503 de `/ready` usa su schema de salud, no el cuerpo de error de negocio.
Un ping correcto no acredita esquemas ni datos; verificar también la ruta funcional.
Redis no participa de `/ready`: es caché opcional y, si cae, la API sigue respondiendo desde MongoDB.

## Pendiente respecto del MVP

Los logs y los chequeos de salud no completan la observabilidad propuesta.
Todavía falta exponer `/metrics`, integrar Prometheus y Grafana y sus exporters,
y medir latencia por percentiles, solicitudes por región, aciertos y fallos de
caché, antigüedad de datos y recursos según los lineamientos.

Los objetivos de disponibilidad, latencia y concurrencia son metas del diseño;
no son resultados demostrados por los logs actuales. Los procedimientos de carga
y la evidencia de evaluación se conservan fuera de `docs/`, en
[laboratorio](../laboratorio/README.md) y [hito-12](../hito-12/README.md).
