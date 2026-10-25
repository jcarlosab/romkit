# Preparación y traducción local por memoria

`prepare_pokapoka.py` compara un catálogo editorial con las tablas FMG verificadas
de una extracción Poka Poka. Mantiene IDs, originales y ediciones existentes,
separa los candidatos no indexados y aplica un diccionario explícito de traducciones.
No usa servicios online ni intenta traducir datos binarios o palabras desconocidas.

```powershell
uv run python scripts/translation/prepare_pokapoka.py --source-project catalogs/pokapoka --workspace "C:/mi-carpeta-de-trabajo" --output translations/pokapoka-es --memory translations/pokapoka-es-memory.json
```

La memoria es un JSON local: `{"translations":{"Back":"Volver","Name":"Nombre"}}`.
Se reutiliza cada propuesta exacta en todas sus apariciones; no se hacen sustituciones
de palabras dentro de diálogos. Las guías de botones usan etiquetas completas y
conservan los iconos. Para añadir traducciones a un proyecto existente usa `--resume`;
no se sobrescriben sus destinos ni sus revisiones. Las propuestas no válidas conservan
el texto español pero permanecen pendientes, con su error en las notas.

La validación individual comprueba codec, bytes y controles. **No demuestra que la
tabla comprimida quepa ni que el juego muestre todos los glifos.** Antes de distribuir,
usa Importar traducción para reconstruir una ISO nueva y comprobar los límites del
contenedor. Si una tabla falla, conserva sus propuestas en estado Pendiente hasta
resolver su capacidad. Prueba la salida en emulador o hardware por separado.

Los datos editoriales se guardan en `translations/`, fuera de Git. No cambies el
estado a Revisado automáticamente ni presentes un lote como traducción completa.

## Español editorial con ñ y tildes

Con `prepare_pokapoka.py --resume --editorial`, una propuesta válida en contenido
puede quedar como Traducida aunque aún no cumpla el codec CP932 o el espacio.
Sus errores de reinserción siguen en las notas y en la validación. Los controles
alterados sí impiden aplicarla. No se relajan las comprobaciones del escritor ISO.
Este modo separa avance editorial de compatibilidad con la ROM; no equivale a revisión.

`audit_pokapoka_fonts.py` lee los CCM 0x10001 y localiza códigos comunes que no
aparecen en los FMG/CSV comprobados. Sus candidatos están **inactivos**: aún hay que
verificar los atlas activos, sus métricas, textos generados en ejecución y el mapa
de escritura. No basta con que el nombre del CCM se parezca al del PNG.

## Borrador automático local opcional

`offline_draft.py` trabaja sin red, con CTranslate2 4.8.3, SentencePiece 0.2.2,
NumPy 2.3.5 y PyYAML 6.0.3 instalados aparte. El modelo no forma parte de los EXE.
El script no descarga paquetes ni ejecuta scripts del modelo. Suministra un modelo
Marian ya inspeccionado y convertido a int8, y los tokenizadores originales.

```powershell
uv run python scripts/translation/offline_draft.py --project translations/pokapoka-es --runtime build/local-translation/runtime --model build/local-translation/en-es-int8 --source-spm build/local-translation/en-es-source/source.spm --target-spm build/local-translation/en-es-source/target.spm --memory translations/pokapoka-es-memory.json
```

La evaluación local empleó los pesos oficiales de Helsinki-NLP, OPUS-MT eng-spa
`opus-2021-02-19.zip`, SHA-256
`f76bd91280deb275a36ccee61c1069e7808badd3e19ac73f0def08f18aaf896d`.
Su archivo LICENSE indica **CC BY 4.0**, diferente de la licencia del código de
ROMKit. Conserva atribución a Helsinki-NLP/OPUS-MT y ese LICENSE al redistribuir
los pesos. Fuente: https://object.pouta.csc.fi/Tatoeba-MT-models/eng-spa/opus-2021-02-19.zip

El script mantiene destinos y revisiones existentes, consulta primero la memoria
editorial y usa caché SQLite por modelo. Aparta controles, variables, iconos y
términos protegidos; comprueba su conservación después. Nunca marca Revisado.
Las etiquetas técnicas, símbolos, nombres de autores/personajes y la lista de
palabras prohibidas se conservan aparte, con motivo explícito en el informe.
El texto japonés fuera de controles no se envía al modelo inglés.

El resultado es un borrador pendiente de revisión lingüística y de inserción.
No se deben convertir sugerencias idénticas al original ni frases automáticas en
una declaración de «juego traducido y probado». Consulta `offline-draft-report.json`
para conocer omisiones, controles rechazados, identidad del modelo y estados.
