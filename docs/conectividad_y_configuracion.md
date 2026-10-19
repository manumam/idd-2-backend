# Conectividad y configuración

La API se ejecuta en la notebook, fuera de Docker. Los servicios de los hitos previos
mantienen sus propios volúmenes y cargas; no se migran ni se inicializan al importar la API.

1. Clonar `https://github.com/mateolewinzon/idd-2-tp` junto a este repositorio.
2. En `fixture2030-mongo`, `fixture2030-neo4j`, `fixture2030-cassandra`,
   `fixture2030-redis` y `fixture2030-influxdb`,
   seguir el README propio: `docker compose up -d`, esperar disponibilidad y ejecutar
   los scripts de esquema y datos indicados por cada módulo. No ejecutar cargas
   masivas para probar esta API; alcanza el conjunto sintético representativo.
3. Cassandra: cargar `scripts/esquema.cql` antes de los comentarios. El keyspace es
   `fixture2030_comentarios`, datacenter `datacenter1` salvo configuración distinta.
5. Configurar `.env` con los valores reales locales y ejecutar
   `python scripts/verificar_conectividad.py`. Salida no cero si alguna fuente falla.
6. Iniciar Uvicorn y ejecutar los ejemplos HTTP y tests según el README.

| Variables principales | Valor local sugerido |
| --- | --- |
| `MONGO_URI`, `MONGO_DATABASE` | `mongodb://localhost:27017`, `fixture2030` |
| `NEO4J_URI`, `NEO4J_DATABASE` | `bolt://localhost:7687`, `neo4j` |
| `CASSANDRA_HOSTS`, `CASSANDRA_PORT`, `CASSANDRA_KEYSPACE` | `localhost`, `9042`, `fixture2030_comentarios` |
| `CASSANDRA_LOCAL_DC` | `datacenter1` |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | `localhost`, `6380`, `0` |
| `INFLUX_URL`, `INFLUX_DATABASE` | `http://127.0.0.1:8181`, `fixture2030_resumen` |
| `DB_TIMEOUT_SECONDS` | `5` |

Hosts y puertos deben coincidir con los mappings del Compose de cada módulo.
`NEO4J_USER/PASSWORD`, `REDIS_PASSWORD`, `INFLUX_TOKEN`
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

Detener con Ctrl+C y `docker compose stop` en cada módulo; conservar volúmenes.
No publicar `.env`, archivos token, dumps o logs del motor con credenciales.

Si el proceso hereda un proxy HTTP corporativo o del entorno cloud, conservarlo para
Internet y añadir `localhost,127.0.0.1` a `NO_PROXY` para las conexiones HTTP locales
(Influx y cURL). No enviar solicitudes a las bases locales a través del proxy externo.
