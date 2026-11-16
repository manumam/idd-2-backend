# Seguimiento de los casos de uso del MVP

El alcance se define en [lineamientos](lineamientos-entrega-demo.md),
[casos de uso](casos-de-uso-fixture.md) y [modelo técnico](modelo-tecnico-demo.md).
La implementación se contrasta con esos requisitos; la existencia de una ruta
histórica no demuestra cumplimiento. Stack objetivo: MongoDB, Redis e InfluxDB.

Los lineamientos originales limitaban la entrega a la API. El trabajo posterior
solicitado incorpora el frontend del fixture, los grupos, los planteles y la ficha de jugador.
Esta ampliación no cambia las decisiones de persistencia del MVP.

## Estado de implementación

El estado funcional y la alineación técnica se evalúan por separado. Usar una
base prevista por el modelo no completa por sí solo un caso de uso. «Pendiente»
significa que el modelo todavía no está implementado para ese caso, no que se
haya validado su cumplimiento. El caso 3 está implementado en ambos repositorios; su comprobación con motores
reales requiere la configuración local y la carga explícita de grupos. Los demás
casos conservan las brechas detalladas abajo.

| # | Caso del MVP | Estado funcional | Alineación con el modelo técnico | Trabajo pendiente para completarlo |
| --- | --- | --- | --- | --- |
| 1 | Consultar el fixture | Listado implementado; demo en vivo incompleta | Parcial: `GET /fixture` usa MongoDB y Cache-Aside en Redis, como se propone. La API no admite todavía `equipo_id`, `fecha` ni `fase`; los filtros actuales se aplican en el frontend. | Completar los filtros del contrato propuesto y sus claves de caché. Vincular ingesta, cierre y correcciones con la invalidación. El frontend muestra orden, horario, fase, estado y resultado, pero falta el simulador que avance el torneo. |
| 2 | Consultar los partidos de una selección | Parcial: búsqueda de texto, sin recorrido específico por selección | Parcial: reutiliza el fixture de MongoDB/Redis, pero no existe el filtro de API por identificador de selección propuesto en `/fixture?equipo_id=…`. | Seleccionar un equipo desde el fixture debe abrir sus partidos próximos, en vivo y finalizados, en lugar de su plantel. Agregar filtro exacto por código y caché que lo incluya. La búsqueda por nombre no equivale al flujo completo. |
| 3 | Consultar el estado de los grupos | Implementado en backend y frontend; verificación real pendiente | Grupos, participantes y reglas explícitas en MongoDB; cálculo desde resultados finalizados, sin tandas. Orden por puntos, DG, GF y desempate del dataset. Caché Redis opcional versionada por todas las entradas. | Cargar grupos de forma explícita con `scripts/cargar_grupos.py` y verificar con MongoDB del proyecto. La vista permite elegir grupo, consultar PJ/PG/PE/PP/GF/GC/DG/puntos y abrir sus partidos. La página central de detalle corresponde al caso 5. |
| 4 | Consultar los playoffs | Pendiente; solo hay encuentros eliminatorios en el fixture | Sin implementar: el modelo pide cruces en MongoDB con origen de plazas, orden y ganador, y copia derivada en Redis. | Implementar `/playoffs`, carga y validación de dependencias sin ciclos, resolución idempotente de plazas y propagación de ganadores, incluidas tandas. Invalidar ante cierres/correcciones y agregar el cuadro navegable. |
| 5 | Ver el detalle de un partido | Ruta histórica disponible; falta la página del encuentro | No alineado: `/partidos/{codigo}` sigue consultando Neo4j. El objetivo es MongoDB con caché Redis. | Migrar la lectura a MongoDB y completar sede, estado, marcador y reloj de juego, con goles de tanda separados. Implementar caché e invalidación y una página accesible desde fixture, grupos y playoffs. |
| 6 | Consultar las alineaciones | Pendiente | Sin implementar: el modelo pide titulares y suplentes dentro del documento de partido en MongoDB, con caché Redis. | Implementar `/partidos/{id}/alineaciones`, referencias a jugadores y navegación al rendimiento individual. Cargar alineaciones por encuentro; el plantel de selección no las reemplaza. |
| 7 | Seguir los eventos del partido | Ruta histórica disponible; sin seguimiento en vivo | No alineado: los eventos se leen de Neo4j; el objetivo es eventos embebidos en MongoDB y caché Redis. | Migrar persistencia y lectura, identificar eventos para evitar duplicados, actualizar marcador e invalidar eventos/partido/estadísticas al ingresar datos. Agregar ingesta del simulador y cronología con actualización en vivo. |
| 8 | Comparar estadísticas de equipos | Lectura temporal parcial; falta comparación completa en el frontend | Parcial: Influx contiene posesión, tiros y pases. Falta el Aggregator con eventos de MongoDB, los resúmenes finales en MongoDB y la caché Redis. | Completar goles y tarjetas, combinar ambas fuentes en vivo, consolidar de forma idempotente e indicar estado provisional/final. Las estadísticas finales deben poder leerse con Influx caído y caché vacía; agregar comparación y actualización en el frontend. |
| 9 | Rendimiento de un jugador en el partido | Pendiente; solo existe ficha personal | Sin implementar: faltan estadísticas deportivas desde eventos MongoDB y físicas desde Influx, resúmenes finales por partido/jugador en MongoDB y caché Redis. | Implementar `/partidos/{id}/jugadores/{jugador_id}/estadisticas` y acumulados en `/jugadores/{id}/estadisticas`, con consolidación y sin doble conteo. Mostrar goles, asistencias, tarjetas, distancia y velocidad máxima desde la alineación. |
| 10 | Mapa de calor de un jugador | Pendiente | Sin implementar: el objetivo usa tracking crudo de Influx en vivo, ocupación por celda/minuto para histórico y caché Redis por filtros. | Implementar endpoint, grilla e intervalos efectivos, materialización antes de vencer el crudo y reproceso idempotente. Validar consultas históricas en InfluxDB Core y mostrar cancha e intervalos en el frontend. No usar promedios de coordenadas como mapa de calor. |
| 11 (opcional) | Seguir la pelota en vivo | Pendiente | Sin implementar: el objetivo consulta la última muestra de `tracking_pelota` en Influx y la cachea en Redis con TTL corto. | Implementar `/partidos/{id}/pelota`, simulación a 1 Hz y visualización con actualización durante el partido en vivo. No prometer trayectoria histórica después de vencer el tracking crudo. |

