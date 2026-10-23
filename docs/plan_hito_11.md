# Plan de trabajo: Hito 11 - Evaluación de conectividad

Fecha: 2026-10-23. Alcance: trabajar en este backend, extendiendo el Hito 10.
Este documento conserva el plan inicial. El cierre ejecutado, resultados actuales y limitaciones están en `docs/hito_11/README.md` y `docs/hito_11/matriz_de_conectividad.md`.

## Punto de partida

- FastAPI y adaptadores para MongoDB, Neo4j, Redis e InfluxDB 3.
- Configuración externa, timeout configurable, request ID y logs de operaciones con duración.
- CLI `scripts/verificar_conectividad.py`: prueba `ping` de todos los adaptadores, pero no separa capas ni permite seleccionar producto o generar evidencia estructurada.
- `/health` devuelve 200 con estado por fuente; no garantiza lectura del contexto de dominio. En particular, el health HTTP de Influx no demuestra autorización para consultar su database.
- Pruebas unitarias e integración optativa existentes. La evidencia del 16 de octubre corresponde al Hito 10 y a otro entorno; no reutilizarla como ejecución del Hito 11.
- IRIS no está integrado: documentarlo como fuera del alcance/no configurado.
- Topología documentada: API Python en la notebook y bases en Docker. El Compose actual reutiliza persistencia y rutas del laboratorio anterior; un laboratorio aislado necesita su propia configuración y volúmenes.

## 1. Inventario y preparación

- Crear `docs/hito_11/` con índice, mapa de dependencias, topología, matriz, fallas, health/readiness, limitaciones y `evidencia/`.
- Registrar por motor: módulo, origen de conexión, host, puertos publicados/internos, protocolo, contexto, mecanismo de identidad, driver, lectura y rutas relacionadas.
- Verificar requisitos locales, versiones instaladas, disponibilidad de Docker y datos representativos sin imprimir `.env` ni secretos.
- Revisar ejemplos y Compose: externalizar la contraseña Neo4j que hoy está escrita en el YAML; evitar valores secretos en resultados y documentación.

Salida: inventario reproducible y configuración de ejemplo sin secretos.

## 2. Diagnóstico automatizado por capas

- Extender el script existente o delegar a módulos reutilizables, conservando una entrada CLI clara.
- Ofrecer modos completo, configuración/resolución, TCP, clientes/drivers y API; filtro por producto y capa, salida terminal y JSON.
- Evaluar en orden: configuración, resolución, TCP, protocolo, autenticación, autorización, contexto y lectura mínima.
- Distinguir rechazo TCP, timeout, resolución fallida, autenticación, autorización, contexto incorrecto y consulta inválida cuando la evidencia del driver lo permita. Si una prueba combina capas, explicitar qué verifica y qué queda desconocido.
- Aplicar límites de tiempo, cerrar conexiones y evitar reintentos ilimitados. Conservar resultados parciales aunque otra fuente falle.
- Registrar timestamp con zona horaria, entorno/origen, versión, producto, capa, prueba, estado, duración, diagnóstico y próximo paso.
- Definir disponible, no disponible, degradado, no probado y desconocido; `SKIP` significa no ejecutado por falta de herramienta/configuración, nunca caída.
- Usar una lista explícita de campos seguros para las salidas: excluir credenciales, URI completas con secretos, respuestas de dominio y mensajes crudos de drivers.

Salida: diagnóstico ejecutable por producto, por capa y completo, con resumen estructurado.

## 3. Verificaciones específicas

| Producto | Prueba mínima y distinciones |
| --- | --- |
| MongoDB | Driver, ping y lectura acotada de equipos/jugadores; contexto y colección existentes frente a documento ausente. No inferir existencia de database de una consulta vacía. |
| Neo4j | Diferenciar Browser HTTP 7474 de Bolt 7687; identidad, database y Cypher parametrizado de lectura limitada. |
| Redis | RESP/PING, identidad si aplica, base lógica, lectura y TTL; una clave ausente no prueba que haya expirado: para afirmar expiración hace falta observación previa o evidencia del fixture. |
| InfluxDB 3 | HTTP health, token/permisos, database y consulta temporal acotada; distinguir ausencia de puntos de fallas de acceso o contexto. |
| IRIS | Registrar no configurado/fuera del alcance, sin inventar pruebas de portal o Superserver. |

Usar los drivers Python ya instalados como clientes adecuados. Las herramientas CLI adicionales serán opcionales y su ausencia quedará registrada. Las verificaciones no escribirán ni borrarán datos; la preparación de fixtures será una etapa separada y explícita.

## 4. Cadena HTTP completa y errores

