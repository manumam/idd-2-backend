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

Cada fuente es un job en `scrape_configs`; cada target lleva la etiqueta
`entorno` (`prueba` o `demo`) para que los datos de prueba no se mezclen con los de la demo.

## Modo prueba (local, sin envío a Grafana Cloud)

```bash
bash scripts/iniciar_api.sh                     # desde la raíz del backend
cd observabilidad
docker compose up -d
```

Revisar targets en http://localhost:9090/targets: el job `api` tiene que figurar `UP`.
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
   docker compose -f docker-compose.yaml -f docker-compose.demo.yaml up -d
   ```

`generar_config_demo.py` copia `prometheus/prometheus.yml` cambiando `entorno: prueba`
por `entorno: demo`, agrega `remote_write` y escribe el token en un archivo aparte
(`password_file`). Todo queda en `generado/`, ignorado por git. El modo demo usa el
volumen `prometheus_demo_data`, separado del de prueba.

Para volver a prueba: `docker compose -f docker-compose.yaml -f docker-compose.demo.yaml down`
y `docker compose up -d`.
