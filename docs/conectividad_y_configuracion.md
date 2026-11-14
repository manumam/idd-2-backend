# Conectividad y configuración

> Describe la implementación actual. El objetivo del MVP está en el
> [modelo técnico](modelo-tecnico-demo.md); las diferencias se registran en el
> [seguimiento](casos_de_uso.md).

La configuración siguiente corresponde a la API actual; varias dependencias históricas están pendientes de retirar.

La API se ejecuta localmente, fuera de Docker, con `.env`. Para fixture y
planteles basta iniciar `docker compose up -d mongo redis` y luego
`bash scripts/iniciar_api.sh`. No se inicia el laboratorio ni se cargan datos.
MongoDB conserva su volumen normal y publica `MONGO_PORT` (27018 por defecto)
solo en loopback; `MONGO_URI` debe coincidir. Redis usa 6380 por defecto.

Para importar archivos MongoDB, agregar explícitamente
`-f docker-compose.yaml -f docker-compose.imports.yaml` al comando Compose.
El override monta los directorios del repositorio `idd-2-tp`, cuya raíz se
configura con `TP_DATA_DIR` (por defecto `../idd-2-tp`). No ejecuta imports.
Los demás motores del Compose normal aún requieren los montajes de ese repositorio.
IRIS se inicia aparte. Las conexiones y credenciales se configuran en `.env`;
no usar las del laboratorio para abrir la app.

| Variables principales | Valor local sugerido |
| --- | --- |
| `MONGO_URI`, `MONGO_DATABASE` | `mongodb://127.0.0.1:27018`, `fixture2030` |
| `NEO4J_URI`, `NEO4J_DATABASE` | `bolt://localhost:7687`, `neo4j` |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | `localhost`, `6380`, `0` |
| `INFLUX_URL`, `INFLUX_DATABASE` | `http://127.0.0.1:8181`, `fixture2030_resumen` |
| `CASSANDRA_HOSTS`, `CASSANDRA_PORT`, `CASSANDRA_KEYSPACE` | `localhost`, `9042`, `fixture2030_comentarios` |
| `CASSANDRA_LOCAL_DC` | `datacenter1` |
| `IRIS_HOST`, `IRIS_PORT`, `IRIS_NAMESPACE` | `127.0.0.1`, `1972`, `USER` |
| `DB_TIMEOUT_SECONDS` | `5` |

Hosts y puertos deben coincidir con los mappings de `docker-compose.yaml`.
`NEO4J_USER/PASSWORD`, `REDIS_PASSWORD`, `INFLUX_TOKEN`, `IRIS_USER/PASSWORD`
se configuran localmente; no copiar credenciales reales a ejemplos ni capturas.
Influx acepta token por variable o archivo local `.influxdb3-token`; se recomienda
la variable para evitar depender del directorio de trabajo. No se necesitan tokens
ni credenciales para la suite unitaria.

Desde otro contenedor, `localhost` es ese contenedor: unir la API a la red del
servicio y usar nombre DNS y puerto interno (Redis 6379, por ejemplo). No usar el
puerto publicado del host como si fuese el puerto interno. El repositorio no
incluye una imagen de la API; el procedimiento de referencia es ejecutar Python
en la notebook. Docker Desktop y Linux pueden requerir hosts distintos.

`/health` prueba conexiones (en Influx /health), pero no garantiza
que existan tablas, clases o datos. Los tests `LIVE_MODULES` sí consultan los
endpoints de dominio y exigen resultados no vacíos. Si falla una fuente, revisar
puerto, namespace/keyspace, carga de esquema, permisos y timeout en ese orden.

Detener la API con Ctrl+C y las bases con `docker compose stop` desde la raíz del backend;
conservar volúmenes.
No publicar `.env`, archivos token, dumps o logs del motor con credenciales.

Si el proceso hereda un proxy HTTP corporativo o del entorno cloud, conservarlo para
Internet y añadir `localhost,127.0.0.1` a `NO_PROXY` para las conexiones HTTP locales
(Influx y cURL). No enviar solicitudes a las bases locales a través del proxy externo.
