# Instrucciones para agentes que trabajen en ROMKit

Lee este archivo antes de cambiar el proyecto. Consulta también README.md y las
pruebas del módulo afectado. Las instrucciones directas del usuario prevalecen.
Este archivo guía el trabajo de una IA; no añade soporte de formatos por sí solo.

## Objetivo y arquitectura

ROMKit Studio extrae recursos, detecta textos e imágenes y prepara la reinserción.
ROMKit Translator edita y revisa traducciones. Mantén ambas aplicaciones separadas
y comparte modelos, servicios y estilos a través de romkit_core. Los lectores de
formatos pertenecen al núcleo, nunca al código de ventanas.

La parte reutilizable es el flujo de trabajo, los modelos, los proyectos y la
interfaz. El formato de cada juego se resuelve mediante adaptadores. Una nueva
ROM no debe obligar a rehacer las dos aplicaciones ni a crear una herramienta aparte.

## Alcance de una adaptación y condición de finalización

Cuando el usuario pida adaptar un juego para traducirlo, contempla el recorrido
completo: detectar → extraer → exportar → traducir → importar → verificar la ROM
resultante. Implementar solo la lectura es un avance parcial, no una adaptación
terminada. Si el usuario limita el trabajo a lectura o imágenes, respeta ese alcance.

- Reutiliza **Buscar textos**, **Exportar marcados…** e **Importar traducción…**.
  Selecciona el adaptador por evidencias del formato y su versión. No añadas un
  botón de importar distinto para cada juego ni fuerces sus datos por el escritor FMG.
- Inspecciona primero `analysis/`, `project/rebuild.py`, `project/generator.py`,
  `project/reinsert_map.py`, `platforms/` y los modelos existentes. Reutiliza los
  lectores de contenedores, el runner, la validación y la publicación segura de ISO.
  Si el escritor actual está acoplado a un juego, separa la selección del adaptador
  de la reconstrucción específica sin alterar el comportamiento ya probado.
- Cada adaptador debe identificar qué puede leer y qué puede escribir. Conserva
  procedencia y versión suficientes para reconstruir el recurso desde el proyecto
  y el workspace original; los offsets editoriales solos pueden ser insuficientes.
  No anuncies reinserción compatible mientras falte el escritor o su validación.
- Al escribir, preserva IDs, índices, metadatos, controles, idiomas y recursos no
  modificados. Recalcula punteros, longitudes, alineaciones, compresión y tablas de
  archivo cuando el formato lo exija. Acepta crecimiento solo si toda la cadena
  recurso → contenedor → imagen puede reconstruirse y verificarse; en caso contrario,
  aplica un límite explícito y explica cuál. Nunca trunques traducciones para que quepan.
- Comprueba una reconstrucción sin cambios y otra con cambios de prueba conocidos.
  Reabre la salida con el lector y verifica textos, índices y recursos intactos.
  Incluye errores de espacio, controles inválidos, hash incorrecto y cancelación.
  La equivalencia sin cambios puede ser semántica si la compresión no es determinista;
  documenta las diferencias y exige identidad de los recursos que deban conservarse.
- El arranque y la visualización en emulador o hardware son una comprobación adicional:
  informa si no se han hecho. No confundas validación estructural con juego probado.
- Actualiza la matriz de compatibilidad del README por separado para extracción,
  edición, reinserción de textos e imágenes. Si hay un bloqueo real, registra evidencia,
  trabajo pendiente y límite concreto; no declares completado el recorrido.

La implementación por juego vive en `romkit_core/adapters/pokapoka/` y
`romkit_core/adapters/digimon/`. `adapters/registry.py` define el contrato Adapter,
la selección por archivos y los perfiles `all`, `base`, `pokapoka`, `digimon`.
Los imports antiguos son compatibilidad, no deben recibir lógica nueva.
El importador común valida identidad, proyectos y controles y delega el escritor.
La detección y extracción en Studio deben pasar por el registro; los lectores de
imágenes cargan solo los adaptadores habilitados. No añadas dependencias de juegos
nuevos al arranque de la base. La compilación con `scripts/desktop/build.py --profile`
fija el perfil y excluye físicamente los módulos de otros juegos. Translator es común.

