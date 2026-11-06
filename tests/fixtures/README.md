# Modelos de laboratorio

`cassandra.cql` y `iris/Fixture.*.cls` se copiaron de los Hitos 6 y 9 de
https://github.com/mateolewinzon/idd-2-tp para reproducir los contratos de acceso.
No alteran los modelos originales. Cargar solo en una instancia descartable o
usar los scripts del hito correspondiente para la instancia del grupo.

Cassandra: ejecutar el CQL con cqlsh, luego
`python scripts/preparar_lab.py --laboratorio-descartable --sources cassandra`.
IRIS: importar y compilar ambas clases juntas en el namespace USER con
`$system.OBJ.Import("/scripts", "compile",, "*.cls")`, luego cargar datos con
`python scripts/preparar_lab.py --laboratorio-descartable --sources iris`.
Este último comando informa IRIS_TEST_ID; crea objetos nuevos en cada repetición.

El usuario de IRIS debe tener una contraseña vigente (resolver el cambio inicial
en la instancia antes de conectar el driver), acceso al namespace y permisos de
lectura SQL. Para la carga sintética necesita además INSERT en las clases del fixture.
