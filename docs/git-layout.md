# Qué subir a Git

Un único repositorio conserva la base y los adaptadores en carpetas separadas.
Las compilaciones por perfil generan ejecutables exclusivos sin copiar ni mantener
varias versiones de Studio o Translator.

```text
romkit/
  .gitignore
  .python-version
  AGENTS.md
  README.md
  pyproject.toml
  uv.lock
  src/
    romkit_core/
      adapters/
        registry.py
        digimon/          # ARCV, BTX, GMIO, escritura y modo experimental
        pokapoka/         # FAT/BHD/BND, FMG y escritura
      assets/             # iconos originales SVG/PNG/ICO
      analysis/           # análisis compartido y compatibilidad de imports
      image/
      models/
      platforms/
      project/            # proyectos, validación común de reinserción y BPS
      transforms/
      validation/
      workspace/
      app.py
      icons.py
      ui_styles.py
    romkit_studio/        # interfaz y flujo de trabajo común
    romkit_translator/    # editor común, sin adaptadores de juegos
  tests/
    fixtures/             # datos sintéticos y constructores de archivos
    unit/
    integration/
  catalogs/               # proyectos editoriales actuales autorizados
    digimon/
    pokapoka/
  scripts/
    desktop/              # compilación, empaquetado, iconos y lanzadores
  tools/
    scraper/              # herramienta adicional ya presente en el repositorio
    m3u-organizer/        # herramienta adicional ya presente en el repositorio
  docs/
    git-layout.md
    render_preview.py
    studio.png            # capturas con datos de demostración
    studio-info.png
    translator.png
    icons.png
```

El árbol resume las carpetas principales; incluye los demás módulos de código y
documentación que pertenezcan al proyecto. Los `.spec` escritos para las herramientas
de `tools/` son código de compilación; los `.spec` generados dentro de `build/` son
salidas locales y no se suben.

## Qué queda fuera

Excepción solicitada expresamente el 24 de octubre de 2026: los snapshots de textos
de `catalogs/digimon` y `catalogs/pokapoka` sí se versionan. Las reglas de ignorado
tienen una excepción para esos catálogos. Esta autorización no incluye ROMs,
imágenes extraídas ni la metadata privada `.romkit`. Los demás proyectos locales
siguen excluidos.

- ROMs e imágenes ISO, originales o modificadas, y sus archivos extraídos.
- Carpetas `.romkit/`, mapas locales de reinserción y metadata de imágenes del usuario.
- Proyectos de traducción locales: `project.toml`, `text/*.jsonl`, exportaciones,
  traducciones y gráficos recuperados del juego. Los ejemplos que se versionen
  deben ser sintéticos y estar identificados como tales.
- `.venv/`, cachés, logs, configuración personal, `.env` y credenciales.
- `build/`, `dist/`, ejecutables, DLL y parches de prueba.

Si necesitas trabajar dentro del repositorio, guarda todo el material de juegos
en `local/`, que está ignorado. También puedes usar carpetas externas. El `.gitignore`
no elimina archivos que ya estuvieran versionados: revisa el contenido preparado
para el commit antes de publicar, incluidas imágenes y archivos grandes.

## Ejecutables: archivos de release

Los binarios se publican como ZIP adjuntos a una release, separados del código:

```text
ROMKit-Studio-Base.zip
  ROMKit Studio - Base/
    ROMKit Studio - Base.exe
    _internal/...

ROMKit-Studio-Digimon.zip
  ROMKit Studio - Digimon/
    ROMKit Studio - Digimon.exe
    _internal/...

ROMKit-Studio-Pokapoka.zip
  ROMKit Studio - Pokapoka/
    ROMKit Studio - Pokapoka.exe
    _internal/...

ROMKit-Translator.zip
  ROMKit Translator/
    ROMKit Translator.exe
    _internal/...
```

Puedes publicar también la compilación completa de Studio como otro ZIP. Copia la
carpeta completa; el `.exe` solo no contiene todas las dependencias. Studio y Translator
se publican como `v1.2.0`, separados del historial de las utilidades ya publicadas.
Los ZIP llevan versión en su nombre.

Los EXE autónomos se compilan con `scripts/desktop/build.py --onefile` y se publican
también como assets individuales de Translator, Base y cada juego. Incluyen las
dependencias y las extraen temporalmente al arrancar. No deben confundirse con el
EXE pequeño de una carpeta `_internal`, que necesita esa carpeta completa.

La licencia MIT de la raíz cubre el código propio de Studio/Translator y sus scripts.
Las herramientas con licencia propia, dependencias y catálogos conservan sus derechos.
