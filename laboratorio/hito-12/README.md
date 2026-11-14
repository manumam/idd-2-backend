# Hito 12: instrumentación y configuración del experimento

La entrega reproducible, el orquestador, el plan JMeter y la evidencia de las 18 corridas se conservan en este backend: [entrega Hito 12](../../hito-12/README.md).

El flujo medido es `GET /fixture`: MongoDB más Cache-Aside en Redis. La instrumentación agrega `fixture_cache=hit` después de validar una copia y `fixture_cache=miss` antes de reconstruirla; ambos mensajes se mantienen iguales en línea base y variante. Se reutilizan los tiempos y `X-Request-Id` del middleware y los adaptadores. No cambia el contrato HTTP.

El experimento compara `FIXTURE_CACHE_TTL_SECONDS=5` con `15` por variable de entorno al iniciar la API del laboratorio. El valor por defecto de la aplicación permanece en 5 s. Un TTL de 15 s se evalúa sólo para consultas previas al partido; aumenta la antigüedad posible cuando falta la invalidación y no se adopta como configuración del marcador en vivo.

Los datos, fuentes y dependencias exactos usados están preservados mediante snapshot con SHA-256 en `hito-12/evidencia/`, porque el backend tenía cambios locales al comenzar. La comparación incluye latencia, throughput, consultas, errores, recursos e integridad; no se declaran capacidades productivas a partir de esta prueba local.
