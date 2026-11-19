# Datos de InfluxDB

`scripts/cargar_influx.py` genera las series sintéticas del torneo y las carga en
InfluxDB 3 Core. Reemplaza al generador del repositorio TP
(`fixture2030-influxdb`): lee solo datos versionados en este backend. No se
ejecuta al iniciar la API ni durante los tests.

## Modelo

| Tabla | Base | Tags | Fields | Frecuencia |
| --- | --- | --- | --- | --- |
| `tracking_jugador` | `fixture2030_en_vivo` (7 días) | `partido_id`, `equipo_id`, `jugador_id` | `x_m`, `y_m`, `velocidad_kmh`, `distancia_acum_m` | 1 s |
| `tracking_pelota` | `fixture2030_en_vivo` (7 días) | `partido_id` | `x_m`, `y_m`, `z_m`, `velocidad_kmh` | 1 s |
| `estadisticas_partido` | `fixture2030_resumen` (sin vencimiento) | `partido_id`, `equipo_id`, `sede_id` | `posesion_pct`, `tiros_acumulados` (entero), `pases_intervalo` (entero) | 5 s |
| `actividad_usuarios` | `fixture2030_resumen` (sin vencimiento) | `partido_id`, `region` | `usuarios_conectados` (entero) | 5 s |

Line Protocol con timestamps en segundos y 90 minutos por partido. La API lee
`estadisticas_partido` de `INFLUX_DATABASE` (por defecto `fixture2030_resumen`).

## Fuentes

- Partidos, equipos, sedes y confederaciones: `data/fixture/import/*.csv`.
- Inicio de cada partido: `fecha_hora` de `data/fixture/fixture-calendario.json`,
  el mismo horario que carga `cargar_fixture.py` en MongoDB.
- Titulares para `tracking_jugador`: lotes de alineaciones con el formato de
  `cargar_alineaciones.py` (por defecto `alineaciones-argentina-demo.json`).
  Solo los partidos con alineación generan tracking de jugadores; no se inventan
  convocatorias desde el plantel.

Los valores son pseudoaleatorios con semilla fija por tabla y partido: la misma
entrada produce los mismos puntos, y cargar un partido aislado da los mismos
puntos que el torneo completo.

## Uso

```bash
# Sin conectar a InfluxDB: puntos y series por tabla
.venv/bin/python scripts/cargar_influx.py --solo-validar

# Con el servicio influxdb del Compose ya iniciado
.venv/bin/python scripts/cargar_influx.py --crear-bases
.venv/bin/python scripts/cargar_influx.py --partido P-001   # prueba de un partido
.venv/bin/python scripts/cargar_influx.py                   # torneo completo

# Archivos .lp por tabla y partido, sin conectar
.venv/bin/python scripts/cargar_influx.py --exportar /ruta/a/lp
```

La carga usa `INFLUX_URL` y el token de la API (`INFLUX_TOKEN` o
`.influxdb3-token`). Envía lotes de 10.000 líneas a `/api/v3/write_lp` con
`precision=second` y hasta tres intentos por lote; si queda alguno rechazado
informa la cantidad y termina con código 1. Volver a cargar sobrescribe los
mismos puntos (misma serie y timestamp), sin duplicarlos.

`--crear-bases` ejecuta `influxdb3` dentro del servicio `influxdb` con
`docker compose exec`; no inicia contenedores ni modifica bases existentes.

Con los datos versionados: 127 partidos, 1.961.280 puntos y 1.176 series
(33 de jugadores en 3 partidos, 127 de pelota, 254 de estadísticas y 762 de
audiencia).
