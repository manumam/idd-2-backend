# Seguimiento de los casos de uso del MVP

El alcance se define en [lineamientos](lineamientos-entrega-demo.md),
[casos de uso](casos-de-uso-fixture.md) y [modelo técnico](modelo-tecnico-demo.md).
La implementación se contrasta con esos requisitos; la existencia de una ruta
histórica no demuestra cumplimiento. Stack objetivo: MongoDB, Redis e InfluxDB.

Los lineamientos originales limitaban la entrega a la API. El trabajo posterior
solicitado incorpora el frontend del fixture, los planteles y la ficha de jugador.
Esta ampliación no cambia las decisiones de persistencia del MVP.

## Estado de implementación

| # | Caso del MVP | Estado | Evidencia y trabajo pendiente |
| --- | --- | --- | --- |
| 1 | Consultar el fixture | Implementado para el listado | `GET /fixture` lee MongoDB con Redis opcional. Frontend con orden por fecha, estado y resultado. No hay simulador que avance el torneo. |
| 2 | Consultar los partidos de una selección | Parcial | El frontend permite buscar por nombre; falta una consulta dedicada por selección. `/fixture` no acepta todavía los filtros propuestos por el modelo técnico. Abrir un plantel no resuelve este caso. |
| 3 | Consultar el estado de los grupos | Pendiente | No existen `/grupos` ni `/grupos/{id}/posiciones`, cálculo de clasificación ni vista de grupos. |
| 4 | Consultar los playoffs | Pendiente | Hay partidos eliminatorios en el fixture, pero faltan `/playoffs`, orígenes de plazas y propagación de ganadores. |
| 5 | Ver el detalle de un partido | Requiere migración | `/partidos/{codigo}` sigue en Neo4j; debe leer MongoDB y agregar estado, marcador y reloj. Falta la página del partido. |
| 6 | Consultar las alineaciones | Pendiente | No existe `/partidos/{id}/alineaciones`. Plantel de selección y alineación del partido son datos distintos. |
| 7 | Seguir los eventos del partido | Requiere migración | La ruta existe sobre Neo4j; debe leer eventos embebidos de MongoDB, acompañar marcador e invalidar caché. Falta ingesta y actualización en vivo. |
| 8 | Comparar estadísticas de equipos | Parcial | Hay lectura temporal de posesión, tiros y pases en Influx. Falta combinar eventos de MongoDB, consolidar estadísticas finales y mostrarlas en el frontend. |
| 9 | Rendimiento de un jugador en el partido | Pendiente | No existe la consulta de estadísticas por partido y jugador. La ficha personal no incluye rendimiento deportivo. |
| 10 | Mapa de calor de un jugador | Pendiente | Faltan endpoint, ocupación por celda/minuto, consulta histórica y visualización. |
| 11 (opcional) | Seguir la pelota en vivo | Pendiente | Falta endpoint de última posición, simulación y vista de tracking. |

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

El [inventario de API actual](api_actual.md) conserva las rutas y comportamientos
existentes, incluidas las operaciones pendientes de retirar. Esta revisión es de
código y documentación; no certifica pruebas de carga ni distribución global.
