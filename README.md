# Hito 10 — API REST integrada del Fixture 2030

FastAPI con capas HTTP → servicios → adaptadores para MongoDB, Neo4j, Cassandra,
Redis, InfluxDB 3 e InterSystems IRIS. Rama de entrega: `Hito-10`.

## Instalar e iniciar

Requisitos: Python 3.12, acceso a los motores de los hitos 4 a 9 y Docker Compose
si se ejecutan esas bases en contenedores. La API no crea ni borra bases al iniciar.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock  # versiones verificadas; requirements.txt define mínimos
cp .env.example .env
# Editar .env con las conexiones y credenciales locales, sin versionarlo.
python scripts/verificar_conectividad.py
bash scripts/iniciar_api.sh
```

Swagger UI: <http://localhost:8000/docs>. Contrato dinámico:
<http://localhost:8000/openapi.json>. Copia versionada:
[openapi/openapi.yaml](openapi/openapi.yaml).

Las bases y sus esquemas se levantan desde el [repositorio de los hitos anteriores](https://github.com/mateolewinzon/idd-2-tp).
Ver [conectividad y configuración](docs/conectividad_y_configuracion.md) para el
orden de carga, puertos, hosts en Docker y datos necesarios.

## Probar y reproducir

```bash
bash scripts/ejecutar_pruebas.sh       # suite sin motores, integra contratos ASGI y dobles de drivers
bash scripts/ejemplos_curl.sh          # requests HTTP reales contra la API iniciada
python scripts/exportar_openapi.py    # regenerar contrato después de cambiar rutas/schemas
```

La suite normal incluye tests de integración desactivados explícitamente. Para
probar las fuentes reales cargadas con datos representativos:

```bash
LIVE_MODULES=mongodb,neo4j,cassandra,redis,influxdb,iris IRIS_TEST_ID=1 \
  python -m pytest tests/integration -v
```

Se puede seleccionar un subconjunto en `LIVE_MODULES`. Los tests habilitados fallan
si la fuente cae o no devuelve los datos esperados. La lectura de Cassandra requiere
dos comentarios en el bloque indicado para probar el cursor. La prueba Redis crea
y borra exclusivamente `sesion:SES-HITO10TEST`. Ver [tests/README.md](tests/README.md).

## Contrato y decisiones

- [Casos de uso, rutas e identificadores](docs/casos_de_uso.md).
- [Arquitectura y adaptadores](docs/arquitectura_y_adaptadores.md).
- [Validación, errores e idempotencia](docs/contratos_y_errores.md).
- [Pruebas y evidencia disponible](docs/pruebas_y_evidencia.md).

El feed Cassandra conserva su identificador `ARG-ESP-20300624`; Neo4j e InfluxDB usan
`P-001`. No se inventa una traducción. IRIS expone una vista de demostración por ID
persistente, separada de los partidos operativos. Los comentarios son de solo lectura:
no se ofrece una escritura parcial que desincronice tablas y contadores del Hito 6.
La única mutación HTTP es invalidar una sesión (DELETE idempotente).

`/health` devuelve 200 con `up/down` por fuente aun si alguna está caída. Los endpoints
de datos responden 503 ante una dependencia inaccesible. Los detalles del driver no
se publican en respuestas ni logs.

## Detener

Ctrl+C detiene Uvicorn y cierra los adaptadores. En cada módulo de bases, ejecutar
`docker compose stop`; conserva los datos. No se necesita eliminar volúmenes.

## Alcance de validación

Las pruebas con dobles verifican contratos y errores, pero no prueban conectividad.
La evidencia separa esas pruebas de las ejecutadas contra motores reales. No se
presentan cifras de capacidad productiva ni se afirma validación de fuentes no ejecutadas.
