# Instrucciones para agentes

## Arranque normal de la aplicación

- Ejecutar desde este repositorio. Usar `.venv` y la configuración local `.env`;
  no reemplazarla ni mostrar credenciales. Las variables exportadas tienen prioridad.
- Iniciar la API con `bash scripts/iniciar_api.sh`. Respeta `API_HOST` y `API_PORT`
  de `.env`; el puerto habitual del frontend es 8000. Verificar que coincida con
  `API_PROXY_TARGET` del frontend.
- Para fixture y planteles se necesita MongoDB con los datos del proyecto; Redis
  es opcional para el fixture. Los demás casos usan las dependencias de sus rutas.
- Antes de iniciar bases, comprobar la configuración y los contenedores existentes.
  El Compose normal es `docker-compose.yaml`. Para estas vistas, iniciar solo
  `mongo redis`: no requieren el repositorio vecino. MongoDB usa `MONGO_PORT`
  (27018 por defecto), que debe coincidir con `MONGO_URI` en `.env`.
  `docker-compose.imports.yaml` agrega montajes opcionales para importar MongoDB;
  otros motores todavía usan montajes de `../idd-2-tp`. Comprobar puertos libres.
- Si falta el repositorio de datos, una conexión o hay otro proyecto ocupando el
  puerto, informar el bloqueo. No conectar la app a bases de otro proyecto ni
  cambiar al laboratorio como alternativa. No detener contenedores ajenos.
- Cuando el usuario pida levantar o iniciar el proyecto, preguntarle si quiere
  ejecutar el seed antes de cargar datos. Explicar qué carga y si conserva o
  reemplaza resultados existentes. Esperar su respuesta para ejecutar el seed;
  el pedido de arranque por sí solo no autoriza esa carga.
- Sin autorización explícita, no cargar seeds, reiniciar escenarios ni reemplazar datos como parte del arranque.
  Usar `GET /live` para comprobar el proceso y las rutas de la funcionalidad para
  verificar los datos; `/ready` requiere las seis fuentes y puede estar degradado.

## Ofrecer la simulación de partidos

- Al levantar la app, preparar una demo o revisar una cronología vacía, ofrecer
  ejecutar el simulador deportivo del caso 7. Es una opción separada del seed;
  consultar [docs/eventos.md](docs/eventos.md) para los comandos y límites.
- Antes de ofrecer un partido concreto, consultar el fixture o su detalle y elegir
  uno próximo con ambas selecciones definidas. Para un partido finalizado, ofrecer
  otro encuentro próximo; no reiniciar ni borrar resultados para volver a simularlo.
- Explicar que usa equipos y jugadores existentes, pero los eventos son un guion
  ficticio y determinista: nueve ticks, cinco eventos, resultado local 2–0; con
  `--intervalo 6` dura unos 48 segundos. Excluye arqueros, prioriza delanteros y
  respeta titulares/suplentes cuando hay alineaciones. No produce tracking de Influx.
- Se puede generar y validar un plan local sin cambiar datos deportivos. Para
  ejecutarlo, obtener autorización explícita para el partido y explicar que
  modificará eventos, reloj, marcador y estado hasta dejarlo finalizado. El pedido
  de arranque por sí solo no autoriza la simulación; si ya fue autorizada para ese
  partido en la conversación, continuar sin pedir una segunda confirmación.
- Después de ejecutarlo, verificar cronología, detalle y fixture a través del
  proxy del frontend y comunicar el resultado. No presentar una prueba en memoria
  como ejecución con MongoDB real.

## Tests y laboratorio separados del arranque

- Tests habituales: `bash scripts/ejecutar_pruebas.sh` o
  `.venv/bin/python -m pytest -q`. Solo recolectan `tests/unit`; no levantan Docker.
- Tests reales: ejecutar `tests/integration` explícitamente, con las variables
  opt-in y bases de prueba dedicadas indicadas en `tests/README.md`. No usar la
  base de desarrollo para pruebas que escriben o eliminan datos.
- No ejecutar `docker-compose.hito11.yaml`, `config/hito11.env.example`,
  `scripts/preparar_lab.py`, `scripts/cerrar_hito11.py`, ni el entorno de Hito 12
  para abrir la app o ejecutar tests habituales. Son entornos de evaluación separados.
- No iniciar el laboratorio, cargas masivas ni pruebas de carga salvo pedido
  explícito del usuario de ejecutar esa evaluación. Conservar sus volúmenes.


## Mantener sincronizado el contrato de la API

Cuando un cambio agregue, quite o modifique una ruta HTTP, sus parámetros, schemas,
respuestas, códigos de estado o comportamiento observable, actualizá en el mismo cambio:

- `openapi/openapi.yaml`, regenerándolo con `python scripts/exportar_openapi.py` cuando corresponda.
- `postman_collection.json`, para que incluya las operaciones y parámetros vigentes, con ejemplos válidos.
- La documentación afectada, como `docs/casos_de_uso.md` y `README.md`.

Tomá las rutas y schemas de `app/routes/` y `app/schemas/` como fuente de implementación.
No dejes cambios de API documentados solo en el código ni actualices un contrato sin
actualizar los demás artefactos afectados. Conservá las variables de entorno de Postman
(por ejemplo `baseUrl`) para que la colección funcione en local.

Antes de terminar, verificá que OpenAPI y Postman incluyan el mismo conjunto de
operaciones HTTP y que los parámetros de cada operación coincidan. Si el cambio no afecta
el contrato público, no hace falta modificar estos artefactos.