Digimon dispone de escritura fija y un modo experimental en `digimon/repack.py`.
Redistribuye cadenas dentro de un bloque BTX contiguo y aislado, actualizando
sus punteros y conservando IDs y metadatos. Puede usar espacio liberado por
otras traducciones de la misma tabla. Los tutoriales independientes PSP (BTX a offset
4, prefijo de posición de metadatos y registros de metadatos de 12 bytes) también
pueden crecer dentro del relleno cero de su asignación original de sectores ARCV.
Se desplazan sus metadatos intactos, se actualiza el prefijo y el tamaño del miembro
en ARCVINFO. No se desplazan otros miembros ni cambia el tamaño de la ISO. Se rechaza
relleno ocupado, descriptores MARV/auxiliares desconocidos y falta de capacidad.
El crecimiento de BTX anidado en KCAP no está implementado. Nunca interpretes «forzar» como permiso para truncar,
eliminar controles, sobrescribir recursos vecinos o saltarse la identidad de la ROM.
El límite editorial individual se omite solo cuando el usuario activa el modo de
pruebas y el adaptador implementa la redistribución o ampliación correspondiente.
El crecimiento de volúmenes y la reubicación completa siguen sin estar implementados.
Verifica por IDs/registro tras mover punteros, no por offsets antiguos. Mantén los
IDs editoriales ligados a la imagen original para poder repetir la reconstrucción.

### Lección de capacidad: un modo de pruebas debe tratar todos los límites

No confundas tres capacidades distintas: bytes de una cadena, espacio de toda su
tabla y espacio asignado al recurso dentro del contenedor. «Permitir textos más
largos» no se resuelve simplemente omitiendo el primer límite ni repitiendo el mismo
error en el segundo. Investiga si existen huecos definidos por el formato, relleno
del sector, tamaños en índices y metadatos desplazables; implementa solo las rutas
que puedan reconstruirse y verificarse de extremo a extremo.

Caso de regresión real: `BattleEvent/battleTutorial.bin` de Digimon tiene una zona
de cadenas de 1134 bytes. Una traducción que necesita 1142 agotaba la redistribución,
aunque el miembro ARCV de 1400 bytes tenía relleno de sector disponible. El escritor
ahora puede crecer el tutorial y conservar sus metadatos mediante el caso específico
descrito arriba. No extrapoles este diseño a KCAP ni a otros formatos sin evidencia.

Todo error de capacidad debe incluir recurso/tabla, bytes requeridos y disponibles,
y distinguir capacidad agotada de un formato cuya ampliación no está implementada.
Indica qué modo de pruebas se está usando y sus límites reales. Añade pruebas de
desbordamiento de cadena y de bloque, crecimiento permitido, índice actualizado,
metadatos intactos, relleno no nulo y recurso vecino conservado. Reabre la ISO final
y verifica también los textos pendientes; el arranque en emulador sigue siendo una
comprobación adicional que debe declararse por separado.

`project/delta.py` genera BPS lineal por streaming y verifica que el parche reproduce
el destino exactamente. Conserva CRC de original, destino y parche; comprueba también
el SHA-256 del original abierto. La UI usa el runner con cancelación y publica solo
un archivo nuevo al terminar. No confundir BPS con Xdelta, no descargar ejecutables
externos como parte del flujo y no asumir que una base japonesa equivale al parche
 inglés usado para traducir. La aplicación de parches BPS externos no está implementada.

## Cómo incorporar un juego o una variante nueva

1. Reproduce el problema con la carpeta extraída indicada por el usuario. Lee su
   inventario y cabeceras; no presupongas formatos por la extensión ni por la plataforma.
2. Identifica si los recursos están sueltos, indexados en varios archivos, comprimidos,
   anidados o cifrados. Busca primero las tablas y los índices: una búsqueda de firmas
   no recupera de forma fiable texturas sin cabecera ni texto con punteros.
3. Documenta versión, endian, tamaños, alineación, base de los offsets, terminadores,
   formatos de píxel y límites. Comprueba varios recursos, dimensiones y paletas.
   Distingue hechos verificados de hipótesis; dos versiones del mismo formato pueden
   tener estructuras incompatibles. Consulta referencias primarias cuando sea necesario.
4. Implementa un adaptador pequeño, con detección estructural y límites explícitos.
   Reutiliza el recorrido de contenedores, la conversión de píxeles y la exportación
   existentes. No añadas un escaneo indiscriminado como sustituto de un índice conocido.
5. Añade pruebas sintéticas de las variantes admitidas y de datos truncados o maliciosos.
   Comprueba también recursos reales en modo lectura y revisa visualmente las imágenes.
   No declares compatible un formato solo porque se produjo un PNG o apareció texto.
