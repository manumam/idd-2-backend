# Contratos, errores e idempotencia

La fuente del contrato es `app.main.app.openapi()`. `scripts/exportar_openapi.py`
genera YAML sin conectarse a las bases; un test compara el archivo con `/openapi.json`.
Swagger incluye schemas, ejemplos de parámetros, respuestas y `X-Request-Id`.
No hay autenticación HTTP en este laboratorio; las credenciales pertenecen a las conexiones.

Cada error tiene exclusivamente `code`, `message`, `requestId`. Se admite un
`X-Request-Id` de 1 a 64 letras, números o guiones; si falta o es inválido se genera
un UUID. El mismo valor se devuelve en el encabezado de todas las respuestas.

| HTTP | Semántica |
| --- | --- |
| 200 | Recurso o lista válida; lista vacía permitida donde corresponda |
| 204 | Sesión invalidada, también si ya estaba ausente |
| 400 | `VALIDACION_INVALIDA`: formato, valor, límite, fecha, ventana o cursor inválidos |
| 404 | Código de ausencia específico |
| 404 / 405 | `RUTA_NO_ENCONTRADA` / `METODO_NO_PERMITIDO` |
| 500 | `ERROR_INTERNO`: error inesperado seguro |
| 503 | `<FUENTE>_UNAVAILABLE`: dependencia inaccesible, autenticación fallida o timeout |

No se documenta 409 en las rutas actuales porque no hay una operación con conflicto
de negocio. No se implementan altas ni transiciones de objetos, ni POST de comentarios.
El DELETE de Redis es idempotente; no se cuentan invalidaciones ni se reintenta la
operación en el cliente Redis. Un fallo de red produce 503 y el consumidor puede
repetir DELETE: una respuesta perdida no genera duplicados.

La validación ocurre antes del adaptador: códigos por módulo, `limit` entre 1 y 100
(eventos hasta 200), `skip` entre 0 y 1000, instantes UTC con sufijo Z y calendario
válido, `desde < hasta`, ventanas estadísticas `1m/5m`. Cassandra exige bloque exacto
múltiplo de cinco minutos y UUID v1 para el cursor. El código Cassandra no prueba
existencia del partido en Neo4j. Influx tampoco cruza bases para validar existencia.

La agregación Influx se hace sobre puntos limitados: promedio de posesión, máximo de
tiros acumulados y suma de pases por intervalo. Ventanas alineadas al reloj UTC;
la primera y la última pueden ser parciales. Se presupone el modelo del Hito 8:
dos equipos por partido y un punto cada cinco segundos (2880 puntos en dos horas).
El tope 5000 es protección; datos que violen esa cardinalidad pueden truncarse y
requieren revisar el contrato antes de usarlos como estadísticas completas.
