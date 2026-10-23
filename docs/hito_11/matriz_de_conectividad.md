# Matriz de conectividad ejecutada

Cierre: 2026-10-23. Origen: Python y Uvicorn en notebook macOS arm64; motores en Compose aislado. Fechas UTC y duración por prueba en los JSON.

| Motor | Pruebas ejecutadas | Estado | Máxima duración observada por prueba |
| --- | --- | --- | --- |
| mongodb | 8 | Disponible | 11.85 ms |
| neo4j | 8 | Disponible | 43.14 ms |
| redis | 6 | Disponible | 5.99 ms |
| influxdb | 6 | Disponible | 9.60 ms |

28 verificaciones de configuración, resolución, TCP, protocolo, contexto/lectura y rutas HTTP aprobadas. El ping no se presenta como prueba de contexto.

## Evidencia del cierre

- [Diagnóstico completo](evidencia/completo.json).
- [11 casos HTTP negativos](evidencia/api_negativos.json): 5 HTTP/transporte reales y 6 simulaciones ASGI identificadas.
- [Falla y recuperación Redis](evidencia/falla_redis.json): detención real, sesión 200 → 503 → 200; /live siempre 200; /ready 200 → 503 → 200; /health conserva 200 con redis=down durante la caída. Volúmenes conservados.
- [Logs HTTP y adaptadores del servidor](evidencia/api_cierre.log) y [logs de simulaciones](evidencia/api_negativos.log), correlacionados por request ID.
- [Suite JUnit](evidencia/suite.xml): 78 aprobadas y 10 integraciones omitidas explícitamente en la suite normal.
- [Integración JUnit](evidencia/integracion.xml): las 10 integraciones reales aprobadas con los cuatro motores habilitados.
- [Versiones observadas e imágenes/digests](evidencia/versiones.json).

## Diagnóstico de incidencias

| Condición | Hipótesis | Prueba y resultado | Acción/recuperación |
| --- | --- | --- | --- |
| Influx falló en preparación inicial | El usuario del contenedor no podía escribir en /data | Logs de arranque indicaron Permission denied | Montar el volumen en /var/lib/influxdb3; carga y consultas repetidas con éxito |
| Redis detenido intencionalmente | No hay listener disponible para el adaptador | GET sesión 503; readiness 503; logs identifican Redis | Iniciar únicamente Redis y repetir; sesión y readiness 200 |
| API sin listener | No hay proceso HTTP en ese puerto reservado de prueba | Rechazo TCP, sin status ni request ID de servidor | Usar la URL del Uvicorn iniciado por el procedimiento |

## Limitaciones

El laboratorio no usa autenticación y publica puertos solo en loopback. Identidad, permisos y contexto se evalúan conjuntamente en las lecturas; sus rechazos y el timeout se verifican con simulaciones identificadas, no con ACL reales. Una lectura vacía puede ser válida y una clave ausente no demuestra expiración previa. No hay prueba de carga, SLA ni validación productiva. Cassandra se retiró por decisión del equipo e IRIS no está integrado: ambos fuera del alcance. Los tags Docker son mutables; la evidencia conserva sus digests. El único aviso de tests es la deprecación de TestClient/httpx, sin fallas.

Los resultados anteriores del Hito 10 están separados en ../evidencia/ y no se usan para afirmar disponibilidad en este entorno. Para repetir todo: `.venv/bin/python scripts/cerrar_hito11.py`.
