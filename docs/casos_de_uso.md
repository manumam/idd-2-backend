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
| 3 | Consultar el estado de los grupos | Implementado en backend y frontend; verificación real pendiente | Grupos, participantes y reglas explícitas en MongoDB; cálculo desde resultados finalizados, sin tandas. Orden por puntos, DG, GF y desempate del dataset. Cache-Aside opcional en Redis, invalidado por cierres, correcciones y cargas. | Cargar grupos de forma explícita con `scripts/cargar_grupos.py` y verificar con MongoDB del proyecto. La vista permite elegir grupo, consultar PJ/PG/PE/PP/GF/GC/DG/puntos y abrir sus partidos. La página central de detalle corresponde al caso 5. |
| 4 | Consultar los playoffs | Implementado en backend y frontend; verificación con motores reales pendiente | Cruces y orígenes en MongoDB; resolución derivada de grupos y resultados, Cache-Aside en Redis invalidado por resultados y cargas. Dos primeros de cada grupo, sin mejores terceros. | Ejecutar la carga explícita del cuadro y verificar con MongoDB del proyecto. La vista permite abrir cada cruce y navegar su camino. El detalle completo con sede y reloj corresponde al caso 5. Resultados con participantes obsoletos requieren revisión y no propagan ganador. |
| 5 | Ver el detalle de un partido | Implementado en backend y frontend; fixture → detalle próximo verificado con MongoDB local | MongoDB con Cache-Aside opcional en Redis, invalidado por cada escritura del partido o del cuadro. Sede, fecha/hora, estado, resultado con tanda separada y reloj persistido opcional. Plazas consistentes con playoffs. | Completar verificación real de vivo/finalizado y entradas desde grupos/playoffs (no cargados en la base local revisada). Los documentos sin reloj muestran minuto no disponible; el simulador/ingesta que lo avance corresponde al trabajo pendiente de vivo. Aplicar el nuevo validador explícitamente antes de escribir reloj en bases existentes. |
| 6 | Consultar las alineaciones | Consulta implementada en backend y frontend; verificación real pendiente | Convocatorias embebidas en MongoDB con referencias estables y Cache-Aside opcional en Redis. Once titulares y hasta quince suplentes por equipo; formación opcional validada y cancha navegable por selección. | Cargar convocatorias explícitas por encuentro con `scripts/cargar_alineaciones.py` y verificar con motores reales. La selección de jugador conserva el partido y abre su ficha con rendimiento por encuentro y acumulados del caso 9; su cierre físico real sigue pendiente. Ver [alineaciones](alineaciones.md). |
| 7 | Seguir los eventos del partido | Implementado en backend y frontend; avance y cierre de P-001 verificados con MongoDB del proyecto | Eventos embebidos en MongoDB y Cache-Aside opcional en Redis. Cronología de goles, autogoles, tarjetas y cambios; marcador/reloj de la misma instantánea. Simulador explícito por consola con protección básica por ID. | Para nuevas demos, generar y ejecutar explícitamente un plan sobre otro partido próximo. Sin migración automática de los eventos históricos de Neo4j ni sistema de correcciones. El caso 8 agrega comparación y simulación temporal; el seed final fue verificado con motores reales. Ver [eventos](eventos.md). |
| 8 | Comparar estadísticas de equipos | Backend y frontend implementados; seed final P-001 verificado con MongoDB e Influx propios | Aggregator MongoDB + Influx en vivo, caché Redis opcional de 5 s y resumen final de equipos en MongoDB con huella de entradas. Consolidación explícita y reemplazable; valores ausentes null y estado pendiente/provisional/final. Serie temporal previa compatible. | Seed final autorizado P-001: 2–0, cinco eventos, 2.162 muestras y resumen completo verificados mediante el proxy. Lectura final comprobada con Influx detenido y Redis inaccesible en lector aislado; diseño de escritorio y móvil revisado. Reproducción en vivo cubierta con adaptadores en memoria; su ejecución real sigue pendiente. Sin tracking. Ver [estadísticas](estadisticas.md). |
| 9 | Rendimiento de un jugador en el partido | Implementado en backend y frontend; lectura deportiva real URU-21/P-001 verificada por proxy y página, cierre físico real pendiente | Eventos MongoDB y tracking confirmado a 1 Hz en Influx para el vivo; generaciones de resúmenes individuales en MongoDB, publicadas por CAS. Acumulados sin doble conteo y Redis opcional de 5 s con huellas de entradas. | Registrar explícitamente cobertura de tracking existente y consolidar un encuentro autorizado. Verificar físicas mediante el proxy, repetir cierre y consultar finales sin Influx. La ficha desde alineaciones muestra goles, asistencias, tarjetas, distancia, velocidad máxima y acumulados. Ver [rendimiento](rendimiento.md). |
| 10 | Mapa de calor de un jugador | Implementado en backend y frontend; histórico verificado contra InfluxDB real con P-002 (crudo y ocupación materializada coinciden celda por celda) | Grilla de 5 × 5 m; las celdas las cuenta InfluxDB (`FLOOR`, `LEAST`, `GROUP BY`) sobre `tracking_jugador`, con rango por minuto anclado a `inicio_tracking` o a `fecha_hora`. Los finalizados se leen de `ocupacion_jugador_minuto` (script explícito; crudo como respaldo solo si la tabla aún no existe). Cache-Aside en Redis: 5 s en vivo, 1 h histórico. Ficha `/jugador.html?codigo=…&partido=…` con intervalos y actualización cada 5 s en vivo. | Simulador que escriba tracking en vivo y registre `inicio_tracking` (plan del modo demo). Materializar la ocupación de cada partido antes de que venza el crudo (7 días). Filtro por equipo fuera de alcance. No usar promedios de coordenadas como mapa de calor. |
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

- El caso 8 agrega simulación temporal de equipos y consolidación final por consola; seed final y lectura sin Influx verificados con motores reales. El caso 9 incorpora lecturas físicas desde tracking y cierre individual explícito, con tests locales; falta comprobarlo con motores reales y cobertura autorizada. El mapa de calor del caso 10 está implementado; sigue pendiente el simulador de tracking en vivo y la materialización por encuentro. Ninguna carga se ejecuta al arrancar.
- Completar cachés por funcionalidad. El monitoreo (Prometheus, exporters, dashboard en Grafana Cloud y prueba de carga) está integrado; faltan las métricas por región y de antigüedad del dato servido.
- Validar los contratos propuestos antes de implementarlos. OpenAPI y Postman
  describen la API actual y solo deben cambiar junto con sus rutas y schemas.

El contrato HTTP implementado se consulta en [OpenAPI](../openapi/openapi.yaml)
y [Postman](../postman_collection.json). Esta revisión es de código y
documentación; no certifica pruebas de carga ni distribución global.

### Tracking y estadísticas del caso 8

El simulador `simular_estadisticas.py` escribe posesión, tiros acumulados y cantidades de pases por intervalo en `estadisticas_partido`; los eventos deportivos se guardan en MongoDB. No genera posiciones ni trayectorias de jugadores o pelota. Para un mapa de calor con contenido se necesita una carga de tracking independiente y, para conservarlo, materializar la ocupación antes de que venza el crudo. Sin muestras, tabla o base de tracking creada, el mapa devuelve 200 con `celdas: []`; no inventa posiciones. Los fallos de autenticación, permisos, conexión y consultas inválidas siguen devolviendo errores.
