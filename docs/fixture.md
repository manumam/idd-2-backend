# Fixture reproducible del Mundial 2030

La API publica `GET /fixture`, sin filtros ni paginación. Devuelve `{items: [...]}`
con código, fecha/hora UTC, fase, grupo, equipos, estado y resultado. Ordena por
`fecha_hora` y luego por código. La lista vacía es 200. Próximo tiene resultado
nulo; en vivo y finalizado tienen goles de juego y tanda separada. Una plaza sin
resolver admite equipo nulo.

## Cargar el seed

El repositorio de datos debe estar disponible localmente. Desde el backend, con su
entorno instalado y MongoDB/Redis levantados, definir las rutas y conexiones:

```bash
# Ajustar a la ubicación de tu clon de idd-2-tp (en este workspace se llama tp).
export FIXTURE_DATA_ROOT=/ruta/al/tp
export MONGO_URI=mongodb://localhost:27017
export MONGO_DATABASE=fixture2030
export REDIS_HOST=localhost
export REDIS_PORT=6380
export REDIS_DB=0
# Exportar MONGO_URI/REDIS_PASSWORD de tu entorno si requieren credenciales.

# Validar sin acceder a las bases.
.venv/bin/python "$FIXTURE_DATA_ROOT/fixture2030-mongo/scripts/cargar_fixture.py" --solo-validar
# Crear colección, validadores, índice y cargar los 127 partidos.
.venv/bin/python "$FIXTURE_DATA_ROOT/fixture2030-mongo/scripts/cargar_fixture.py"
```

El cargador lee variables exportadas, **no lee automáticamente `.env`**. La API sí
usa `.env`; ambos procesos deben apuntar a las mismas bases. La colección usa los
nombres embebidos de los CSV y puede cargarse independientemente del seed de planteles.

La carga combina `partidos.csv`, `participaciones.csv`, `equipos.csv` y `sedes.csv`
de `fixture2030-neo4j/import/` con `fixture2030-mongo/datos/fixture-calendario.json`.
Todos los horarios son simulados, explícitos en ese JSON. No es el calendario
oficial. La carga normal preserva estados y marcadores existentes; no duplica
partidos, borra colecciones ni necesita un servidor Neo4j.

## Reiniciar la demo

```bash
# P-001 finalizado 2–1, P-002 en vivo 1–0 y el resto próximos.
.venv/bin/python "$FIXTURE_DATA_ROOT/fixture2030-mongo/scripts/cargar_fixture.py" \
  --reiniciar-escenario \
  --escenario "$FIXTURE_DATA_ROOT/fixture2030-mongo/datos/fixture-escenario-demo.json"

# Restaurar todos los partidos al estado próximo.
.venv/bin/python "$FIXTURE_DATA_ROOT/fixture2030-mongo/scripts/cargar_fixture.py" --reiniciar-escenario

curl http://localhost:8000/fixture
```

Esto reproduce el fixture y una instantánea de estados. El simulador que hace
avanzar los partidos y resuelve el Mundial se implementará en otro incremento.

## Caché y disponibilidad

Clave `fixture:v1:todos`; TTL configurable de 5 segundos por defecto (1–3600).
Cache-Aside: un miss consulta MongoDB y guarda el cuerpo validado. Redis caído o
payload inválido permite reconstruir desde MongoDB. Una escritura de caché fallida
no invalida una lectura exitosa. La carga intenta borrar la clave incluso ante
escrituras parciales; un fallo de invalidación se informa por stderr y se resuelve
al vencer el TTL. No hay transacción distribuida ni garantía de lectura monótona.

La futura ingesta debe llamar a `app.services.fixture_service.invalidar_fixture`
después de confirmar cambios. MongoDB caído con caché válida puede responder 200;
sin caché, 503 `MONGODB_UNAVAILABLE` o 504 `MONGODB_TIMEOUT`, según la causa.
Identidad, permisos y errores de consulta conservan la clasificación común.

## Verificación

```bash
.venv/bin/python -m pytest tests/unit -q
python3 -m unittest discover -s "$FIXTURE_DATA_ROOT/fixture2030-mongo/tests" -v

# Crear contenedores temporales aislados; no se usan las bases existentes.
docker run --rm -d --name fixture-r1-mongo -p 127.0.0.1:47017:27017 --tmpfs /data/db mongo:7.0
docker run --rm -d --name fixture-r1-redis -p 127.0.0.1:46379:6379 redis:7.4-alpine
# Esperar a que MongoDB acepte conexiones.
FIXTURE_INTEGRATION=1 FIXTURE_DATA_ROOT="$FIXTURE_DATA_ROOT" \
FIXTURE_TEST_MONGO_URI=mongodb://127.0.0.1:47017 FIXTURE_TEST_REDIS_PORT=46379 \
  .venv/bin/python -m pytest tests/integration/test_fixture_live.py -q
docker stop fixture-r1-mongo fixture-r1-redis
```

La integración crea y elimina una base con nombre aleatorio y usa la clave fija del
fixture en el Redis indicado: usar siempre un Redis aislado. Comprueba carga doble,
preservación/reinicio de marcadores, validadores reales, índice de orden, HTTP,
expiración e invalidación. También comprueba Redis inaccesible y MongoDB inaccesible
con y sin caché mediante conexiones TCP reales a puertos reservados sin listener,
sin detener otros servicios. Los tests de servicio cubren caché inválida.

Evidencia de esta implementación: [validación del requerimiento 1](evidencia/fixture-requerimiento-1.md).
