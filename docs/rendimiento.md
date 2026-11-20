# Rendimiento individual — caso 9

Implementado en backend y frontend. La suite habitual usa adaptadores en memoria;
el cierre integral con tracking en MongoDB e Influx reales sigue pendiente. El arranque no carga
tracking, no registra cobertura y no consolida partidos automáticamente.

## Lecturas

- `GET /partidos/{codigo}/jugadores/{jugador_codigo}/estadisticas`: jugador y equipo,
  estado/reloj, consolidación, actualización, métricas y advertencias. Solo acepta
  un jugador de las plazas vigentes registrado en convocatoria, eventos o control
  de tracking válido; otro jugador devuelve 404. Un convocado de un partido próximo
  devuelve `sin_datos`, con métricas null.
- `GET /jugadores/{codigo}/estadisticas`: acumulados del Mundial 2030 y detalle por
  partido, con cantidad de encuentros consolidados y pendientes. Excluye próximos
  y participantes obsoletos del cuadro. Sin encuentros disputados devuelve
  `sin_datos` y métricas null.

Métricas: `goles`, `asistencias`, `tarjetas_amarillas`, `tarjetas_rojas`,
`distancia_m` y `velocidad_max_kmh`. Un cero confirmado se conserva; una fuente
incompleta produce null. Los goles propios vienen de eventos `gol/autor`; las
asistencias, de `gol/asistente`. Los autogoles y las tandas no suman goles ni
asistencias individuales. Se rechazan eventos repetidos, equipos ajenos y
cronologías incompatibles con el marcador.

Durante el vivo se combinan eventos MongoDB y tracking confirmado en Influx.
La caché Redis es opcional, de cinco segundos, con partido, jugador y huella de
entradas. Al finalizar, GET nunca lee Influx: usa el resumen vigente o conserva
las deportivas recalculadas y señala consolidación pendiente con físicas null.
Una caída de Influx durante el vivo conserva las deportivas; los errores internos
de consulta no se presentan como ausencia de datos.

Los acumulados solo requieren MongoDB y caché Redis opcional. Cada encuentro aporta
un resumen final vigente o sus eventos actuales, en conjuntos disjuntos. No hay
incrementos persistidos sobre totales. Distancias se suman; velocidad es el máximo.
Si falta una métrica en un encuentro, su total queda null; el detalle conserva lo
conocido. Las físicas en vivo se consultan desde el detalle del partido, no se
incluyen como totales físicos confirmados del torneo.

## Tracking y cobertura explícita

Se usa `tracking_jugador` de `INFLUX_TRACKING_DATABASE` (por defecto
`fixture2030_en_vivo`), separado de `INFLUX_DATABASE` para estadísticas de equipos.
Tags: `partido_id`, `equipo_id`, `jugador_id`; campos físicos:
`distancia_acum_m`, `velocidad_kmh`; frecuencia 1 Hz. Este caso no necesita
coordenadas y no implementa mapas de calor.

El productor debe registrar `tracking_control` en el documento del partido,
confirmando su revisión, cierre de ingesta y los intervalos de cada participante.
Cada intervalo tiene extremos inclusivos y comienza con una muestra base del
odómetro, que puede ser distinta de cero. Ejemplo de archivo de control:

```json
{
  "revision": "tracking-P001-v1",
  "completa": true,
  "jugadores": {
    "ARG-10": [{
      "desde": "2030-06-24T20:00:00Z",
      "hasta": "2030-06-24T21:30:00Z",
      "muestras": 5401
    }]
  }
}
```

El ejemplo es ilustrativo: adaptar fechas, códigos y cobertura a los datos
existentes y declarar a todos los convocados y protagonistas conocidos.
Los intervalos deben estar dentro del tiempo confirmado: desde el inicio temporal
del partido (`inicio_tracking` si lo registró la simulación en vivo, si no
`fecha_hora`; la misma regla que el mapa de calor y el caso 8) hasta ese inicio
más el reloj, sin
superponerse, con zona horaria, precisión de segundo y cantidad exacta de muestras.
Se comprueban identidad de jugador/equipo, continuidad a 1 Hz, duplicados,
valores finitos no negativos y odómetro monótono. Distancia = último contador
menos base de cada intervalo, nunca suma de contadores. Un reinicio requiere
intervalos separados y bases explícitas. Máximo cuatro horas de muestras por jugador.

