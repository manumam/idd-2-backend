# Observabilidad

Prometheus corre en Docker (este compose, proyecto `fixture2030-observabilidad`) y hace
*scrape* (modelo pull) de la API, que corre en el host (`bash scripts/iniciar_api.sh`) y
expone `GET /metrics`. Desde el contenedor la API se alcanza como
`host.docker.internal:8000`. Si cambiás `API_PORT`, ajustá el target en
`prometheus/prometheus.yml`.

| Pieza | Dónde corre | Puerto |
| --- | --- | --- |
| API (`/metrics`) | host | `API_PORT` (8000) |
| Bases (mongo, redis, influxdb) | `docker-compose.yaml` de la raíz | ver `.env` |
| Prometheus | este compose | `127.0.0.1:9090` |
| Exporters (mongodb, redis, node) | este compose | solo red interna |
| Simulador en vivo (`/metrics`) | host, solo mientras corre | `--puerto-metricas` (9105) |

Cada fuente es un job en `scrape_configs`; cada target lleva la etiqueta
`entorno` (`prueba` o `demo`). Las pruebas y la demo se envían a Grafana Cloud y los
dashboards filtran por `entorno`: Grafana Cloud no permite borrar series, así que la
etiqueta es lo que mantiene la vista de la demo limpia.

## Exporters

Un exporter traduce las estadísticas de una base a métricas de Prometheus. Alcanzan las
bases por `host.docker.internal` y el puerto publicado (`MONGO_PORT`, `REDIS_PORT`), así
que funcionan aunque cada base se haya levantado con otro compose. Por eso el compose se
levanta con `--env-file ../.env`.

| Job | Exporter | Qué aporta | Panel |
| --- | --- | --- | --- |
| `mongodb` | `percona/mongodb_exporter` | `mongodb_up`, conexiones (`mongodb_ss_connections`), operaciones por tipo (`mongodb_ss_opcounters`), memoria y uptime | Salud de MongoDB |
| `redis` | `oliver006/redis_exporter` | `redis_up`, `keyspace_hits/misses` (tasa de aciertos de caché), `evicted_keys`, `memory_used_bytes`, clientes conectados | Salud de Redis / caché |
| `node` | `prom/node-exporter` | CPU, memoria, disco y red de la máquina | Recursos del host |
| `influxdb` | ninguno: `/metrics` propio de InfluxDB 3 (`:8181`) | `http_requests_total` y latencia HTTP (el resto, histogramas internos de almacenamiento, se descarta) | Salud de InfluxDB |

## Simulador en vivo

El job `simulador` hace scrape de `host.docker.internal:9105`, el `/metrics` que
`scripts/simular_en_vivo.py` abre mientras juega un partido
([docs/simulador_en_vivo.md](../docs/simulador_en_vivo.md)). Escucha en `0.0.0.0` para
que el contenedor lo alcance; con otro `--puerto-metricas`, ajustar el target. Fuera de
una simulación el target figura `DOWN`: es lo esperado.

| Métrica | Tipo | Qué mide |
| --- | --- | --- |
| `simulador_ticks_aplicados_total` | counter | ticks del guion confirmados en MongoDB (9 por partido) |
| `simulador_puntos_escritos_total{tabla}` | counter | puntos escritos en InfluxDB por tabla |
| `simulador_puntos_rechazados_total{tabla}` | counter | puntos rechazados después de los reintentos |
| `simulador_segundo_de_juego` | gauge | último segundo de juego escrito (0–5400) |
| `simulador_retraso_segundos` | gauge | segundos reales que la escritura va detrás del reloj acelerado |

La única etiqueta propia es `tabla` (cuatro valores). El partido no es etiqueta: una
simulación por vez, identificada por el target y `entorno`. Usa un registro propio: no
publica las métricas `api_*` de los adaptadores que usa, así los paneles de la API no
mezclan sus escrituras.

Del exporter de MongoDB solo se guardan las métricas de la tabla (`metric_relabel_configs`):
el resto son ~2400 series y Grafana Cloud Free admite 10k activas.

En macOS, `node-exporter` mide la VM de Docker Desktop, no la Mac.

InfluxDB exige token también en `/metrics`. Prometheus lo lee de `secretos/influxdb_token`
(ignorado por git), que se genera con `python3 copiar_token_influx.py`: toma el token igual
que la API (`INFLUX_TOKEN` o `.influxdb3-token`) o, si no, el `admin_token.json` del compose
de la raíz. Sin ese archivo solo el job `influxdb` queda `DOWN`.

## Enviar a Grafana Cloud (prueba o demo)

1. Agregar al `.env` del backend (o exportar) los datos del stack de Grafana Cloud:

   ```
   GRAFANA_CLOUD_PROM_URL=     # URL de remote_write (https://.../api/prom/push)
   GRAFANA_CLOUD_PROM_USER=    # usuario / instance ID de Prometheus
   GRAFANA_CLOUD_PROM_TOKEN=   # token de acceso con permiso de escritura de métricas
   ```

2. Generar la config con el entorno y levantar con el override:

   ```bash
   bash scripts/iniciar_api.sh                     # desde la raíz del backend
   cd observabilidad
   python3 copiar_token_influx.py                  # una vez, o si cambia el token
   python3 generar_config.py --entorno prueba      # o --entorno demo para la corrida de la demo
   docker compose --env-file ../.env -f docker-compose.yaml -f docker-compose.nube.yaml up -d
   ```

`generar_config.py` copia `prometheus/prometheus.yml` con el `entorno` elegido, agrega
`remote_write` y escribe el token en un archivo aparte (`password_file`). Todo queda en
`generado/`, ignorado por git. Para cambiar de entorno: volver a generar la config y
reiniciar Prometheus (`docker compose ... restart prometheus`).

En Grafana Cloud Free una serie cuenta como activa si recibió datos en los últimos
20 minutos. Prueba y demo corriendo a la vez duplican las series; por separado no se suman.

## Dashboard

`grafana/war-room.json` es el dashboard "Fixture 2030 — War Room" (uid `fixture2030-war-room`)
publicado en Grafana Cloud. Usa el datasource `grafanacloud-prom` y la variable `entorno`
para mostrar solo `prueba` o solo `demo`. Secciones: disponibilidad y salud por base,
latencia (P50/P95/P99 contra el SLO de 100 ms) y throughput, errores, caché, saturación
(operaciones en curso por base, pool de MongoDB, CPU y memoria) y estado de MongoDB e
InfluxDB. Para recrearlo en otro stack: Dashboards → New → Import y pegar el JSON.

## Solo local (sin credenciales ni envío)

```bash
cd observabilidad
docker compose --env-file ../.env up -d
```

Usa `prometheus/prometheus.yml` tal cual (`entorno: prueba`, sin `remote_write`).

## Verificar y apagar

Revisar targets en http://localhost:9090/targets: todos los jobs tienen que figurar `UP`
(`api` solo si la API está corriendo).
Un target `UP` solo indica que el scrape funcionó, no que el sistema funcione: eso se
evalúa con las métricas (errores, latencia, etc.).

Para apagar, el mismo comando con `down` en lugar de `up -d`. Los datos locales quedan
en los volúmenes `prometheus_data` (solo local) y `prometheus_nube_data` (con envío).
