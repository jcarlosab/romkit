import os
import sys
import re
import shutil


# =================================================================
# CONSTANTES Y UTILIDADES
# =================================================================

def resource_path(relative_path):
    """Obtiene la ruta absoluta para recursos, compatible con PyInstaller."""
    try:
        # Modo PyInstaller
        base_path = sys._MEIPASS
    except Exception:
        # Modo normal (ejecutando desde Python)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# Extensiones de archivo de disco válidas
VALID_EXTENSIONS = ('.chd', '.bin', '.cue', '.iso', '.gdi', '.cdi', '.ccd', '.img')

# Patrón para encontrar el número de disco (ej: (Disc 2), [CD 3], - D4)
DISC_PATTERN = re.compile(r'[\s(\[-](Disc|CD|Disco|D)\s?(\d+)[\])]', re.IGNORECASE)

# Patrón para limpiar el nombre: elimina marcadores de disco, texto entre paréntesis/corchetes, y guiones de sufijo.
CLEAN_PATTERN = re.compile(r'[\s(\[-](Disc|CD|Disco|D)\s?(\d+)[\])]|\([\s\S]*?\)|\[[\s\S]*?]|-\s*.*', re.IGNORECASE)


def clean_game_name(filename):
    """Limpia el nombre del archivo para obtener el nombre base del juego."""
    name_without_ext = os.path.splitext(filename)[0]
    cleaned_name = CLEAN_PATTERN.sub('', name_without_ext).strip()
    return cleaned_name.rstrip('.').strip()


# =================================================================
# FUNCIÓN CENTRAL DE PROCESAMIENTO
# =================================================================

def process_m3u_generation(m3u_base_name: str, output_dir: str, full_file_paths: list):
    """
    Lógica central para crear el M3U, mover archivos y escribir rutas relativas.

    Args:
        m3u_base_name (str): Nombre base para el M3U y la subcarpeta de discos.
        output_dir (str): Directorio donde se creará el M3U y la subcarpeta.
        full_file_paths (list): Lista de rutas absolutas a los archivos de disco (ya ordenados).
    """

    # 1. Crear la subcarpeta
    subfolder_path = os.path.join(output_dir, m3u_base_name)
    if not os.path.exists(subfolder_path):
        os.makedirs(subfolder_path)

    m3u_path = os.path.join(output_dir, f"{m3u_base_name}.m3u")

    # 2. Escribir el M3U y mover los discos
    with open(m3u_path, 'w', encoding='utf-8') as f:
        for full_file_path in full_file_paths:
            filename = os.path.basename(full_file_path)

            # Mover el archivo de disco a la subcarpeta
            try:
                # Solo mover si el archivo NO está ya en la carpeta de destino
                dest_path = os.path.join(subfolder_path, filename)
                if full_file_path != dest_path:
                    shutil.move(full_file_path, dest_path)
            except Exception as e:
                # Esto es una advertencia, no un error fatal, la generación del M3U puede continuar
                print(
                    f"Advertencia (Core): No se pudo mover {filename} desde {os.path.dirname(full_file_path)}. {e}")

            # Escribir la ruta relativa en el M3U (NombreSubcarpeta/filename)
            # El uso de replace('\\', '/') garantiza la compatibilidad con Linux/RetroArch.
            relative_path = os.path.join(m3u_base_name, filename).replace('\\', '/')
            f.write(f"{relative_path}\n")