Una lista vacía solo confirma cero físico para un suplente conocido sin
participación deportiva registrada. Titulares, autores/asistentes de goles y
protagonistas de cambios necesitan muestras. Las tarjetas por sí solas no prueban
que un suplente haya ingresado al campo. `completa` declara que el productor cerró
la ingesta; no se infiere por encontrar la última muestra.

La carga histórica `cargar_influx.py` no registra este control ni confirma todos
los participantes. Sus muestras por sí solas no completan el caso 9. No se
reemplazan ni se fabrican muestras para ocultar cobertura faltante.

## Consolidación explícita

Usar la `.venv` y `.env` normales del proyecto. Estos comandos de escritura se
realizan solo como una operación solicitada, nunca al arrancar ni en los tests:

```bash
# Archivo local: no conecta a bases ni modifica datos deportivos
.venv/bin/python scripts/consolidar_jugadores.py --partido P-001 \
  --registrar-control /ruta/control.json --solo-validar

# Migración explícita para bases existentes: amplía el validador, conserva documentos
.venv/bin/python scripts/consolidar_jugadores.py --partido P-001 --actualizar-validador

# Registra cobertura de muestras existentes; no carga ni modifica tracking/eventos/resultados
.venv/bin/python scripts/consolidar_jugadores.py --partido P-001 --registrar-control /ruta/control.json

# Partido finalizado y cobertura completa: calcula y publica resúmenes individuales
.venv/bin/python scripts/consolidar_jugadores.py --partido P-001 --consolidar
```

Un control distinto exige `--reemplazar-control` explícito. Repetir un control
equivalente conserva los datos. No confirmar rangos sin verificar la ingesta.
Si el tracking crudo venció, se conserva un resumen final ya publicado, pero no se
promete poder reconstruir sus métricas físicas.

`estadisticas_jugador_partido` guarda generaciones inmutables con clave única
`_id = partido:generación:jugador`, más índice `(jugador_id, partido_id)`.
Primero se calculan todos los resúmenes; después se insertan y se publica de forma
atómica el manifiesto `jugadores_finales` mediante comparación de las entradas
anteriores (CAS). Solo la generación referenciada por ese manifiesto es visible.
Un fallo parcial o un escritor concurrente puede dejar una generación no publicada;
no se suma ni se muestra. No se borran generaciones anteriores automáticamente.
Repetir el cierre publica una nueva generación equivalente, sin duplicar totales.

La huella incluye estado, participantes, resultado, reloj, eventos, alineaciones y
control de tracking. Una corrección invalida el resumen y exige reproceso. Los
escritores de eventos y resultados invalidan las cachés individuales y acumuladas;
la huella y TTL cubren cambios externos. Para corregir muestras conservando las
fechas, el productor debe cambiar `revision` antes de reprocesar.

## Frontend y verificación

Desde las alineaciones se abre `/jugador.html?codigo=ARG-10&partido=P-001` y se
conserva el regreso a `#alineaciones`. Muestra rendimiento, reloj, actualización,
acumulados y enlaces a otros encuentros del jugador. Desde el plantel se muestran
los acumulados aunque no se haya elegido partido. Nothing Design oscuro, fuentes
Space Grotesk/Space Mono y Doto desde Google Fonts; diseño adaptable, navegación
por teclado, carga y errores en línea. Actualiza cada cinco segundos durante el
vivo/cierre pendiente, pausa al ocultar la pestaña y conserva datos ante errores.

Antes de certificar la demo real: comprobar ambos endpoints a través de `/api`,
verificar correspondencia con eventos y tracking, repetir consolidación y comparar
totales, corregir una entrada, y consultar finales con Influx no disponible y Redis
vacío. Estas comprobaciones con escrituras requieren datos dedicados/autorizados.

Lectura real verificada mediante el proxy y la página: URU-21 en P-001 muestra
un gol, cero asistencias y tarjetas, y físicas null con consolidación pendiente;
el acumulado incluye ese encuentro una sola vez. Se conservaron eventos, resultado
y tracking existentes. Revisión visual del diseño oscuro y grilla móvil a 390 px
sin desborde horizontal. Esta lectura no certifica la consolidación física.
