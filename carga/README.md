# Prueba de carga con el polling del frontend

Prueba de carga para obtener evidencia de monitoreo (Clase 14): JMeter reproduce las consultas periódicas que hace el frontend mientras un espectador tiene una página abierta. No es una prueba de estrés ni de capacidad; los valores del escenario son parámetros, no una afirmación sobre cuánto soporta la API.

Esta carpeta todavía no contiene resultados. La ejecución y la evidencia (resultados de JMeter y capturas del monitoreo) se agregan en un commit posterior.

## Qué simula y por qué

Una prueba que carga una sola operación (por ejemplo `GET /fixture`) no representa el uso real. La Clase 13 pide que el generador represente patrones reales y no una única consulta artificial. El patrón real de lectura del sistema es el polling del frontend: cada página abierta repite sus consultas con `setInterval` mientras el partido no terminó. Por eso cada usuario virtual es una pestaña abierta en una página.

| Página | Usuarios por defecto | Consultas | Intervalo | Origen en `idd-2-frontend` |
| --- | --- | --- | --- | --- |
| Partido en vivo | 20 | `GET /partidos/{codigo}` y `GET /partidos/{codigo}/eventos?limit=200&skip=0` | 5 s | `src/components/PartidoDetalle.tsx:30` |
| | | `GET /partidos/{codigo}/alineaciones` | 15 s | `src/components/Alineaciones.tsx:46` |
| Fixture | 6 | `GET /fixture` | 15 s | `src/hooks/useFixture.ts:5` |
| Grupos | 2 | `GET /grupos` al abrir; `GET /grupos/{id}/posiciones` | 15 s | `src/components/Grupos.tsx:15` |
| Playoffs | 2 | `GET /playoffs` | 15 s | `src/components/Playoffs.tsx:44` |

La mayoría de los usuarios está en la página del partido porque la prueba representa el escenario "partido en vivo" de la Clase 13. Con los valores por defecto se esperan alrededor de 10 requests/s en régimen (20 × 7/15 + 6/15 + 2/15 + 2/15).

Cómo se imita al navegador:

- Cada página hace sus consultas al abrirse y luego en cada tick. El tick se agenda desde la apertura, como `setInterval`, y no desde el fin de la respuesta.
- Si una respuesta tarda más que el intervalo, ese tick se pierde: el usuario espera la respuesta antes de volver a consultar (carga cerrada).
- Timeout HTTP de 10 s y cabecera `Accept: application/json`, como `useApi.ts` y `useFixture.ts`.
- Las rutas no llevan `/api`: ese prefijo sólo existe en el proxy de Vite, que lo quita antes de llegar al backend.

El front deja de consultar el detalle y las alineaciones cuando el partido está finalizado. Por eso el partido por defecto es `P-002`, que el escenario demo de `data/fixture` deja en vivo y que tiene alineaciones cargadas. Si el partido se finaliza (por ejemplo, con el simulador del caso 7) durante la prueba, JMeter seguirá consultando y ya no representaría al front.

## Escenario

`config/escenario.json` define URL de la API, partido, grupo, rampa, sostenimiento, timeout, usuarios por página e intervalos. Las fases siguen la Clase 13: rampa (subir usuarios) y sostenimiento (observar estabilidad). Por defecto, 30 s de rampa y 300 s de sostenimiento, para que el monitoreo tenga varios minutos con la concurrencia completa. La rampa se descarta al analizar.

## Generar el plan

Desde la raíz del backend, sin dependencias externas:

```bash
python3 carga/carga/generar_jmx.py
```

Escribe `carga/carga/polling_front.jmx` con los valores del escenario como valores por defecto. Volver a generarlo después de cambiar `escenario.json`.

## Ejecutar (commit posterior)

Requisitos: Java 21 y Apache JMeter 5.6.3, y la API levantada en `api_url` (por defecto `http://127.0.0.1:8000`) con fixture, grupos, playoffs y alineaciones cargados en MongoDB. Comprobar antes que `GET /partidos/P-002` responda con estado `en_vivo`.

```bash
jmeter -n -t carga/carga/polling_front.jmx -l <carpeta de resultados>/resultados.jtl
```

Cualquier valor se puede cambiar sin regenerar el plan con `-J`: `-Jhost`, `-Jpuerto`, `-Jprotocolo`, `-Jpartido`, `-Jgrupo`, `-Jrampa`, `-Jsostenimiento`, `-Jtimeout`, `-Jusuarios_partido`, `-Jusuarios_fixture`, `-Jusuarios_grupos`, `-Jusuarios_playoffs`, `-Jintervalo_partido`, `-Jintervalo_fixture`, `-Jintervalo_grupos` y `-Jintervalo_playoffs`. Una prueba de humo (Clase 13) es la misma ejecución con un usuario por página y un sostenimiento corto. La frecuencia de las alineaciones es la de un tick de partido cada tres y queda fija al generar el plan.
