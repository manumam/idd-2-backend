# Pruebas

`python -m pytest -q` ejecuta la suite unitaria y omite integración salvo que
`LIVE_MODULES` habilite fuentes. Usa HTTP ASGI con TestClient: verifica validación
antes del adaptador, éxitos por módulo, ausencia, listas vacías, dependencia caída,
TTL/expiración, invalidación repetida, cursores, agregaciones y contrato exportado.
Los dobles no constituyen evidencia de conectividad.

`tests/unit/test_adapters.py` verifica parámetros CQL/SQL/Cypher, traducción de fallas
nativas, timeouts, relación padre-hijo IRIS, privacidad y logs.

Para integración, iniciar servicios y cargar los modelos de hitos previos:

```bash
LIVE_MODULES=mongodb,neo4j,cassandra,redis,influxdb,iris IRIS_TEST_ID=1 \
  python -m pytest tests/integration -v --junitxml=docs/evidencia/integracion_local.xml
```

Se pueden elegir fuentes individualmente. Habilitar una fuente hace que su error
sea un fallo, no un skip. Los fixtures esperados son ARG, ARG-10, P-001, S-04 con
goles CONMEBOL, SES-DEMO vigente, dos comentarios ARG-ESP-20300624 en el bloque
2030-06-24T20:05:00Z y estadísticas P-001 entre 20:00 y 20:05 UTC del mismo día.
Ajustar los ejemplos/tests si las cargas elegidas tienen otros identificadores.
IRIS usa `IRIS_TEST_ID`, no el código de negocio del partido.

Las lecturas no mutan datos; el test de invalidación crea y elimina una clave
exclusiva `sesion:SES-HITO10TEST`. No hay pruebas de escritura de comentarios
porque ese endpoint no existe. No ejecutar benchmarks de millones de requests.

Para una falla real, detener solo la fuente del módulo en un entorno de laboratorio,
ejecutar su cURL y comprobar 503 con `requestId`; restaurar con `docker compose start`.
Registrar entorno, comando, resultado y fecha sin secretos. El test unitario de
503 simula la excepción y cubre el contrato aun cuando no hay motores disponibles.
