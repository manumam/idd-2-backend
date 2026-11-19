# Seguimiento de los casos de uso del MVP

El alcance se define en [lineamientos](lineamientos-entrega-demo.md),
[casos de uso](casos-de-uso-fixture.md) y [modelo técnico](modelo-tecnico-demo.md).
La implementación se contrasta con esos requisitos; la existencia de una ruta
histórica no demuestra cumplimiento. Stack objetivo: MongoDB, Redis e InfluxDB.

Los lineamientos originales limitaban la entrega a la API. El trabajo posterior
solicitado incorpora el frontend del fixture, los grupos, los planteles, la ficha de jugador y la cronología de los partidos.
Esta ampliación no cambia las decisiones de persistencia del MVP.

## Estado de implementación

El estado funcional y la alineación técnica se evalúan por separado. Usar una
base prevista por el modelo no completa por sí solo un caso de uso. «Pendiente»
significa que el modelo todavía no está implementado para ese caso, no que se
haya validado su cumplimiento. Los casos 3 y 4 están implementados en ambos repositorios; su comprobación con motores
reales requiere la configuración local y la carga explícita de grupos y cruces. Los demás
casos conservan las brechas detalladas abajo.

| # | Caso del MVP | Estado funcional | Alineación con el modelo técnico | Trabajo pendiente para completarlo |
| --- | --- | --- | --- | --- |
| 1 | Consultar el fixture | Listado implementado; demo en vivo incompleta | Parcial: `GET /fixture` usa MongoDB y Cache-Aside en Redis, como se propone. La API no admite todavía `equipo_id`, `fecha` ni `fase`; los filtros actuales se aplican en el frontend. | Completar los filtros del contrato propuesto y sus claves de caché. Vincular ingesta, cierre y correcciones con la invalidación. El frontend muestra orden, horario, fase, estado y resultado, pero falta el simulador que avance el torneo. |
| 2 | Consultar los partidos de una selección | Parcial: búsqueda de texto, sin recorrido específico por selección | Parcial: reutiliza el fixture de MongoDB/Redis, pero no existe el filtro de API por identificador de selección propuesto en `/fixture?equipo_id=…`. | Seleccionar un equipo desde el fixture debe abrir sus partidos próximos, en vivo y finalizados, en lugar de su plantel. Agregar filtro exacto por código y caché que lo incluya. La búsqueda por nombre no equivale al flujo completo. |
| 3 | Consultar el estado de los grupos | Implementado en backend y frontend; verificación real pendiente | Grupos, participantes y reglas explícitas en MongoDB; cálculo desde resultados finalizados, sin tandas. Orden por puntos, DG, GF y desempate del dataset. Caché Redis opcional versionada por todas las entradas. | Cargar grupos de forma explícita con `scripts/cargar_grupos.py` y verificar con MongoDB del proyecto. La vista permite elegir grupo, consultar PJ/PG/PE/PP/GF/GC/DG/puntos y abrir sus partidos. La página central de detalle corresponde al caso 5. |
| 4 | Consultar los playoffs | Implementado en backend y frontend; verificación con motores reales pendiente | Cruces y orígenes en MongoDB; resolución derivada de grupos y resultados, caché Redis versionada por todas las entradas. Dos primeros de cada grupo, sin mejores terceros. | Ejecutar la carga explícita del cuadro y verificar con MongoDB del proyecto. La vista permite abrir cada cruce y navegar su camino. El detalle completo con sede y reloj corresponde al caso 5. Resultados con participantes obsoletos requieren revisión y no propagan ganador. |
| 5 | Ver el detalle de un partido | Implementado en backend y frontend; fixture → detalle próximo verificado con MongoDB local | MongoDB con caché Redis opcional versionada por las entradas efectivas. Sede, fecha/hora, estado, resultado con tanda separada y reloj persistido opcional. Plazas consistentes con playoffs. | Completar verificación real de vivo/finalizado y entradas desde grupos/playoffs (no cargados en la base local revisada). Los documentos sin reloj muestran minuto no disponible; el simulador/ingesta que lo avance corresponde al trabajo pendiente de vivo. Aplicar el nuevo validador explícitamente antes de escribir reloj en bases existentes. |
| 6 | Consultar las alineaciones | Consulta implementada en backend y frontend; verificación real pendiente | Convocatorias embebidas en MongoDB con referencias estables y caché Redis opcional versionada. Once titulares y hasta quince suplentes por equipo; formación opcional validada y cancha navegable por selección. | Cargar convocatorias explícitas por encuentro con `scripts/cargar_alineaciones.py` y verificar con motores reales. La selección de jugador conserva el partido y abre su ficha personal; el rendimiento por encuentro sigue pendiente en el caso 9. Ver [alineaciones](alineaciones.md). |
| 7 | Seguir los eventos del partido | Implementado en backend y frontend; avance y cierre de P-001 verificados con MongoDB del proyecto | Eventos embebidos en MongoDB y Redis opcional versionado. Cronología de goles, autogoles, tarjetas y cambios; marcador/reloj de la misma instantánea. Simulador explícito por consola con protección básica por ID. | Para nuevas demos, generar y ejecutar explícitamente un plan sobre otro partido próximo. Sin migración automática de los eventos históricos de Neo4j ni sistema de correcciones. La comparación de estadísticas del caso 8 sigue pendiente. Ver [eventos](eventos.md). |
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
- Completar simulación temporal de Influx y consolidación estadística. El caso 7 ya incluye simulador deportivo e ingesta validada por consola; no ejecuta cargas al arrancar.
- Completar cachés por funcionalidad y observabilidad Prometheus/Grafana.
- Validar los contratos propuestos antes de implementarlos. OpenAPI y Postman
  describen la API actual y solo deben cambiar junto con sus rutas y schemas.

El contrato HTTP implementado se consulta en [OpenAPI](../openapi/openapi.yaml)
y [Postman](../postman_collection.json). Esta revisión es de código y
documentación; no certifica pruebas de carga ni distribución global.
