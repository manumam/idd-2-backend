# Pruebas

Ejecutar `.venv/bin/python -m pytest -q` para contratos y dobles de drivers.
Las pruebas reales se habilitan con `LIVE_MODULES=mongodb,neo4j,redis,influxdb`.
Preparar los datos según `docs/hito_11/README.md`; las pruebas de integración exigen datos no vacíos.
El test de DELETE escribe y elimina únicamente `sesion:SES-HITO10TEST`.
Cassandra y sus pruebas se retiraron en el Hito 11.
