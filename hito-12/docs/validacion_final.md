# Validación final

Los controles consolidados están en `evidencia/validacion_final.json` y las métricas por corrida en `evidencia/comparacion.csv`.

| Control ejecutado | Resultado |
| --- | --- |
| Backend, tests unitarios | 123 aprobados, más 5 subtests (128 casos en JUnit). |
| Fixture, integración MongoDB/Redis reales | 6 aprobados. |
| Data Mart: correcciones, reintentos, fallas y penales | 6 aprobados. |
| HTTP 200 con contenido deliberadamente incorrecto | 43 respuestas rechazadas por JMeter. |
| Carga principal | 18 corridas, 14.468 respuestas medidas y 0 errores. |
| Integridad | 127 códigos únicos y fuente/respuesta iguales antes/después. |
| Recarga | Sin inserciones nuevas ni cambios relevantes. |
| Frescura y caché inválida | Ambos TTL verificados y reconstrucción correcta. |
| Fuente archivada | Huellas del tar y archivos comprobadas. |

La auditoría completa original se ejecutó con los registros locales y verificó cada muestra, igualdad de código/JMX y el registro de hipótesis anterior a la optimización. Esos detalles generados no se versionan. En un checkout nuevo, el verificador comprueba coherencia del CSV, fuente y validaciones publicadas e informa `published_summary`; no afirma volver a auditar requests que no están presentes.

Las salidas completas se obtienen repitiendo el procedimiento del README. Pytest informó una advertencia de deprecación de Starlette/httpx, sin fallos.
