# Verificación del fixture con motores dedicados

Ejecutar desde la raíz del backend, solo por pedido explícito.

## Verificación

Los tests habituales no levantan motores. Los comandos de integración siguientes
requieren un pedido explícito y usan contenedores temporales dedicados, separados
de la app y del laboratorio Hito 11.

```bash
.venv/bin/python -m pytest tests/unit -q

# Contenedores temporales independientes del laboratorio de la demo.
docker run --rm -d --name fixture-r1-mongo -p 127.0.0.1:47017:27017 --tmpfs /data/db mongo:7.0
docker run --rm -d --name fixture-r1-redis -p 127.0.0.1:46379:6379 redis:7.4-alpine
# Esperar a que MongoDB acepte conexiones.
FIXTURE_INTEGRATION=1 FIXTURE_TEST_MONGO_URI=mongodb://127.0.0.1:47017 \
FIXTURE_TEST_REDIS_PORT=46379 \
  .venv/bin/python -m pytest tests/integration/test_fixture_live.py -q
docker stop fixture-r1-mongo fixture-r1-redis
```

La integración crea y elimina una base con nombre aleatorio y usa la clave fija del
fixture en el Redis indicado: usar siempre un Redis aislado. Comprueba carga doble,
preservación/reinicio, validadores reales, índice, HTTP, expiración, invalidación y
conexiones reales inaccesibles sin detener otros servicios. La suite unitaria
incluye la validación del seed y los contratos OpenAPI/Postman.

Evidencia inicial: [validación del requerimiento 1](../laboratorio/evidencia/fixture-requerimiento-1.md).

