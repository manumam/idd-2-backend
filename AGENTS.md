# Instrucciones para agentes

## Mantener sincronizado el contrato de la API

Cuando un cambio agregue, quite o modifique una ruta HTTP, sus parámetros, schemas,
respuestas, códigos de estado o comportamiento observable, actualizá en el mismo cambio:

- `openapi/openapi.yaml`, regenerándolo con `python scripts/exportar_openapi.py` cuando corresponda.
- `postman_collection.json`, para que incluya las operaciones y parámetros vigentes, con ejemplos válidos.
- La documentación afectada, como `docs/casos_de_uso.md`, `docs/contratos_y_errores.md` y `README.md`.

Tomá las rutas y schemas de `app/routes/` y `app/schemas/` como fuente de implementación.
No dejes cambios de API documentados solo en el código ni actualices un contrato sin
actualizar los demás artefactos afectados. Conservá las variables de entorno de Postman
(por ejemplo `baseUrl`) para que la colección funcione en local.

Antes de terminar, verificá que OpenAPI y Postman incluyan el mismo conjunto de
operaciones HTTP y que los parámetros de cada operación coincidan. Si el cambio no afecta
el contrato público, no hace falta modificar estos artefactos.
