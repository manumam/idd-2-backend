# Dataset local del fixture

Datos sintéticos versionados para los 127 partidos del Mundial 2030 de la demo.
`import/` contiene partidos, participaciones, selecciones y sedes. El calendario
agrega horarios simulados UTC y estados iniciales; el escenario separado muestra
un partido finalizado, uno en vivo y el resto próximos.

El backend incluye todos los archivos necesarios para validar y cargar el fixture.
Ejecutar `scripts/cargar_fixture.py` según la [guía de carga](../../README.md#carga-de-datos). No hay descargas ni
accesos a otros repositorios durante la carga.

Procedencia: copia del dataset y seed publicados en el commit
`6ec3169f4b069ada12b53c59aeb50e7eb67b2cf6` de `mateolewinzon/idd-2-tp`.
Los datos se mantienen a partir de aquí dentro del backend; los horarios y
resultados de ejemplo no representan un calendario ni un torneo oficiales.

`grupos.json` define participantes y reglas de la demo (3/1/0 y desempate
explícito después de puntos, DG y GF). Carga aditiva independiente:
`.venv/bin/python scripts/cargar_grupos.py`; `--solo-validar` valida sin motores.
No se ejecuta durante el arranque ni modifica resultados.

## Cruces de playoffs

`cruces.json` define 31 partidos: dieciseisavos, octavos, cuartos, semifinales y
final. Clasifican los dos primeros de A–P; se cruzan A1–B2, B1–A2, etc., y los
ganadores consecutivos se enfrentan en la ronda siguiente. No hay mejores terceros.
Son reglas de la demo, no un reglamento oficial.

Validar sin bases: `.venv/bin/python scripts/cargar_playoffs.py --solo-validar`.
Cargar de forma explícita, con fixture y grupos existentes en el MongoDB del
proyecto: `.venv/bin/python scripts/cargar_playoffs.py`. Solo inserta ausentes;
rechaza divergencias y no modifica partidos, marcadores ni planteles.
