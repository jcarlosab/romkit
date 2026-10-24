# Scripts de escritorio

Esta carpeta no contiene una aplicación adicional. El código de Studio, Translator
y sus adaptadores está en `src/`. `tools/` contiene las utilidades independientes,
como Scraper y M3U Organizer.

- `build.py`: compila los perfiles y verifica que cada ejecutable abre su ventana.
- `studio.py` y `translator.py`: puntos de arranque usados por el empaquetador.
- `package_release.py`: crea ZIP completos y sus hashes SHA-256.
- `generate_icons.py`: genera los iconos originales de ROMKit.
- `snapshot_catalog.py`: copia los catálogos editoriales autorizados con sus hashes.

Desde la raíz del repositorio:

```powershell
uv run --group build python scripts/desktop/build.py --profile digimon --app studio --onefile --dist-dir dist/standalone
uv run --group build python scripts/desktop/build.py --app translator --onefile --dist-dir dist/standalone
```

Sin `--onefile` se genera una carpeta con EXE y `_internal`, que se distribuye completa
en ZIP. Con `--onefile`, el EXE incluye las dependencias y las extrae temporalmente
al arrancar; el primer inicio puede tardar más.
