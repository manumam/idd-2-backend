# Caso 8: comparación de equipos, seed y simulación

## Consulta

`GET /partidos/P-002/estadisticas` devuelve una instantánea con `local` y
`visitante`: `posesion_pct`, `tiros`, `pases`, `goles`, `tarjetas_amarillas` y
`tarjetas_rojas`. Incluye `estado`, `reloj`, `actualizado_en`, `advertencias` y
`consolidacion`:

- `sin_datos`: partido próximo; las métricas son `null`.
- `provisional`: fuentes confirmadas para el avance actual; se actualiza en vivo.
- `pendiente`: faltan muestras, eventos consistentes o consolidación final.
- `completa`: resumen final de equipos persistido en MongoDB.

Los valores desconocidos son `null`, nunca ceros de reemplazo. Los autogoles
suman al rival; las tandas no cuentan como goles. Goles y tarjetas vienen de
los eventos de MongoDB. Si la cronología no coincide con el marcador, las
estadísticas deportivas quedan pendientes de revisión.

Influx conserva muestras con duración, posesión, tiros acumulados y pases por
intervalo. La comparación requiere una base cero y cobertura continua para ambos
equipos hasta el reloj confirmado. Usa el valor final menos la base para tiros,
suma los pases y pondera la posesión por duración. La caché Redis de vivo tiene
TTL de cinco segundos y clave versionada por eventos, marcador, reloj, equipos
y control de ingesta. Redis es opcional. Una falla de disponibilidad de Influx
devuelve las métricas deportivas con advertencia y métricas temporales `null`;
un error interno de consulta se informa como error, no como ausencia de datos.

Al finalizar, GET solo usa MongoDB (Redis puede usarse para el detalle, con
fallback); no consulta Influx. Un resumen cuya huella ya no corresponde a los
eventos, reloj, estado o participantes se informa pendiente de reproceso. El
cierre es explícito, se verifica contra una instantánea y reemplaza el resumen
mediante CAS; no incrementa acumulados. Un GET nunca consolida ni escribe en MongoDB.

### Compatibilidad temporal

La misma ruta con `desde` y `hasta` conserva el contrato anterior de serie:

```text
/partidos/P-002/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z&ventana=1m
```

Ambas fechas UTC son obligatorias juntas. `equipo` y `ventana` requieren esas
fechas; sin fechas se comparan ambos equipos. Crudo: máximo 30 minutos;
ventanas `1m`/`5m`: máximo dos horas. El fin es exclusivo. La serie histórica
mantiene promedio simple por ventana, máximo de tiros y suma de pases; no debe
sumarse el campo de tiros acumulados para calcular el total del partido.
Un intervalo sin muestras conserva el 200 con `items: []`; la comparación de
un partido inexistente devuelve 404. Parámetros incompletos devuelven 400.

## Influx propio, sin repositorio de datos externo

Para el caso 8 se ofrece un Compose independiente de desarrollo, sin montajes de
`idd-2-tp` y sin reutilizar volúmenes anteriores ni del laboratorio:

```bash
docker compose -f docker-compose.estadisticas.yaml up -d
.venv/bin/python scripts/preparar_influx_local.py
```

Crea `fixture2030-estadisticas-influxdb`, el volumen persistente
`fixture2030-estadisticas-influxdb-data` y expone solo `127.0.0.1:8181`.
Comprobar que el puerto está libre antes de iniciarlo; no detener servicios ajenos.
`INFLUX_ESTADISTICAS_PORT` permite elegir explícitamente otro puerto si se necesita.
El script crea/verifica la base, obtiene el token del contenedor propio sin imprimirlo,
y actualiza únicamente `INFLUX_URL`, `INFLUX_DATABASE` e `INFLUX_TOKEN` en `.env`.
Conserva una copia privada `.env.antes-estadisticas` la primera vez y no carga datos
estadísticos ni deportivos. Las variables exportadas siguen teniendo prioridad:
revisarlas si la aplicación usa una conexión diferente.

MongoDB y Redis siguen siendo los servicios del Compose normal. En este proyecto
el Mongo de desarrollo usa 27018: configurar `MONGO_URI` para ese puerto y conservar
su base; nunca usar el Mongo de otro proyecto que escuche en 27017. Reiniciar la API
con `bash scripts/iniciar_api.sh` después de cambiar conexiones; iniciar el frontend
con `npm run dev` y confirmar que `API_PROXY_TARGET` coincide con la API.

## Plan común, sin escrituras deportivas

Ejecutar desde este repositorio con `.venv` y la `.env` normal; las variables
exportadas prevalecen. Comprobar que Mongo apunta al contenedor de este proyecto
y que Influx corresponde a la base del proyecto. No usar la base de otro proyecto
ni el laboratorio Hito 11/12. El script no carga equipos, jugadores, grupos ni
alineaciones: deben existir antes.

Primero consultar el fixture y elegir un partido **próximo con ambos equipos
definidos y jugadores de campo disponibles**. Los códigos siguientes son ejemplos,
no autorización para modificar ese partido.

```bash
.venv/bin/python scripts/simular_estadisticas.py /tmp/estadisticas-P-002.json --crear-plan P-002
.venv/bin/python scripts/simular_estadisticas.py /tmp/estadisticas-P-002.json --solo-validar
```

Crear el plan lee equipos, jugadores y convocatorias existentes. La validación
local no conecta a motores ni verifica referencias actuales. El plan JSON guarda
horario, equipos y nueve ticks deportivos; las 2.162 muestras de ambos equipos
se generan de forma determinista cada cinco segundos deportivos durante 90 minutos,
incluyendo una base cero por selección. Cambiar la velocidad no cambia sus tiempos.

