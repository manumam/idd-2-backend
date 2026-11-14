# Snapshot público del Mundial 2026

Fuente: [OpenFootball / worldcup.json](https://github.com/openfootball/worldcup.json/tree/master/2026).
Licencia publicada: CC0-1.0, incluida en `source/LICENSE.md`.
`provenance.json` registra commit, URL fija, fecha de descarga y SHA-256 de cada archivo.
No se ejecutó código de terceros. Los partidos históricos no se importan en MongoDB.

## Contenido y validación

- 48 selecciones, 12 grupos de 4.
- 48 planteles de 26 jugadores: 1.248 jugadores.
- 104 partidos con resultados en la fuente.
- Sedes y grupos conservados en su formato de origen.

`validation.json` documenta las comprobaciones estructurales ejecutadas. No equivale
a una auditoría independiente de resultados y convocatorias contra actas de FIFA.
El formato 48/12/104 está corroborado por FIFA:
https://www.fifa.com/en/tournaments/mens/worldcup/articles/world-cup-format-evolution-change-history-1930-2026

## Adaptación pendiente

La demo existente en `data/fixture/` es sintética: 64 equipos y 127 partidos para
2030, sin partido por el tercer puesto. Este snapshot usa el torneo 2026 y no debe
mezclarse automáticamente con ella. Definir si se importa como dataset histórico
o se usan únicamente los planteles como base de una demo identificada como tal.

La fuente contiene nombre completo, dorsal, posición, club y fecha de nacimiento.
No separa nombre/apellido ni incluye ranking FIFA en el catálogo. No inventar esos
campos al adaptar las fichas de equipos y jugadores de la API. Las posiciones
GK/DF/MF/FW se corresponden con Arquero/Defensor/Mediocampista/Delantero.
La carga debe ser explícita, reproducible e independiente del arranque y los tests.

## Jugadores utilizados en la demo

`source/players.tsv` incorpora nombres y apellidos separados desde
[matyuschenko/fifa-wc2026-players](https://github.com/matyuschenko/fifa-wc2026-players),
publicados bajo CC BY 4.0 según su README. Atribución: matyuschenko; fuente declarada
por el autor: FIFA. `players-provenance.json` registra versión y SHA-256.
`scripts/cargar_jugadores.py` verifica el hash y los 48 planteles antes de conectar
a MongoDB; hace upserts por equipo y dorsal, sin borrar jugadores ni tocar partidos.
Preserva nombres/apellidos de la fuente, incluidos monónimos, sin inferirlos.
La demo mantiene los 64 equipos y grupos del fixture sintético, no los grupos de 2026.
El cargador de inicio alinea los nombres embebidos de equipo al catálogo simulado.
