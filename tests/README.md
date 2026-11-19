# Pruebas

## Suite habitual, sin motores

```bash
bash scripts/ejecutar_pruebas.sh -q
# Equivalente:
.venv/bin/python -m pytest -q
```

`pytest.ini` limita la recolección predeterminada a `tests/unit`. Incluye contratos
HTTP ASGI, OpenAPI/Postman y dobles de drivers. No inicia Docker, no carga seeds
y no ejecuta el laboratorio, aunque existan variables de integración exportadas.

## Integración, solo por pedido explícito

Seleccionar `tests/integration` explícitamente y configurar bases de prueba
dedicadas. No usar las bases de desarrollo: hay pruebas con escrituras y borrados.
Estas pruebas no inician contenedores automáticamente.

```bash
LIVE_MODULES=mongodb,influxdb .venv/bin/python -m pytest tests/integration/test_live.py -q
```

`LIVE_MODULES` selecciona fuentes reales ya configuradas y cargadas; exige resultados
no vacíos. Admite `mongodb` e `influxdb`; Redis es caché y se prueba con la
integración del fixture.

La integración del fixture usa `FIXTURE_INTEGRATION=1`,
`FIXTURE_TEST_MONGO_URI` y `FIXTURE_TEST_REDIS_PORT`; crea y borra una base MongoDB
con nombre aleatorio y usa la clave de caché del fixture en el Redis indicado.
Usar motores dedicados. Ver [verificación del fixture](../laboratorio/verificacion-fixture.md) para el procedimiento manual.

## Evaluación histórica del Hito 11

`laboratorio/hito-11/README.md` documenta una evaluación independiente que inicia motores,
carga datos y genera evidencia. No es requisito para arrancar la app ni ejecutar
la suite habitual. No ejecutarla salvo pedido explícito de esa evaluación.
