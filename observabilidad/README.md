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

Cada fuente es un job en `scrape_configs`; cada target lleva la etiqueta
`entorno` (`prueba` o `demo`) para que los datos de prueba no se mezclen con los de la demo.

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

Del exporter de MongoDB solo se guardan las métricas de la tabla (`metric_relabel_configs`):
el resto son ~2400 series y Grafana Cloud Free admite 10k activas.

En macOS, `node-exporter` mide la VM de Docker Desktop, no la Mac.

InfluxDB exige token también en `/metrics`. Prometheus lo lee de `secretos/influxdb_token`
(ignorado por git), que se genera con `python3 copiar_token_influx.py`: toma el token igual
que la API (`INFLUX_TOKEN` o `.influxdb3-token`) o, si no, el `admin_token.json` del compose
de la raíz. Sin ese archivo solo el job `influxdb` queda `DOWN`.

## Modo prueba (local, sin envío a Grafana Cloud)

```bash
bash scripts/iniciar_api.sh                     # desde la raíz del backend
cd observabilidad
python3 copiar_token_influx.py                  # una vez, o si cambia el token
docker compose --env-file ../.env up -d
```

Revisar targets en http://localhost:9090/targets: todos los jobs tienen que figurar `UP`
(`api` solo si la API está corriendo).
Un target `UP` solo indica que el scrape funcionó, no que el sistema funcione: eso se
evalúa con las métricas (errores, latencia, etc.).

Para apagar: `docker compose down` (los datos quedan en el volumen `prometheus_data`).

## Modo demo (entorno=demo + envío a Grafana Cloud)

1. Agregar al `.env` del backend (o exportar) los datos del stack de Grafana Cloud:

   ```
   GRAFANA_CLOUD_PROM_URL=     # URL de remote_write (https://.../api/prom/push)
   GRAFANA_CLOUD_PROM_USER=    # usuario / instance ID de Prometheus
   GRAFANA_CLOUD_PROM_TOKEN=   # token de acceso con permiso de escritura de métricas
   ```

2. Generar la config y levantar con el override:

   ```bash
   cd observabilidad
   docker compose down                              # si estaba en modo prueba
   python3 generar_config_demo.py
   docker compose --env-file ../.env -f docker-compose.yaml -f docker-compose.demo.yaml up -d
   ```

`generar_config_demo.py` copia `prometheus/prometheus.yml` cambiando `entorno: prueba`
por `entorno: demo`, agrega `remote_write` y escribe el token en un archivo aparte
(`password_file`). Todo queda en `generado/`, ignorado por git. El modo demo usa el
volumen `prometheus_demo_data`, separado del de prueba.

Para volver a prueba: `docker compose -f docker-compose.yaml -f docker-compose.demo.yaml down`
y `docker compose --env-file ../.env up -d`.
