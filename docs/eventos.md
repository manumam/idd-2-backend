# Eventos del partido — caso 7

El visitante abre **Cronología** en `/partido.html?codigo=P-001`. Ve goles,
autogoles, tarjetas amarillas/rojas y cambios, con minuto/adicional, selección y
jugadores. Los cambios distinguen `sale` y `entra`; los goles admiten un asistente.
Los autogoles se muestran asociados a la selección del autor y suman para el rival.
Las tandas quedan fuera de esta cronología.

## Lectura

`GET /partidos/{codigo}/eventos?limit=50&skip=0`

- MongoDB: eventos embebidos en `partidos.eventos`; no consulta Neo4j.
- Orden ascendente `(minuto, adicional, codigo)`. `limit`: 1–200; `skip`: entero >= 0.
- Respuesta: `partido`, `items`, `total`, `siguiente_skip`, `estado`, `resultado`, `reloj`.
- Cada evento contiene `codigo`, `tipo`, `minuto`, `adicional`, `equipo` y `protagonistas`.
- `tipo`: `gol`, `autogol`, `tarjeta_amarilla`, `tarjeta_roja`, `cambio`.
- Roles: `autor`, `asistente` (solo gol), `entra` y `sale` (ambos obligatorios en cambios).
- Marcador, reloj y eventos provienen de la misma lectura. La resolución de plazas
  de playoffs sigue la ficha central; resultados obsoletos no muestran eventos heredados.
- Sin eventos: 200 con lista vacía; partido inexistente: 404; parámetros inválidos: 400;
  eventos persistidos inválidos: 500 `EVENTOS_INVALIDOS`; MongoDB caído: 503/504.
- Redis es opcional: Cache-Aside con clave `eventos:v2:{codigo}:{limit}:{skip}` y el TTL
  del fixture. Cada tick borra todas las páginas del partido con `SCAN` + `DEL`.

El frontend consulta cada cinco segundos mientras el partido no esté finalizado,
pausa las consultas automáticas con la pestaña oculta y refresca al volver.
Muestra la instantánea del marcador de la cronología, permite actualización manual
y paginación, y conserva los últimos datos ante errores indicando que pueden estar
desactualizados. Al finalizar deja de consultar automáticamente.

## Simulador de demo: ejecución explícita

No se ejecuta durante el arranque. Usa `.venv`, `.env` y variables exportadas,
sin iniciar contenedores ni cargar equipos, jugadores o partidos.

Primero se puede **generar un plan sin cambiar datos deportivos** desde las
selecciones y jugadores ya existentes. Elegir un partido próximo con ambas
selecciones persistidas, dos jugadores de campo locales y al menos uno visitante.
Si tiene convocatoria local, debe haber un titular y un suplente de campo elegibles.
El guion puede generarse para cualquier partido que cumpla esas condiciones; el
código del ejemplo debe sustituirse por uno que siga próximo en la base actual:

```bash
.venv/bin/python scripts/simular_partido.py /tmp/plan-P-001.json --crear-plan P-001
.venv/bin/python scripts/simular_partido.py /tmp/plan-P-001.json --solo-validar
```

El guion es determinista: inicio, gol local, amarilla visitante, entretiempo,
segundo tiempo, cambio local, segundo gol local, roja visitante y cierre 2–0.
Elige jugadores de campo, priorizando delanteros, luego mediocampistas y defensores;
desempata por dorsal de mayor a menor. Excluye arqueros. Si hay alineaciones,
el primer goleador debe ser titular y quien entra debe ser suplente de campo.
Sin alineaciones usa dos jugadores distintos del plantel como participantes
implícitos del guion, sin inventar ni guardar una convocatoria. El primer goleador
sale en el cambio y el segundo gol lo marca quien entró. Si faltan candidatos,
informa el problema en lugar de elegir un arquero. Este script no genera muestras de Influx; para el caso 8 usar el plan combinado de [estadísticas](estadisticas.md), que incluye los mismos eventos y su serie temporal.
El archivo de salida debe ser nuevo; no reemplaza planes existentes.

| Minuto simulado | Acción |
| --- | --- |
| 0 | Inicia el partido, en vivo y 0–0. |
| 12 | Gol del atacante local elegido como participante inicial. |
| 28 | Amarilla al jugador visitante elegido. |
| 45 | Entretiempo. |
| 46 | Comienza el segundo tiempo. |
| 62 | Sale el primer goleador y entra otro jugador de campo. |
| 78 | Gol de quien entró: 2–0. |
| 82 | Roja al jugador visitante amonestado. |
| 90 | Finaliza el encuentro. |

Los minutos del guion saltan entre estos puntos: `--intervalo` mide segundos reales
entre ticks, no la duración de un minuto de juego. El primer tick es inmediato y
los ocho intervalos siguientes duran unos 48 segundos con `--intervalo 6`
(más la latencia de las bases). El visitante amonestado y luego expulsado recibe
dos eventos independientes; no se representa una segunda amarilla.

Los equipos y nombres se leen de MongoDB; la secuencia, tiempos y resultado son
ficticios y fijos, no aleatorios ni la reproducción de un encuentro real. Sin
alineaciones no se afirma que el plantel seleccionado sea una convocatoria real.

Revisar el JSON y, **solo cuando se quiera avanzar el partido**, ejecutar:

```bash
.venv/bin/python scripts/simular_partido.py /tmp/plan-P-001.json --intervalo 6
```

