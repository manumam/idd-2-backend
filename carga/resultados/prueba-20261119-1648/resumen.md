# Corrida de carga — entorno prueba (2026-11-19)

Inicio 2026-11-19T19:48:12Z · fin 2026-11-19T19:53:44Z. Escenario por defecto de
`carga/config/escenario.json`: 30 usuarios (20 partido P-002, 6 fixture, 2 grupos, 2 playoffs),
rampa 30 s, sostenimiento 300 s. P-002 estaba en estado `proximo` (el front lo consulta igual).
Métricas del cliente calculadas del `.jtl` descartando la rampa.

| Medida | Cliente (JMeter) | Servidor (Prometheus en Grafana Cloud) | SLO |
| --- | --- | --- | --- |
| Throughput | 10,0 req/s (2.988 en 299 s) | 10,0 req/s | — |
| Errores | 0 | 0 respuestas 5xx | ≥ 99,99 % sin 5xx |
| P50 / P95 / P99 | 6 / 16 / 23 ms (máx. 86 ms) | P95 16 ms | P95 < 100 ms |
| P95 por base | — | MongoDB 8,5 ms · InfluxDB 9,4 ms · Redis 4,8 ms | — |

| Ruta | n | P50 | P95 | P99 (ms) |
| --- | --- | --- | --- | --- |
| `/partidos/{codigo}` | 1198 | 8 | 15 | 19 |
| `/partidos/{codigo}/eventos` | 1198 | 4 | 8 | 11 |
| `/partidos/{codigo}/alineaciones` | 398 | 10 | 23 | 27 |
| `/fixture` | 118 | 11 | 24 | 50 |
| `/grupos/{id}/posiciones` | 38 | 12 | 28 | 73 |
| `/playoffs` | 38 | 12 | 23 | 63 |

Caché (`api_cache_total`, ventana de 5 min): partido 93 % hit, eventos 92 %, alineaciones 77 %,
fixture 55 %, playoffs y posiciones 50 %. Con TTL de 5 s, las páginas que consultan cada 15 s
encuentran la copia vencida en casi la mitad de las lecturas: es la hipótesis a probar en la
próxima corrida (cambiar solo el TTL y repetir, Clase 13).

Saturación: operaciones en curso por base en 0 en cada scrape; la carga está lejos del límite.

Archivos: `resultados.jtl` (una fila por request), `jmeter.log`, `consola.txt`,
`inicio_utc.txt`, `fin_utc.txt`. Dashboard: "Fixture 2030 — War Room", entorno `prueba`,
rango 19:48–19:54 UTC.
