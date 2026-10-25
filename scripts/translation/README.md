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
