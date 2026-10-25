# Importar imágenes modificadas

Disponible desde Studio 1.1.0. Translator sigue siendo el editor de textos.

1. Abre la ROM y su carpeta de trabajo en el Studio correspondiente al juego.
2. Extrae los recursos y pulsa **Buscar y extraer imágenes…**. Debes repetir la
   extracción si `imagenes.json` no tiene `schema_version: 2`.
3. Conserva el manifiesto y los nombres de los PNG. Edita los píxeles manteniendo
   dimensiones, transparencia y los colores representables en el formato original.
4. Pulsa **Importar imágenes…**, elige la carpeta que contiene `imagenes.json`
   y guarda una ISO con un nombre nuevo. Para combinar texto e imágenes, abre
   después la ISO modificada en una carpeta de trabajo nueva y vuelve a exportar
   sus textos/imágenes: la identidad y los hashes cambian al modificar una ROM.
5. Prueba la salida en un emulador o dispositivo. La app verifica la estructura y
   los recursos insertados, pero no acredita cómo los dibuja el juego.

## Compatibilidad y límites

- **Poka Poka:** GIM de una superficie/nivel compatible, sueltos o dentro de BND
  indexados compatibles y flujos zlib/gzip. Se conserva cada cabecera, paleta,
  paso de fila, swizzle y el tamaño descomprimido del miembro. La compresión puede
  usar relleno cero comprobado antes del siguiente miembro BHD.
- **Digimon PSP:** GMIO v5 que el lector pueda decodificar, incluso indexado con
  paletas TTPO admitidas; conserva orientación y dimensiones. Se comprueban otras
  vistas que compartan datos: un cambio indirecto no seleccionado se rechaza.
- **PNG comunes:** igual dimensión y tamaño que quepa en el espacio original.
- Los colores nuevos ajenos a una paleta y los colores no representables en 16 bits
  se rechazan. No se cuantiza silenciosamente ni se modifica una paleta compartida.
- No se escriben ZIP, variantes desconocidas, GIM con varios frames/niveles ni
  recursos que necesiten ampliar o reubicar volúmenes. No cambia el tamaño de ISO.
- Una imagen exportada una sola vez por deduplicación se aplica a todas sus
  apariciones registradas. Conserva los archivos sin modificar para mantenerlas.
- La app rechaza hashes incorrectos, enlaces, rutas fuera del proyecto, solapes y
  salidas existentes. La cancelación no publica una ISO parcial.

## Comprobación realizada el 25 de octubre de 2026

Con las extracciones locales indicadas por el usuario:

| Juego | PNG únicos extraídos | Apariciones duplicadas | Avisos del lector |
| --- | ---: | ---: | ---: |
| Poka Poka parcheado | 4.826 | 4.149 | 92 |
| Digimon Re:Digitize PSP parcheado | 3.177 | 4.685 | 200 (límite del informe) |

En cada ROM se hizo una reconstrucción sin cambios cuyo SHA-256 coincidió con
el original y otra cambiando un píxel de una imagen compatible. Se verificaron
las superficies reconstruidas y los bytes publicados en la ISO. Los hashes de
las ROM originales permanecieron intactos. La prueba Poka Poka incluyó GIM dentro
de MainFont.bnd; la de Digimon, GMIO dentro de un recurso ARCV.

Los avisos y límites de extracción siguen existiendo: estos resultados no prueban
compatibilidad con todas las imágenes. No se han arrancado las salidas en emulador
ni hardware. Las muestras comerciales y las ISO de comprobación se conservan fuera
de Git y de los assets de release.
