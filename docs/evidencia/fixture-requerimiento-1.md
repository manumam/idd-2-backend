# Verificación del requerimiento 1: fixture

Se verificó con Python 3.12, MongoDB 7.0 y Redis 7.4 Alpine en contenedores
temporales aislados, puertos 47017 y 46379, sin modificar las bases existentes.

| Comprobación | Resultado |
| --- | --- |
| Suite normal del backend | 116 pruebas aprobadas; 19 de integración omitidas por ser opt-in y verificadas por separado cuando corresponde. |
| Validación del seed sin motores | 7 pruebas aprobadas; 127 partidos válidos. |
| Integración del fixture, corrida final | 6 pruebas aprobadas con MongoDB/Redis reales. |
| CLI de carga con escenario | 127 insertados, 0 actualizados, 0 rechazados, en `fixture_r1_evidence` temporal. |
| Estados del escenario | `proximo`, `en_vivo`, `finalizado`. |
| OpenAPI y Postman | Operaciones y parámetros coinciden; comprobado por la suite. |
| Índice de orden real | Plan `FETCH → IXSCAN`, `idx_partidos_fecha_codigo`, sin etapa `SORT`. |
| Redis inaccesible | HTTP ASGI 200 desde MongoDB; también tolera el fallo al guardar caché. |
| MongoDB inaccesible con caché | HTTP ASGI 200. |
| MongoDB inaccesible sin caché | HTTP ASGI 504 `MONGODB_TIMEOUT`, encabezado e identificador de error coincidentes; no guarda el error en Redis. |

La integración comprueba además la carga doble sin duplicados, conservación de un
marcador modificado y reinicio explícito, validadores del motor, orden estable,
caché inválida, TTL real de 1 segundo e invalidación. Los fallos reales se provocan
mediante sockets TCP reservados sin listener; no se detienen bases para esas pruebas.

Medición puntual de extremo a extremo vía HTTP ASGI, con drivers y bases reales:
**45,792 ms** con caché fría y **2,764 ms** con caché caliente para los 127 partidos.
En esa medición se configuró TTL de 60 segundos; el valor predeterminado de la
implementación es 5 segundos y la expiración se probó por separado con 1 segundo.
Son dos lecturas locales, sin prueba de carga ni red HTTP externa: no demuestran
un P95 ni la capacidad global del sistema.

La suite emite una advertencia de deprecación existente de Starlette/TestClient
sobre httpx; no impide las verificaciones. La guía [fixture.md](../fixture.md)
contiene los comandos para reproducirlas. No se implementó un simulador de partidos.
