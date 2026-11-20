# Simulación en vivo acelerada (modo demo)

`scripts/simular_en_vivo.py` juega un partido próximo en tiempo real acelerado:
con el factor por defecto (10) los 90 minutos duran unos 9 minutos reales. Por
cada segundo de juego escribe lo que escribiría una ingesta real:

| Destino | Qué | Frecuencia | Hora del punto |
| --- | --- | --- | --- |
| MongoDB `partidos` | reloj, marcador, eventos y estado (guion del caso 7) | en el minuto de cada tick del guion | — |
| `fixture2030_en_vivo.tracking_jugador` | `x_m`, `y_m`, `velocidad_kmh`, `distancia_acum_m` | 1 Hz por titular | `inicio_tracking` + segundo |
| `fixture2030_en_vivo.tracking_pelota` | posición y velocidad | 1 Hz | `inicio_tracking` + segundo |
| `fixture2030_resumen.estadisticas_partido` | muestras del caso 8 | cada 5 s por selección | `fecha_hora` + segundo |
| `fixture2030_resumen.actividad_usuarios` | usuarios conectados | cada 5 s por región | `inicio_tracking` + segundo |

Las bases son las configuradas en `INFLUX_DATABASE_EN_VIVO` e `INFLUX_DATABASE`,
las mismas que leen el mapa de calor y la comparación de equipos.

## Reutiliza el caso 8 y la carga masiva

- El plan es el mismo archivo de `scripts/simular_estadisticas.py`: sirve para
  cualquiera de los dos scripts. La validación inicial, el control
  `estadisticas_control`, la confirmación de cada tick y la consolidación final
  son las funciones del caso 8 (`preparar_ejecucion`, `verificar_avance`,
  `confirmar_tick`, `consolidar`). La comparación de equipos funciona en vivo y
  termina `completa`, igual que con `--modo vivo`.
- Las estadísticas de equipo son las muestras del caso 8 (base cero, cobertura
  continua cada 5 s, 2.162 en total), no las de la carga masiva: no se escriben dos veces.
- Tracking y audiencia usan los generadores de `scripts/cargar_influx.py`: para
  el mismo partido y alineación, cada segundo tiene los mismos valores que la carga
  masiva; solo cambia la hora. Las escrituras pasan por el adaptador de InfluxDB
  (`escribir_lineas`: line protocol, precisión en segundos, lotes atómicos de hasta
  10.000 líneas, hasta tres intentos ante fallas de disponibilidad).

Es un script aparte porque su contrato difiere del caso 8: escribe tracking,
ancla el tiempo en la hora real de inicio y **no es reanudable**.

## Anclaje temporal

Al empezar guarda `inicio_tracking` en el partido: la hora UTC actual redondeada
al minuto, el mismo redondeo que aplica el mapa de calor. El segundo de juego `s`
se escribe en `inicio_tracking + s`; con factor 10 esos puntos quedan por delante
del reloj de pared, sin efecto para las consultas, que cuentan minutos de juego
desde `inicio_tracking`.

Las estadísticas de equipo quedan ancladas en `fecha_hora`, porque la comparación
del caso 8 exige que su control empiece en el horario del partido.

## Comandos

Elegir un partido **próximo con ambas selecciones**, sin simulaciones previas.
Crear y validar no modifica bases; la validación no conecta (P-051 es un ejemplo):

```bash
.venv/bin/python scripts/simular_en_vivo.py /tmp/vivo-P-051.json --crear-plan P-051
.venv/bin/python scripts/simular_en_vivo.py /tmp/vivo-P-051.json --solo-validar
```

`--solo-validar` informa duración real, segundo real de cada tick, jugadores con
tracking y puntos por tabla. Como no conecta, toma las alineaciones de los lotes
versionados (por defecto los de demo; `--alineaciones ARCHIVO` repetible). La
ejecución usa las alineaciones cargadas en MongoDB: se sigue a todos los titulares
de cada selección con alineación (ambas en P-001; solo Argentina en P-002, P-051
y P-083). Sin alineaciones no hay `tracking_jugador`.

Ejecutar requiere autorizar el partido concreto: modifica eventos, reloj,
marcador y estado hasta finalizarlo, escribe en ambas bases de Influx, guarda el
resumen de equipos y actualiza el validador de `partidos` (incluye `inicio_tracking`).

```bash
.venv/bin/python scripts/simular_en_vivo.py /tmp/vivo-P-051.json --factor 10
```

Se rechazan partidos no próximos, con `estadisticas_control` o `inicio_tracking`,
referencias desactualizadas y muestras de `estadisticas_partido` preexistentes en
el horario del partido. La carga masiva de `cargar_influx.py` escribe esas muestras
para todos los partidos: en una base con esa carga, el partido se rechaza.

## Ritmo, orden e invalidación

El bucle escribe un lote por tabla cada segundo real con todos los segundos de
juego vencidos; si se atrasa, el siguiente lote los recupera sin huecos. Cada
tick del guion se confirma en MongoDB cuando sus muestras ya están en Influx. Si
Influx rechaza un lote después de los reintentos, la simulación se detiene antes
de confirmar el tick. Al terminar informa puntos escritos y rechazados por tabla.

Cada tick invalida las cachés del partido, fixture, posiciones y cuadro (lo hace
`aplicar_tick`) y además `mapa_calor:v2:{partido}:*`. Entre ticks, el TTL de 5 s
del mapa en vivo limita la antigüedad. Redis caído no detiene la simulación.

## Corte: no es reanudable

Una ejecución cortada deja el partido con `inicio_tracking`, el control del caso 8,
los ticks confirmados y muestras ya escritas. Volver a ejecutar se rechaza. Para
otra demo, **restaurar el partido** (estado próximo, sin eventos, resultado,
reloj, `estadisticas_control` ni `inicio_tracking`, y sin sus muestras de
estadísticas) **o elegir otro partido próximo**. El script no restaura ni borra.

## Límites

- El reloj de MongoDB avanza en los nueve ticks del guion, no minuto a minuto.
- Se siguen los once titulares durante los 90 minutos: el cambio y la expulsión
  del guion no modifican el tracking.
- El caso 9 valida el tracking dentro de `fecha_hora` y el reloj; el tracking
  anclado en `inicio_tracking` todavía no es consolidable por ese caso. Los campos
  sí son compatibles: odómetro creciente sin huecos a 1 Hz y velocidad en km/h.
- El crudo vence a los 7 días: materializar la ocupación con
  `scripts/materializar_ocupacion.py` para conservar el mapa de calor.

Las pruebas (`tests/unit/test_simulador_en_vivo.py`) recorren el partido completo
con reloj, MongoDB, Redis e Influx en memoria. No certifican una ejecución real.
