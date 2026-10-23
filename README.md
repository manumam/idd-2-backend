# Fixture 2030 — Backend e Hito 11

FastAPI con capas HTTP → servicios → adaptadores para MongoDB, Neo4j,
Redis e InfluxDB 3. Rama de entrega: `codex/hito-11-conectividad`.

Entrega actual: [Hito 11: procedimiento y evidencia](docs/hito_11/README.md).

Para reproducir la entrega en un laboratorio aislado (Python 3.12 y Docker Compose):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/cerrar_hito11.py
```

El procedimiento conserva volúmenes, no usa datos de los hitos anteriores y guarda la evidencia en `docs/hito_11/evidencia/`. La configuración manual que sigue sirve para conectar la API a los motores existentes.

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

La colección de Postman está en [postman_collection.json](postman_collection.json).
Importala desde **Import → File**; la variable `baseUrl` apunta por defecto a
`http://localhost:8000`.

Cloná el [repositorio de los hitos anteriores](https://github.com/mateolewinzon/idd-2-tp)
al mismo nivel que este repositorio. Desde el directorio del backend, levantá las
bases con `docker compose up -d`; el archivo `docker-compose.yaml` usa los scripts y
datos del repositorio vecino. Ver [conectividad y configuración](docs/conectividad_y_configuracion.md)
para el orden de carga, puertos, hosts en Docker y datos necesarios.

## Probar y reproducir

```bash
bash scripts/ejecutar_pruebas.sh       # suite sin motores, integra contratos ASGI y dobles de drivers
bash scripts/ejemplos_curl.sh          # requests HTTP reales contra la API iniciada
python scripts/exportar_openapi.py    # regenerar contrato después de cambiar rutas/schemas
```

La suite normal incluye tests de integración desactivados explícitamente. Para
probar las fuentes reales cargadas con datos representativos:

```bash
LIVE_MODULES=mongodb,neo4j,redis,influxdb \
  python -m pytest tests/integration -v
```

Se puede seleccionar un subconjunto en `LIVE_MODULES`. Los tests habilitados fallan
si la fuente cae o no devuelve los datos esperados. Ver [tests/README.md](tests/README.md).

## Contrato y decisiones

- [Casos de uso, rutas e identificadores](docs/casos_de_uso.md).
- [Arquitectura y adaptadores](docs/arquitectura_y_adaptadores.md).
- [Validación, errores e idempotencia](docs/contratos_y_errores.md).
- [Pruebas y evidencia disponible](docs/pruebas_y_evidencia.md).

Cassandra y la ruta de comentarios se retiraron por decisión del equipo para el Hito 11.
La única mutación HTTP es invalidar una sesión (DELETE idempotente).

`/live` comprueba el proceso sin consultar motores. `/ready` devuelve 200 si todas las fuentes responden a su ping o 503 si alguna falla. `/health` devuelve 200 con `up/down` por fuente aun si alguna está caída. Los endpoints
de datos responden 503 ante una dependencia inaccesible o con identidad/permisos/contexto rechazados, y 504 ante timeout. Los detalles del driver no
se publican en respuestas ni logs.

## Detener

Ctrl+C detiene Uvicorn y cierra los adaptadores. Desde el backend, `docker compose stop`
detiene las bases y conserva los datos. No se necesita eliminar volúmenes.

## Alcance de validación

Las pruebas con dobles verifican contratos y errores, pero no prueban conectividad.
La evidencia separa esas pruebas de las ejecutadas contra motores reales. No se
presentan cifras de capacidad productiva ni se afirma validación de fuentes no ejecutadas.

Casos HTTP negativos del Hito 11: `.venv/bin/python scripts/prueba_api_negativos.py` con la API del laboratorio iniciada. Los casos de driver simulados y los casos HTTP reales se identifican en la evidencia.
