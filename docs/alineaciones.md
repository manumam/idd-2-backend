# Alineaciones por encuentro · caso 6

`GET /partidos/{codigo}/alineaciones` devuelve `partido`, `local` y `visitante`.
Cada lado es `null` cuando todavía no se informó o su selección ya no coincide
con la plaza efectiva del partido. Un partido inexistente devuelve 404; un código
inválido, 400. Datos persistidos inválidos devuelven 500 `ALINEACIONES_INVALIDAS`.
Los fallos de MongoDB conservan el formato de error habitual (503/504 según causa).

Una convocatoria contiene:

- `equipo`: `{ "codigo": "ARG", "nombre": "Argentina" }`.
- `titulares`: exactamente once jugadores.
- `suplentes`: entre cero y quince jugadores.
- Cada jugador contiene `codigo` (referencia al catálogo, por ejemplo `ARG-10`),
  `nombre` completo, `dorsal` entero de 1 a 99 y `posicion` en ese encuentro.

No se permiten jugadores ni dorsales repetidos dentro de una selección, ni
referencias con el prefijo de otra selección. Se conserva la instantánea del
encuentro: dorsal, posición y nombre no se reconstruyen desde el plantel actual.
El orden de las listas es el de la carga. La formación táctica es opcional; no se infiere desde la posición del catálogo.

## Persistencia y caché

Las convocatorias se guardan en `partidos.alineaciones` en MongoDB, con los mismos
campos `local` y `visitante` de la respuesta. No hace falta InfluxDB ni Neo4j.
La lectura usa una proyección acotada y reutiliza el detalle para resolver plazas
de playoffs. No se muestran convocatorias de equipos que perdieron su plaza por
una corrección. Un lado pendiente no se completa automáticamente con el plantel.

Redis es opcional: Cache-Aside con clave `alineaciones:v2:{codigo}` y el TTL
configurado del fixture. Un hit no consulta MongoDB; ante miss se leen el detalle y
las convocatorias y se guarda la respuesta. `scripts/cargar_alineaciones.py` borra las
claves de los partidos cargados, y un tick o una carga del cuadro también las
invalida porque pueden cambiar las plazas. Hasta vencer el TTL, una copia en caché
puede responder aunque MongoDB no esté disponible.

## Carga explícita

El repositorio incluye un seed simulado de Argentina para pruebas (ver abajo); no incluye convocatorias oficiales por encuentro. Para otros equipos debe prepararse un
JSON con esta envoltura (el ejemplo representa ambos lados sin informar):

```json
{
  "partidos": [
    {
      "partido": "P-001",
      "alineaciones": { "local": null, "visitante": null }
    }
  ]
}
```

Para informar un lado, reemplazar su `null` por la convocatoria descrita arriba,
con once titulares y su lista de suplentes. Nombre y posición son los del partido.
La carga verifica que el partido y los jugadores existan y que pertenezcan a sus
selecciones. Rechaza el lote completo antes de escribir si fallan esas referencias.
Usa `.env` del backend y respeta variables exportadas; comprobar primero que apunte
al MongoDB de este proyecto.

```bash
# Solo estructura, sin bases ni escrituras; no comprueba referencias:
.venv/bin/python scripts/cargar_alineaciones.py /ruta/convocatorias.json --solo-validar
# Carga autorizada explícitamente, conserva convocatorias existentes:
.venv/bin/python scripts/cargar_alineaciones.py /ruta/convocatorias.json
# Corrección explícita; reemplaza ambos lados de cada partido indicado:
.venv/bin/python scripts/cargar_alineaciones.py /ruta/convocatorias.json --reemplazar
```

La carga aplica el validador actualizado de `partidos` antes de escribir. No crea
partidos, no carga el plantel ni modifica resultados, reloj o estado. Un documento
sin alineaciones o con valor `null` admite la carga inicial; uno con alineaciones,
aunque sus lados estén pendientes, se conserva salvo `--reemplazar`. La ejecución
es repetible; no es una transacción del lote y un fallo de escritura puede dejar
una carga parcial. Al terminar, aun ante un fallo, borra las claves de caché de los partidos del lote.

## Frontend y límite con el caso 9

`/partido.html?codigo=P-001#alineaciones` muestra ambos equipos, titulares y
suplentes. Incluye carga, ausencia de datos por lado, error con reintento y
actualización manual. Refresca cada quince segundos mientras la página está
visible y el partido no finalizó, conservando los últimos datos ante un error.

