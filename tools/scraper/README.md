# ROMKit Scraper

Busca, elige y guarda carátulas para Cannoli, EmulationStation / RetroPie y ES-DE. Incluye una galería de seis imágenes, vista ampliada y migración de carátulas entre frontends.

## Windows

Descarga **ROMKit Scraper.exe** desde [Releases](https://github.com/jcarlosab/romkit/releases/latest) y guárdalo en una carpeta donde puedas escribir. No necesitas instalar Python. La aplicación crea `scraper_config.json` junto al ejecutable al aplicar la configuración o cerrar.

## Uso

1. En **Biblioteca y análisis**, selecciona frontend, consola y carpetas de ROMs y destino.
2. Selecciona Libretro o SteamGridDB y pulsa **Analizar biblioteca**. El listado y el porcentaje se actualizan durante el análisis; **Detener análisis** conserva los resultados encontrados.
3. En **Carátulas**, selecciona las imágenes de varios juegos y pulsa **Guardar seleccionadas**. Otro clic deselecciona una imagen; el doble clic o **Preview** la amplían. Las flechas recorren los resultados.
4. Usa **Buscar** para corregir el título o cambiar la fuente. También puedes importar una imagen local. **Descargar coincidencias** guarda las elecciones automáticas.

Las elecciones pendientes se conservan durante la sesión. La aplicación avisa antes de descartarlas. Al cambiar de consola se vacían las carpetas de ROMs y destino.

## Fuentes y configuración

| Fuente | Acceso | Selección |
| --- | --- | --- |
| Libretro | Sin cuenta ni clave | Consola, título, región y variante del nombre |
| SteamGridDB | Clave API personal en Configuración | Relevancia y valoración de carátulas |

El filtro de SteamGridDB comprueba el título contra el catálogo Libretro de la consola. Puedes desactivarlo en Configuración para buscar hacks o juegos fuera del catálogo. SteamGridDB no identifica la consola de cada imagen; revisa la edición en juegos multiplataforma.

La identificación utiliza los nombres de archivo, sin hashes. Se consultan los archivos de la carpeta seleccionada, sin descomprimir ni recorrer subcarpetas. No se descargan juegos.

Las preferencias se guardan al cerrar y al aplicar Configuración. En Windows, la clave API se cifra para el usuario actual mediante DPAPI. Al cambiar de equipo o usuario puede ser necesario introducirla de nuevo. **La configuración personal no se distribuye ni se publica**. El archivo también contiene rutas locales: no lo compartas.

## Exportación y migración

| Frontend | Estructura dentro del destino |
| --- | --- |
| Cannoli | `Art/<sistema>/<nombre-ROM>.png` o `.jpg` |
| EmulationStation / RetroPie | `<sistema>/images/` y `<sistema>/gamelist.xml` |
| ES-DE | `downloaded_media/<sistema>/covers/` y `gamelists/<sistema>/gamelist.xml` |

Se conservan las imágenes y metadatos existentes. Cada imagen nueva incluye un archivo `.source.json` con su procedencia. Antes de modificar un listado XML se crea una copia `.bak`.

**Migrar carátulas** trabaja con las raíces de los frontends de origen y destino, para todos los sistemas, sin seleccionar consola ni ROMs. Conserva el origen y adapta los nombres de sistemas conocidos. Si Cannoli no dispone de un listado de juegos, las imágenes se copian pero el frontend de destino puede necesitar generar su `gamelist.xml`.

## Ejecutar el código

Requiere Python 3.13 con Tkinter. Desde la raíz del repositorio:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r tools/scraper/requirements.txt
.venv/Scripts/python.exe tools/scraper/romkit_scraper.py
```

Para desarrollar, ejecutar las pruebas y crear el ejecutable:

```powershell
.venv/Scripts/python.exe -m pip install -r tools/scraper/requirements-dev.txt
.venv/Scripts/python.exe -m pytest tools/scraper/tests -q
.venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath dist tools/scraper/romkit_scraper.spec
```

El ejecutable se genera en `dist/ROMKit Scraper.exe`. Solo incorpora el código y los recursos de `assets/`.

## Archivos

- `romkit_scraper.py`: interfaz y coordinación de búsquedas.
- `scraper_core.py`: fuentes, coincidencias, exportación y migración.
- `scraper_config.py`: preferencias y protección de credenciales.
- `assets/`: icono de Windows y logo pequeño.
- `tests/`: pruebas del scraper.
- `requirements*.txt` y `romkit_scraper.spec`: dependencias y compilación.
