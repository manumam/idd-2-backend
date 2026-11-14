# Fixture reproducible del Mundial 2030

`GET /fixture` devuelve `{items: [...]}` con código, fecha/hora UTC, fase, grupo,
equipos, estado y resultado, ordenados por fecha y código. El seed, sus CSV, el
validador y el escenario están incluidos en este backend: no se necesita otro clon.

## Cargar y abrir localmente

Desde la raíz del backend, con el entorno `.venv` instalado:

```bash
# Usar el MongoDB y Redis de desarrollo configurados en .env.
# No iniciar el laboratorio Hito 11 para abrir la aplicación.

# Validar los 127 partidos sin acceder a las bases.
.venv/bin/python scripts/cargar_fixture.py --solo-validar

# Solo cuando se solicite cargar datos: conserva estados y marcadores existentes.
.venv/bin/python scripts/cargar_fixture.py

# Arranque normal: usa .env, sin ejecutar seeds ni tests.
bash scripts/iniciar_api.sh
```

El cargador usa `.env` por defecto, admite `--env-file` y mantiene la prioridad de
las variables exportadas sobre el archivo, igual que la configuración del backend.
Usar el mismo archivo para el seed y para la API. Comprobar que los puertos configurados correspondan a las bases de este proyecto;
no usar el MongoDB de otra aplicación ni sustituirlo por el laboratorio de evaluación.

El dataset de `data/fixture/` incluye los CSV de partidos, participaciones, equipos
y sedes, más `fixture-calendario.json`, `fixture-escenario-demo.json` y
`partidos-validator.json`. Los horarios son simulados, explícitos en UTC; no es el
calendario oficial. No necesita un servidor Neo4j para cargar el listado.

Para restaurar todos los partidos al estado próximo:

```bash
.venv/bin/python scripts/cargar_fixture.py --reiniciar-escenario
```

La carga valida el lote antes de escribir, hace upserts por código sin borrar
colecciones e informa insertados y actualizados. La carga normal preserva los
marcadores; `--reiniciar-escenario` los reemplaza explícitamente. Esto reproduce una
instantánea del fixture, no un simulador que hace avanzar el Mundial. La ficha
histórica `/partidos/{codigo}` sigue usando Neo4j.

## Caché y disponibilidad

Clave `fixture:v1:todos`; `FIXTURE_CACHE_TTL_SECONDS=5` por defecto (1–3600).
Cache-Aside: un miss consulta MongoDB y guarda el cuerpo validado. Redis caído o
payload inválido permite reconstruir desde MongoDB. Un fallo al guardar caché no
invalida una lectura exitosa. El cargador intenta invalidar incluso ante escritura
parcial y advierte por stderr si Redis falla; el TTL limita la antigüedad. No hay
transacción distribuida ni garantía de lectura monótona.

La futura ingesta debe llamar a `app.services.fixture_service.invalidar_fixture`
después de confirmar cambios. MongoDB caído con caché válida puede responder 200;
sin caché, 503 `MONGODB_UNAVAILABLE` o 504 `MONGODB_TIMEOUT`, según la causa.
Identidad, permisos y errores de consulta conservan la clasificación común.

## Verificación local

La suite habitual no inicia motores: `.venv/bin/python -m pytest -q`.
Las pruebas con motores dedicados y su evidencia pertenecen al
[laboratorio](../laboratorio/verificacion-fixture.md).

## Inicio sin partidos disputados (64 selecciones)

```bash
.venv/bin/python scripts/cargar_jugadores.py --solo-validar
.venv/bin/python scripts/cargar_jugadores.py
.venv/bin/python scripts/cargar_inicio_mundial.py --solo-validar
.venv/bin/python scripts/cargar_inicio_mundial.py
```

Usar esta inicialización, y no el escenario histórico de ejemplo, para preparar
el torneo antes de comenzar: 64 equipos, 16 grupos de 4, 96 partidos de grupos,
16 de dieciseisavos, 8 de octavos, 4 de cuartos, 2 semifinales y una final.
No hay partido por el tercer puesto en este dataset. Los cruces de grupos, fechas
y sedes son los sintéticos existentes. Las plazas eliminatorias quedan nulas.
El script exige que no existan partidos; no borra ni reinicia datos. Equipos nuevos
se insertan sin ranking ni técnico conocido; se preservan fichas existentes.
Los 1.248 jugadores provienen de 2026; 16 selecciones todavía no tienen plantel.
Los nombres embebidos de equipo se alinean al catálogo simulado.
Todavía no hay cálculo de posiciones ni avance automático de clasificados.