- Ejecutar solicitudes HTTP reales a Uvicorn para las rutas de lectura de equipos, jugadores, partidos, eventos, goleadores, sesiones, estadísticas y health.
- Registrar método/path, parámetros seguros, dependencia, HTTP, duración, request ID, resumen e identificación del log asociado.
- Incluir éxito, lista vacía válida, recurso inexistente, parámetros inválidos, API inaccesible y API accesible con dependencia fallida.
- Excluir DELETE de sesiones del diagnóstico de solo lectura; documentar esa decisión y conservar su cobertura funcional existente.
- Revisar las excepciones de los adaptadores: hoy disponibilidad y timeout se agrupan en `DatabaseUnavailableError`/503. Dar al timeout una identificación propia y definir/documentar su código HTTP, sin exponer detalles del driver.
- Verificar error interno controlado y conservar diferencias respecto de 400, 404 y fallo de dependencia.
- Si cambia el contrato público, actualizar rutas/schemas, OpenAPI exportado, Postman y documentación en el mismo cambio, conforme a `AGENTS.md`.

Salida: evidencia HTTP correlacionada y errores inequívocos.

## 5. Liveness, readiness y diagnóstico

- Conservar y documentar el significado actual de `/health` para no romper consumidores.
- Propuesta: agregar `/live` sin consultar motores y `/ready` con 200 si todas las dependencias integradas requeridas pasan el chequeo definido, 503 si alguna falla.
- Separar readiness básica de las lecturas profundas de dominio del CLI; documentar exactamente qué asegura cada prueba.
- Definir timeout, frecuencia y costo de los chequeos. Ejecutar diagnósticos profundos bajo demanda, sin consultar todos los motores por cada request de negocio.
- Incluir estas rutas en OpenAPI, Postman y pruebas si se implementan.

## 6. Falla controlada y recuperación

- Entorno elegido: Redis en laboratorio aislado. Registrar lectura inicial y PING/TTL, detener solo ese servicio, repetir diagnóstico y GET de sesión, restaurarlo y repetir.
- Registrar estado antes/durante/después, comando aplicado, HTTP, request ID, logs, tiempos y persistencia conservada.
- Preparar recuperación garantizada ante interrupción o error; no usar `down -v`, borrar volúmenes ni eliminar datos.
- Si se eligen las bases actuales, acordar la ventana de detención antes de interrumpir el servicio.
- Complementar con simulaciones de errores de identidad, contexto y timeout, identificándolas como simulaciones; no presentarlas como ejecuciones reales.

Salida: evidencia real de transición disponible -> caída -> recuperada.

## 7. Verificación y cierre

- Ejecutar la suite existente y agregar pruebas relevantes de clasificación de fallas, límites de espera, salida sin secretos, resultados parciales y códigos de salida del CLI.
- Ejecutar integración por motor disponible, diagnóstico completo y casos HTTP contra el entorno elegido.
- Construir la matriz desde los resultados reales. Mantener no probado/desconocido en lo no ejecutado y registrar hipótesis, prueba y siguiente paso por falla.
- Revisar resultados y logs antes de versionarlos; no almacenar cuerpos innecesarios ni datos sensibles.
- Actualizar README con preparación, variables, orden de ejecución, recuperación y limitaciones. Separar evidencia Hito 10 e Hito 11.
- Comprobar igualdad de operaciones y parámetros OpenAPI/Postman si hay cambios de API.
- Preparar commits identificables por etapas. La publicación en GitHub queda como paso de entrega, sin afirmar que ocurrió hasta ejecutarla.

## Orden sugerido y entorno definido

Implementar primero inventario y CLI; después pruebas por motor y HTTP; luego health/errores; finalmente falla controlada, evidencia y documentación final.

Decisión confirmada por el usuario: laboratorio aislado con fixtures mínimos. Preparar un Compose específico con nombres de contenedores, puertos y volúmenes propios, sin reutilizar la persistencia del Compose actual. Ejecutar la API desde la notebook contra los puertos publicados del laboratorio. Usar el laboratorio sin autenticación y publicado solo en loopback y Redis como dependencia para la falla controlada y recuperación. La preparación de datos queda separada del diagnóstico de solo lectura.

## Criterio de entrega completa

Un compañero puede preparar el entorno, ejecutar una sola dependencia o todo el procedimiento, interpretar cada capa, correlacionar solicitudes con logs y reproducir una falla con recuperación. La matriz acredita únicamente pruebas ejecutadas, conserva las limitaciones y no contiene secretos. No se requieren frontend, presentación, video ni pruebas de carga masiva para este hito.
