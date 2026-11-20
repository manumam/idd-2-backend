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
`estadisticas_partido` de `INFLUX_DATABASE` (por defecto `fixture2030_resumen`) y
el tracking crudo de `INFLUX_DATABASE_EN_VIVO` (por defecto `fixture2030_en_vivo`).
Las consultas solo aceptan estas dos bases configuradas.

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

La carga escribe por el adaptador de InfluxDB de la API (`escribir_lineas`, con
`INFLUX_URL` y el mismo token: `INFLUX_TOKEN` o `.influxdb3-token`), como todo
acceso a una base. Envía lotes de 10.000 líneas a `/api/v3/write_lp` con
`precision=second` y `accept_partial=false`: cada lote se escribe entero o se
rechaza entero, así la cantidad informada de líneas rechazadas es exacta. Las
fallas de disponibilidad (conexión, timeout, 5xx) se reintentan hasta tres veces;
un 4xx (líneas o credenciales rechazadas) no se reintenta. Solo escribe en las dos
bases configuradas (`INFLUX_DATABASE` e `INFLUX_DATABASE_EN_VIVO`). Cada lote se
mide en las métricas de dependencias de la API (`operacion="escribir_lote"`). Si
queda alguna línea rechazada informa la cantidad y termina con código 1. Volver a cargar sobrescribe los
mismos puntos (misma serie y timestamp), sin duplicarlos.

`--crear-bases` ejecuta `influxdb3` dentro del servicio `influxdb` con
`docker compose exec`; no inicia contenedores ni modifica bases existentes.

Con los datos versionados: 127 partidos, 1.961.280 puntos y 1.176 series
(33 de jugadores en 3 partidos, 127 de pelota, 254 de estadísticas y 762 de
audiencia).

## Ocupación por celda y minuto

`scripts/materializar_ocupacion.py` resume `tracking_jugador` (crudo de 1 s,
vence a los 7 días) en `ocupacion_jugador_minuto`, que queda en
`fixture2030_resumen` sin vencimiento y alimenta el mapa de calor histórico.
Es un comando explícito: no se ejecuta al iniciar la API.

| Tabla | Base | Tags | Fields | Tiempo |
| --- | --- | --- | --- | --- |
| `ocupacion_jugador_minuto` | `fixture2030_resumen` (sin vencimiento) | `partido_id`, `equipo_id`, `jugador_id`, `celda` (`columna_fila`, p. ej. `7_2`) | `muestras` (entero) | Comienzo de la ventana de 1 minuto, precisión en segundos |

La celda la calcula InfluxDB con una sola consulta SQL por partido sobre
`fixture2030_en_vivo`: `date_bin` agrupa por minuto, `FLOOR` y `LEAST` llevan
`x_m`/`y_m` a la grilla de 5 × 5 m de `app/services/grilla_cancha.py` (21 × 14
celdas; el borde lejano cae en la última celda) y se descartan las muestras
fuera de la cancha. Funciones en la documentación de InfluxDB 3 Core:
[date_bin](https://docs.influxdata.com/influxdb3/core/reference/sql/functions/time-and-date/#date_bin),
[floor](https://docs.influxdata.com/influxdb3/core/reference/sql/functions/math/#floor),
[least](https://docs.influxdata.com/influxdb3/core/reference/sql/functions/conditional/#least).

```bash
# Solo lectura: puntos, series y si la suma de ventanas da el total del partido por celda
.venv/bin/python scripts/materializar_ocupacion.py --partido P-002 --solo-validar

# Escribe en fixture2030_resumen y borra mapa_calor:v2:{partido}:* de Redis (SCAN)
.venv/bin/python scripts/materializar_ocupacion.py --partido P-002
.venv/bin/python scripts/materializar_ocupacion.py --todos   # partidos con tracking_jugador
```

`GET /partidos/{codigo}/mapa-calor` lee esta tabla en partidos finalizados: suma
`muestras` por `celda` de las ventanas que empiezan en el rango pedido.

Ejecutarlo después de cada partido y antes de que venza su crudo (7 días). La
escritura usa el mismo método del adaptador que `cargar_influx.py`; si queda alguna
línea rechazada termina con código 1. Reprocesar escribe el mismo valor en la
misma serie y timestamp, sin sumar. Un punto de una celda que ya no tiene
muestras no se borra (el script solo escribe): `--solo-validar`
informa esos `puntos_obsoletos`. Con el crudo determinístico no aparecen. Si
Redis no responde, solo advierte y la caché vence por TTL.

### Tracking y estadísticas del caso 8

El simulador `simular_estadisticas.py` escribe posesión, tiros acumulados y cantidades de pases por intervalo en `estadisticas_partido`; los eventos deportivos se guardan en MongoDB. No genera posiciones ni trayectorias de jugadores o pelota. Para un mapa de calor con contenido se necesita una carga de tracking independiente y, para conservarlo, materializar la ocupación antes de que venza el crudo. Sin muestras, tabla o base de tracking creada, el mapa devuelve 200 con `celdas: []`; no inventa posiciones. Los fallos de autenticación, permisos, conexión y consultas inválidas siguen devolviendo errores.