### Balance de los requisitos 1 a 3

- **1:** alineado en la elección de MongoDB y Redis y en el listado visible;
  parcialmente alineado con el modelo completo por los filtros de API y el ciclo
  de actualización e invalidación pendientes. No equivale a tener la demo en vivo completa.
- **2:** parcialmente alineado en las fuentes reutilizadas; el flujo de selección
  y el filtro exacto por equipo siguen pendientes. Consultar un plantel no lo cumple.
- **3:** implementado con MongoDB y Redis, reglas versionadas, clasificación
  recalculable y vista de grupos. Los tests locales cubren cálculos, desempates,
  cierres, correcciones y fallos; no certifican un recorrido con motores reales.
  La ficha personal del jugador es una funcionalidad adicional.

## Funcionalidades adicionales implementadas

- Catálogo de equipos, ficha de selección y planteles desde MongoDB.
- Ficha personal de jugador: `GET /jugadores/{codigo}` y página independiente
  `/jugador.html?codigo=ARG-10`, con regreso al plantel y estados de carga/error.
  No corresponde al caso 3 ni reemplaza los casos 9 y 10 del MVP.

## Brechas transversales

- Retirar Neo4j, Cassandra, IRIS y sesiones del runtime y del contrato público
  cuando se implemente la migración; hoy siguen expuestos.
- Adaptar `/ready` y `/health` al stack de tres bases; hoy comprueban seis fuentes.
- Implementar simulador, ingesta validada, consolidación idempotente e invalidación.
- Completar cachés por funcionalidad y observabilidad Prometheus/Grafana.
- Validar los contratos propuestos antes de implementarlos. OpenAPI y Postman
  describen la API actual y solo deben cambiar junto con sus rutas y schemas.

El contrato HTTP implementado se consulta en [OpenAPI](../openapi/openapi.yaml)
y [Postman](../postman_collection.json). Esta revisión es de código y
documentación; no certifica pruebas de carga ni distribución global.