6. Registra procedencia, offsets, formato y avisos en los manifiestos. Deduplica las
   imágenes conservando todas sus apariciones. Comunica lo que sigue sin ser compatible.
7. Actualiza README y los mensajes de la interfaz cuando cambie el soporte real.

## Reinserción de imágenes (1.1)

La exportación genera `imagenes.json` esquema 2, ligado al SHA-256 de la ROM y a
la procedencia BHD/ARCV de cada aparición. Las exportaciones antiguas deben repetirse.
`project/image_rebuild.py` reconstruye en staging y usa `Iso9660Reader.patch_copy`.
Los codificadores viven en `adapters/pokapoka/images.py` (GIM) y
`adapters/digimon/images.py` (GMIO), con píxeles compartidos en `image/pixels.py`.
Preserva dimensiones, formato, paletas, paso de fila, swizzle y orientación.
Rechaza colores no representables sin pérdida, GIM multinivel/frame, ZIP y variantes
sin escritor; no modifica paletas compartidas. Verifica las demás vistas GMIO y
rechaza cambios indirectos en vistas no seleccionadas. Un PNG deduplicado afecta a
todas sus apariciones del manifiesto. No inventes importación de cualquier PNG.

## Traducción editorial de Poka Poka

Comprueba el catálogo contra las tablas FMG antes de estimar el trabajo: el snapshot
de 70.561 entradas contenía 10.682 candidatos sin correspondencia estructural.
No borres los originales ni traduzcas esa basura. La preparación local separa esos
candidatos, reutiliza propuestas exactas y conserva las ediciones del usuario.
CP932 no representa tildes españolas ni ñ; tampoco basta con que una cadena quepa
si su tabla zlib supera el slot. Conserva las propuestas bloqueadas como Pendiente,
conserva controles e iconos y no suprimas tildes ni trunques texto sin una decisión
explícita del usuario. Nunca marques Revisado por haber generado una traducción.

El usuario autorizó continuar con español Unicode (ñ y tildes) y posponer su
sustitución al código del juego. `prepare_pokapoka.py --editorial` separa el estado
Traducido de la validación de reinserción; no relaja el escritor ISO. La generación
local opcional se hace con `scripts/translation/offline_draft.py`, con dependencias
y modelo fuera de la aplicación y sin peticiones de red con textos. Conservar
destinos anteriores, controles, procedencia y caché; no confundir borrador masivo
con revisión lingüística o traducción jugable terminada. Los informes de `translations/`
son locales. `docs/pokapoka-spanish-draft.md` registra cobertura y límites reales.

`adapters/pokapoka/fonts.py` lee solo CCM 0x10001 verificados. El informe de fuentes
es una auditoría de candidatos, nunca un permiso automático para sobrescribir glifos.
MainFont/TitleFont y sjisfont no tienen una asociación a atlas igualmente verificada:
no supongas que el tercer PNG sjisfont es la fuente activa de todos los textos.

## Casuísticas que deben comprobarse

- Contenedores: sueltos, ZIP, gzip/zlib, BND y conjuntos FAT/BHD/BND; índices externos,
  múltiples volúmenes, entradas vacías, duplicadas, desconocidas o fuera de límites.
- Imágenes: PNG y formatos comunes, GIM, texturas GMIO dentro de KCAP/ARCV; color
  directo e indexado, paletas locales, swizzle, ancho lógico distinto del paso de fila,
  orientación, transparencia y varias imágenes que comparten un bloque de datos.
- Texto: ASCII/UTF-8/UTF-16/CP932 según el recurso, japonés e inglés, cadenas cortas,
  tablas de punteros, tokens, controles y terminadores. Evita interpretar audio, gráficos,
  ejecutables o datos comprimidos como texto. Un filtro genérico no debe descartar
  cadenas válidas de una tabla estructural verificada.
- Traducción y reinserción: edición frente a revisión, límites en bytes del codec real,
  conservación de tokens y referencias, capacidad del bloque comprimido y hashes del
  original. Exportar textos no demuestra que se puedan reinsertar en cualquier juego.
- Interfaz: temas claros/oscuros, diálogos legibles, botones sin recortes, selección de
  filas frente a marcado para exportar, búsqueda, cancelación y trabajo fuera del hilo UI.