Seleccionar un jugador abre su ficha personal con `partido=P-001`. El regreso
conserva el encuentro y la sección de alineaciones; se valida el código de partido
antes de construir el enlace. La ficha incorpora las estadísticas individuales
del caso 9 y los acumulados del Mundial, con estados de cobertura explícitos.
Ver [rendimiento, tracking y consolidación](rendimiento.md); no inventa valores
deportivos ni sustituye tracking ausente por ceros.

Las pruebas locales cubren contratos HTTP, referencias, duplicados, plazas
obsoletas, correcciones, fallos de fuentes y navegación. No certifican la carga
ni el recorrido con motores reales.

## Seed simulado de Argentina

`data/fixture/alineaciones-argentina-demo.json` contiene convocatorias de prueba
para P-002 (Argentina–Jordania), P-051 (Argentina–Argelia) y P-083
(Argentina–Austria). Usa los 26 jugadores del snapshot del catálogo: once titulares
y quince suplentes, con nombres, dorsales y posiciones de esa fuente. La elección
del once es sintética, no una formación oficial. Los rivales quedan sin alineación.

```bash
.venv/bin/python scripts/cargar_alineaciones_argentina.py --solo-validar
# Solo después de autorizar la carga y comprobar MONGO_URI del proyecto:
.venv/bin/python scripts/cargar_alineaciones_argentina.py
```

Requiere el fixture y el plantel de Argentina ya cargados. No los crea por su cuenta.
Conserva cualquier alineación existente; no usa `--reemplazar` por defecto y no
modifica resultados, estado ni reloj. No se ejecuta al iniciar la API. El script
admite los mismos argumentos que el cargador genérico, incluido `--reemplazar`
para una corrección explícita de las convocatorias de esos tres encuentros.

## Propuesta simulada para P-001

`data/fixture/alineaciones-p001-demo.json` prepara Uruguay–Arabia Saudita con
once titulares, quince suplentes y formación 4–3–3 por selección. Usa los 52
jugadores existentes del catálogo; la elección del once y las posiciones en cancha
son ficticias. Mantiene la coherencia con los eventos existentes: URU-21 comienza
como titular y URU-19 como suplente; KSA-20 figura entre los titulares.

El archivo fue validado localmente y contrastado con los planteles leídos por API;
su preparación no lo carga en MongoDB. Ejecutar solo tras autorizar esta carga:

```bash
.venv/bin/python scripts/cargar_alineaciones.py data/fixture/alineaciones-p001-demo.json --solo-validar
# Carga explícita; conserva cualquier convocatoria existente y el resultado 2–0:
.venv/bin/python scripts/cargar_alineaciones.py data/fixture/alineaciones-p001-demo.json
```

No modifica eventos, reloj, estado ni tracking; no reinicia el partido finalizado.

## Formación táctica

Cada convocatoria admite `formacion`, opcional y `null` por defecto para conservar
la lectura de datos anteriores. Su estructura es:

```json
{
  "arquero": "ARG-23",
  "lineas": [
    ["ARG-26", "ARG-13", "ARG-19", "ARG-3"],
    ["ARG-7", "ARG-24", "ARG-20"],
    ["ARG-10", "ARG-9", "ARG-22"]
  ]
}
```

Las líneas van de defensa a ataque; cada línea se ordena de izquierda a derecha
al mirar hacia el arco rival. Deben ser entre dos y cinco líneas, con uno a cinco
jugadores por línea. El arquero y las líneas deben cubrir exactamente los once
titulares, una vez cada uno. No se permiten suplentes en el cuadro. El esquema
(por ejemplo, 4–3–3) se deriva de las longitudes de las líneas; no se almacena una
etiqueta redundante que pueda contradecirlas. La posición textual del jugador y
su ubicación táctica son campos independientes.

El frontend ubica estas referencias sobre una cancha en SVG/CSS, con el arquero
abajo y el ataque hacia arriba. Cada dorsal permite abrir la ficha del jugador.
Los botones de equipo alternan la formación y su convocatoria. Si falta la
formación, conserva la lista y muestra “Formación todavía no informada”. No es
tracking ni una representación en vivo de las coordenadas del jugador.

El seed de Argentina incluye un 4–3–3 simulado. La carga inicial sigue conservando
alineaciones existentes. Para enriquecer una convocatoria ya cargada, actualizar
únicamente `alineaciones.local.formacion` o `alineaciones.visitante.formacion`,
tras validar el modelo completo y aplicar el validador actualizado. No hace falta
reemplazar convocatorias ni resultados para añadir el cuadro.