Guion ficticio: cinco eventos, local 2–0, una amarilla y una roja para el visitante,
un cambio local; 14–7 tiros y 360–270 pases. Posesión variable y complementaria.
Prioriza delanteros, excluye arqueros y respeta convocatorias al generar el plan,
igual que [el caso 7](eventos.md). No genera tracking ni estadísticas de jugadores,
y no implementa los casos 9–11.

## Ejecutar después de autorizar el partido concreto

**Ambos modos modifican eventos, reloj, marcador y estado del encuentro hasta
finalizarlo, escriben muestras en Influx y guardan el resumen de equipos en MongoDB.**
También actualizan explícitamente el validador de `partidos` para admitir los campos
`estadisticas_control` y `estadisticas_finales`. Conservan otros partidos y catálogos.

Seed final, sin pausas:

```bash
.venv/bin/python scripts/simular_estadisticas.py /tmp/estadisticas-P-002.json --modo seed-final
```

Reproducción acelerada, aproximadamente 48 segundos:

```bash
.venv/bin/python scripts/simular_estadisticas.py /tmp/estadisticas-P-002.json --modo vivo --intervalo 6
```

No ejecutar ambos modos sobre partidos distintos esperando que representen una
misma ejecución. Son dos velocidades para el mismo plan; al repetirlo se retoman
los ticks pendientes. Se rechazan partidos ajenos ya iniciados/finalizados, otros
planes, referencias desactualizadas y muestras preexistentes en ese intervalo.
La comprobación previa consulta el esquema de Influx: si aún no existe la tabla,
la primera escritura la crea. Las muestras heredadas sin duración no se consideran
cobertura suficiente para consolidar.

Influx se escribe antes de confirmar el tick en MongoDB. No hay transacción
distribuida: una interrupción puede dejar muestras adelantadas. Las lecturas se
limitan al avance confirmado; volver a ejecutar **el mismo archivo** reenvía las
mismas claves y valores y continúa. No borrar el plan ni cambiarlo durante un
reintento. No hay bloqueo distribuido: ejecutar una sola reproducción por partido;
los conflictos detectados detienen la ejecución. No ofrece reinicio ni borrado.

Se usan `accept_partial=false` y confirmación después del WAL. La identidad
(tabla, tags, timestamp) permite reenviar un punto sin crear otro evento temporal:
[escritura HTTP](https://docs.influxdata.com/influxdb3/core/write-data/http-api/v3-write-lp/)
y [line protocol](https://docs.influxdata.com/influxdb3/core/reference/line-protocol/).

Si el cierre falla por una fuente ausente, el resultado deportivo queda finalizado,
pero las estadísticas siguen pendientes. Restaurar la fuente y repetir el mismo plan,
o reprocesar explícitamente el resumen de equipos:

```bash
.venv/bin/python scripts/simular_estadisticas.py --consolidar P-002
```

Una corrección externa de eventos exige revisar marcador y consistencia antes del
reproceso. Este comando no corrige datos deportivos ni reconstruye muestras ausentes.

## Frontend y verificación

`/partido.html?codigo=P-002#estadisticas` incluye «Cara a cara», Nothing Design
oscuro, Space Grotesk y Space Mono desde Google Fonts. Compara seis métricas,
distingue cero de ausencia y muestra fecha, advertencias y estado final/provisional.
Consulta cada cinco segundos mientras el partido no finaliza o el resumen está
pendiente; una falla conserva los últimos datos con advertencia. Permite reintentar.

Después de una ejecución autorizada, verificar a través del proxy del frontend:

```text
GET /api/partidos/P-002/estadisticas
GET /api/partidos/P-002/eventos
GET /api/partidos/P-002
GET /api/fixture
```

Deben coincidir marcador 2–0, reloj 90 y estado finalizado. La comparación debe
informar `completa`, tiros 14–7 y pases 360–270. Comprobar también la lectura final
con Influx no disponible y caché vacía en un entorno de prueba dedicado, sin detener
servicios ajenos ni vaciar la caché general del desarrollo.

Las pruebas unitarias cubren el recorrido con adaptadores en memoria, reintentos,
fallos parciales, cierre incompleto, autogoles, tandas, cobertura y agregación ponderada.
No certifican ejecución real en MongoDB/Influx. Para motores reales seguir
`tests/README.md` y usar bases dedicadas; no ejecutar pruebas que escriben sobre desarrollo.

## Ejecución real verificada (19/11/2026)

Se ejecutó el seed final autorizado de **P-001, Uruguay–Arabia Saudita**, sobre el
Mongo del proyecto (27018) y el Influx propio (8181). Nueve ticks, cinco eventos y
2.162 muestras terminaron en **2–0**, reloj 90 y consolidación completa. El proxy
respondió 200 para estadísticas, cronología, detalle y fixture, con resultados
consistentes. Posesión 54,8–45,2 %, tiros 14–7, pases 360–270 y tarjetas 0–1 de
cada color. La página real se revisó en escritorio y móvil de 390 px.

Se detuvo temporalmente solo el Influx nuevo y se verificó el resumen final con
Mongo real y Redis inaccesible en un lector aislado; el proxy también respondió
200 con Influx detenido. No se borraron cachés ni datos. Influx quedó restaurado.
Esta evidencia corresponde al seed final; no certifica una reproducción en vivo
real ni una prueba de carga. P-001 ya está finalizado: para otra demo elegir otro
partido próximo y generar un plan nuevo, sin reiniciarlo.
