# Borrador español y fuentes de Poka Poka

El trabajo editorial conserva español Unicode con ñ, tildes y signos de apertura.
La adaptación al codec del juego se realiza después: no se eliminan diacríticos
para que una propuesta pase la validación. Traducido, Revisado y Reinsertable
son condiciones distintas. El escritor mantiene los límites reales de la ROM.

## Preparación del 25 de octubre de 2026

Se comparó el catálogo de 70.561 entradas con las tablas FMG de la ROM utilizada:
59.879 entradas tienen correspondencia estructural y 10.682 candidatos antiguos
quedaron separados, conservando tanto el catálogo original como los descartados.

El proyecto local `translations/pokapoka-es` contiene un borrador para 58.084
entradas. Las 1.795 restantes se conservan como símbolos/controles, separadores,
etiquetas técnicas, filtros, nombres propios o créditos. El informe identifica
cada caso. Algunos nombres de equipos y términos del parche base también pueden
permanecer iguales en propuestas automáticas: requieren un glosario específico.
Esto describe cobertura de borrador, no una revisión lingüística completa.

Se mantuvieron 1.934 entradas editoriales y se generaron 56.150 propuestas con el
modelo local OPUS-MT, aplicando después correcciones puntuales de terminología.
Los fragmentos repetidos se reutilizaron mediante caché. No se enviaron textos a
servicios online, no se cambiaron originales/IDs ni se marcaron entradas Revisadas.
El modelo original es OPUS-MT eng-spa `opus-2021-02-19`, con LICENSE CC BY 4.0;
su procedencia y uso opcional están en [scripts/translation](../scripts/translation/README.md).

La comprobación abrió el proyecto con el servicio de Translator y comparó los
controles y los destinos editoriales anteriores. Las ISO comerciales, los modelos
y este borrador local no se incluyen en releases ni fixtures.

## Fuentes: evidencias y trabajo pendiente

Se localizaron `AllCCM_Master.bnd` y `AllCCM.bnd`, con layouts CCM 0x10001
little-endian: MainFont tiene 4.784 códigos, TitleFont 502 y sjisfont 3.533.
La lectura estructural se contrastó con el formato descrito por
[SoulsFormats](https://github.com/JKAnderson/SoulsFormats/blob/master/SoulsFormats/Formats/CCM.cs)
y con los archivos reales; no se aplica a variantes CCM diferentes.

MainFont y TitleFont tienen referencias por nombre en el ELF `MHi2_Master.prx`.
Sus coordenadas CCM reprodujeron visualmente la letra A en los atlas asociados.
La asociación supuesta entre sjisfont y `00sjis12_menu_f.bnd` no superó esa
comprobación y sigue sin verificarse. Un PNG que contiene letras no demuestra
que sea el atlas activo del texto que se quiere traducir.

La auditoría encontró 50 códigos candidatos comunes ausentes del corpus FMG/CSV
examinado. **No están activados ni constituyen un mapa de sustitución validado.**
Falta comprobar métricas, atlas realmente utilizados, entradas del jugador y
texto generado en ejecución. Después habrá que reconstruir los atlas/layouts
pertinentes y aplicar un mapa Unicode→código de juego exclusivo de esta variante.

La ROM original usa CP932, que no representa directamente las letras españolas.
Incluso con la fuente resuelta, deben ampliarse o redistribuirse las tablas FMG
y reconstruir sus contenedores cuando no baste el espacio actual. La ISO de
209 textos del lote inicial sigue siendo un checkpoint independiente; no contiene
este borrador completo. No se ha generado una ISO con el español completo ni se
han realizado pruebas en emulador o hardware.