## Casos conocidos y límites

- Poka Poka: índices LDMU 0x210 FAT/BHD/BND, sectores de 1024 bytes, recursos FMG
  CP932 y texturas GIM. El lector indexado evita perder texto inglés o cadenas cortas.
  La reinserción existente está limitada a este adaptador y conserva el tamaño de la ISO.
- Digimon World Re:Digitize PSP: índice VCRA 0x101 ARCVINFO.BIN y volúmenes ARCVn.BIN,
  sectores de 2048 bytes; descriptores MARV, recursos KCAP y texturas GMIO versión 5.
  No confundir con variantes 3DS. Los BIN de instalación PGD están cifrados; preferir
  los recursos accesibles de ARCV. No prometer soporte universal de todos sus recursos.
  El texto inglés también está en ARCV: tablas BTX v1 UTF-16LE dentro de KCAP y
  tutoriales con BTX a offset 4. Sus punteros son relativos a cada registro ID/puntero;
  las cadenas pueden estar fuera de la sección de estructura, en los datos compartidos.
  Conservar textos cortos y controles como <n1001>. La reinserción BTX usa el mismo
  botón Importar traducción y admite proyectos previos con metadata de origen BTX.
  Aplica el límite original en bytes UTF-16LE, rechaza cadenas solapadas y verifica
  los recursos reconstruidos. La compatibilidad de glifos debe probarse en el juego.
- Los formatos desconocidos se informan como tales. Añade lectores cuando haya evidencia
  verificable; no inventes offsets, descifrados, formatos o resultados de pruebas.

## Seguridad, rendimiento y validación

Nunca alteres la ROM ni la extracción originales al analizar o exportar. Genera salidas
nuevas mediante staging y publicación al terminar. No sigas enlaces simbólicos ni uses
nombres internos de archivos para escribir fuera del destino. Limita memoria, dimensiones,
profundidad, expansión y número de entradas. Propaga la cancelación y conserva avisos.
No ejecutes herramientas descargadas sin inspección ni subas textos del juego a servicios
online salvo dentro del flujo autorizado de sugerencias de traducción.

Usa fixtures sintéticas versionadas. Deja muestras comerciales, ROMs y exportaciones de
comprobación fuera de los artefactos distribuidos. Ejecuta las pruebas relevantes y la
suite completa cuando cambies lectores compartidos; construye los paquetes si modificas
archivos distribuidos. En Windows usa .venv/Scripts/python.exe o uv según el entorno.
En el resultado explica cambios, pruebas y límites pendientes con cifras comprobadas.

## Empaquetado y publicación

Consulta `docs/git-layout.md` para distinguir código versionable, datos locales y
binarios de release. No publiques ROMs, extracciones, proyectos reales de traducción
ni capturas con datos comerciales entre los fixtures o ejemplos.

Excepción autorizada expresamente por el propietario el 24 de octubre de 2026:
publicar los proyectos editoriales actuales de Digimon y Poka Poka en `catalogs/`.
Conservar su estado, hashes y documentación de origen; no mezclarlos con fixtures
ni incluir ROMs, gráficos extraídos, rutas personales o `.romkit`. No extender esta
excepción a otros proyectos sin que el usuario lo solicite.

Studio/Translator y los adaptadores permanecen en `src/`: son el producto principal.
Los scripts de compilación y publicación pertenecen a `scripts/desktop/`.
Las utilidades independientes permanecen en `tools/`. No confundir scripts con productos.
Las releases del scraper/M3U tienen historial propio; no modificar sus assets ni
renumerarlas al publicar Studio/Translator. La versión Desktop sale de `__version__`
y se replica en ventanas, PE VERSIONINFO, manifiestos y ZIP. Antes de publicar,
comprobar todos los perfiles, el checksum de cada paquete y los catálogos autorizados.

Compila Windows con `scripts/desktop/build.py`: el script aísla PATH y las variables
de Qt/Python para que PyInstaller no recoja DLL de otras herramientas (por ejemplo
una ICU incompatible de Poppler). Mantén la limpieza y los cachés separados por perfil.
Una compilación no está validada porque su proceso siga vivo: puede estar mostrando
un error del cargador. Exige `--smoke-test <informe.json>`, salida cero y un informe
nuevo que confirme la ventana, `frozen: true` y el plugin `windows`. El script hace
esta comprobación para cada ejecutable. Nunca uses solo `poll() is None` como prueba.
