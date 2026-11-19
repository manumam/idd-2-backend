# Documentación del producto

## Alcance y requisitos

1. [Lineamientos de la entrega y demo](lineamientos-entrega-demo.md).
2. [Casos de uso del MVP](casos-de-uso-fixture.md).
3. [Modelo técnico objetivo](modelo-tecnico-demo.md).
4. [Estado de implementación y brechas](casos_de_uso.md).

Estos documentos definen el producto. El stack objetivo es MongoDB, Redis e
InfluxDB; una funcionalidad histórica no se considera parte del MVP por existir.
El frontend se incorpora por pedido posterior a los lineamientos de solo API.

## Consulta operativa

- [Rendimiento individual y consolidación del caso 9](rendimiento.md).
- [Observabilidad y errores](observabilidad_y_errores.md).
- [Monitoreo con Prometheus y Grafana Cloud](../observabilidad/README.md) y
  [prueba de carga](../carga/README.md).
- [Generación y carga de datos de InfluxDB](influx_datos.md).
- [Configuración, arranque y carga de datos](../README.md).
- [Contrato HTTP implementado](../openapi/openapi.yaml) y
  [colección Postman](../postman_collection.json).

Planes, procedimientos de evaluación y evidencia están fuera de `docs/`, en
[laboratorio](../laboratorio/README.md) y [hito-12](../hito-12/README.md).
