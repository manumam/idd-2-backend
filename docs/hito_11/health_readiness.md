# Liveness, readiness y diagnóstico

| Ruta | Objetivo | Respuesta | Costo |
| --- | --- | --- | --- |
| GET /live | Proceso HTTP activo | 200, estado alive | Sin consultas a motores |
| GET /health | Diagnóstico individual de conectividad | 200 con up/down por fuente | Cuatro pings en paralelo |
| GET /ready | Readiness básica de conectividad | 200 listo=true si todos los pings pasan; 503 listo=false si alguno falla | Cuatro pings en paralelo |

Las cuatro dependencias son requeridas para readiness global. La API puede seguir atendiendo módulos sanos con otra fuente caída; por eso /live sigue activo y /health conserva el estado individual. Readiness no comprueba que todos los endpoints de negocio puedan responder con datos. En particular, el health HTTP de Influx no verifica database ni permisos SQL; el CLI de lecturas profundas sí prueba el contexto configurado.

Los chequeos se ejecutan solo al solicitar estas rutas; no hay tarea periódica ni consultas de todas las bases en requests de negocio. El laboratorio configura DB_TIMEOUT_SECONDS=3. Cada driver limita sus fases de conexión/consulta; no es un deadline global de 3 segundos para HTTP. Se usan cuatro workers por evaluación y se cierran al terminar. No se realizan reintentos ilimitados. Un ping fallido, incluso inesperado, se marca down y no oculta el resultado de las demás fuentes.

Frecuencia operativa propuesta: /live cada 30 segundos y /ready cada 30 segundos, sin solapar evaluaciones. Esto genera como máximo cuatro pings por evaluación de readiness; /health queda bajo demanda para diagnóstico. No se ejecutan lecturas de dominio desde estos endpoints. No se configuró un orquestador de producción ni se afirma un SLA de latencia.

La evidencia de falla Redis registra /live=200, /health=200 con redis=down, /ready=503 y GET de sesión=503. Después de restaurar Redis, /ready y GET de sesión vuelven a 200 sin eliminar volúmenes. Ver `evidencia/falla_redis.json` y `evidencia/api_cierre.log`.
