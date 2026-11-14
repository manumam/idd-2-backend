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