Abrir `/partido.html?codigo=P-001` en el frontend para seguir el avance; conserva
el código elegido si se generó otro partido. El frontend consulta cada cinco
segundos y puede agrupar visualmente varios ticks si se usa un intervalo menor.
Un `--intervalo 0` aplica el guion sin pausas, por lo que se verá principalmente
el resultado final. El mismo plan no sirve para cambiar otro partido: su código
y las referencias a sus selecciones y jugadores están dentro del archivo.

Cada tick escribe conjuntamente eventos nuevos, marcador, estado, reloj y
`actualizado_en`. Después invalida el fixture, el detalle, las alineaciones y todas
las páginas de eventos del partido, las posiciones de su grupo, el cuadro y los cruces
eliminatorios. El script aplica explícitamente el validador actualizado
`data/fixture/partidos-validator.json` a la colección existente antes de escribir.
No crea la colección si falta. No reinicia partidos, no reemplaza resultados
existentes ni borra eventos: suma los goles nuevos al marcador actual.

Los IDs repetidos con contenido idéntico se conservan sin volver a sumar goles;
un ID con otro contenido produce error. Hay una comprobación simple de concurrencia;
no hay sistema de correcciones, replay ni reinicio automático. Un partido finalizado
no se reabre. Si el script se interrumpe se conservan los ticks ya confirmados;
no volver a reproducir el plan completo sobre un reloj ya avanzado.

Para repetir la demostración, elegir otro partido próximo y generar un archivo
nuevo. No hay bandera de reinicio ni de reanudación automática. Si falta un equipo,
plantel o suplente elegible, corregir o cargar esos datos mediante su procedimiento
explícito antes de generar el plan; el simulador no los inventa. No importar eventos
históricos de Neo4j para completar esta demo.

## Cómo debe ofrecerlo el agente

Al levantar la app o preparar una demo, el agente debe ofrecer esta simulación
por separado del seed. Puede comprobar candidatos y generar/validar el JSON con
lecturas de la base, y explicar un ejemplo concreto: «Puedo simular este partido
con los jugadores del plantel. En unos 48 segundos avanzará por goles, tarjetas y
un cambio, y quedará finalizado 2–0 para el local».

Antes de escribir en MongoDB debe tener autorización explícita para ejecutar ese
partido; iniciar la app no la implica. Si esa autorización ya está en la conversación,
no debe volver a pedirla. Después de ejecutar, debe contrastar estas lecturas:

- `/api/partidos/{codigo}/eventos?limit=200&skip=0`: cinco eventos y estado finalizado.
- `/api/partidos/{codigo}`: marcador local 2–0 y reloj del último tick.
- `/api/fixture`: el mismo partido finalizado y resultado consistente.

El resultado 2–0 es el del guion sobre un partido próximo; no se deben aplicar esos
valores como expectativa a planes propios o a partidos ya iniciados.

También se pueden preparar planes propios:

```json
{
  "partido": "P-001",
  "ticks": [
    {"reloj": {"periodo": "primer_tiempo", "minuto": 0}, "eventos": []},
    {
      "reloj": {"periodo": "primer_tiempo", "minuto": 12},
      "eventos": [{
        "codigo": "P-001-gol-12", "tipo": "gol", "minuto": 12, "adicional": 0,
        "equipo": {"codigo": "ARG", "nombre": "Argentina"},
        "protagonistas": [{"jugador": {"codigo": "ARG-10", "nombre": "Jugador Demo"}, "rol": "autor"}]
      }]
    },
    {"reloj": {"periodo": "segundo_tiempo", "minuto": 90}, "finalizado": true}
  ]
}
```

Las referencias del ejemplo son ilustrativas: deben coincidir con el partido y
catálogo reales. `--solo-validar` comprueba estructura y secuencia sin conectarse;
la existencia y pertenencia de jugadores se comprueban antes de aplicar cada tick.
No hay una ruta HTTP pública de escritura; la ingesta se ejecuta desde consola.

## Verificación

Los tests unitarios cubren cronología vacía, orden y paginación, tiempo adicional,
roles, ingesta de goles/tarjetas/cambios, autogoles, reenvío básico, cierre, referencias
inválidas, caché corrupta/caída y conflicto de escritura sin motores reales.
El frontend valida el contrato y se compila con TypeScript. La simulación sobre
MongoDB real requiere ejecución explícita y modifica el partido elegido.

Se comprobó además la lectura por la API local y el proxy `/api` con MongoDB del
proyecto y la pantalla de un partido próximo sin eventos. En una página temporal
aislada, con respuestas en memoria, se comprobó avance automático de 0–0 a 1–0,
goles/tarjetas/cambios, tiempo adicional, cierre y detención del polling; también
la vista de 390 px sin desbordamiento horizontal. Esa prueba no escribe partidos
ni certifica la ingesta sobre MongoDB real. La página temporal se retiró al terminar.

También se ejecutó explícitamente el plan de P-001 con MongoDB del proyecto:
Uruguay–Arabia Saudita finalizó 2–0, con goles de Federico Viñas y Rodrigo Aguirre,
el cambio entre ambos y amarilla/roja de Sultan Mandash. Los nueve ticks se
confirmaron y las lecturas mediante el proxy coincidieron en cronología, detalle
y fixture. Es un resultado ficticio persistido de demo; no implica reiniciar ese
partido ni ejecutar el mismo plan en otra base.
