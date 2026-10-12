# Retro M3U Organizer

Organiza juegos multidisco de PlayStation, SEGA Saturn y Dreamcast y genera listas `.m3u` con rutas relativas.

## Windows

Descarga **Retro.M3U.Organizer.exe** desde [Releases de ROMKit](https://github.com/jcarlosab/romkit/releases/latest). No necesitas instalar Python.

## Uso

- **Modo automático:** selecciona una carpeta y revisa los juegos agrupados por marcadores como `(Disc 1)` o `[CD 2]` antes de generar sus listas.
- **Modo manual:** añade los archivos de disco, cambia su orden y elige el nombre del juego.

Al generar una lista, el programa mueve los discos a una subcarpeta con el nombre del juego y crea el `.m3u` en la carpeta principal. Por ejemplo:

```text
Final Fantasy VII.m3u
Final Fantasy VII/
  Final Fantasy VII (Disc 1).chd
  Final Fantasy VII (Disc 2).chd
```

El listado utiliza rutas como `Final Fantasy VII/Final Fantasy VII (Disc 1).chd`. Admite `.chd`, `.bin`, `.cue`, `.iso`, `.gdi`, `.cdi`, `.ccd` y `.img`; revisa los archivos auxiliares de los formatos que los necesiten.

## Código fuente

Requiere Python con Tkinter; no utiliza dependencias externas para ejecutarse. Desde la raíz del repositorio:

```powershell
python tools/m3u-organizer/run.py
```

## Crear el ejecutable

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --distpath dist "tools/m3u-organizer/Retro M3U Organizer.spec"
```

El resultado es `dist/Retro M3U Organizer.exe`. El icono está incluido en la compilación.

## Licencia

Este programa se distribuye bajo GPL-3.0. Consulta [LICENSE](LICENSE).
