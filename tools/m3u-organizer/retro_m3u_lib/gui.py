import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .core import (  # Importa solo lo necesario del core
    resource_path,
    VALID_EXTENSIONS,
    DISC_PATTERN,
    clean_game_name,
    process_m3u_generation
)


# Nota: La importación de 'shutil' y 're' ya no es necesaria aquí

# =================================================================
# APLICACIÓN PRINCIPAL (CLASE POO)
# =================================================================

class M3UGeneratorApp:
    def __init__(self, master):
        """Constructor: Inicializa el estado y configura la GUI."""
        self.master = master
        self.roms_directory = ""
        # Diccionario para el modo automático: {nombre_limpio: {disc_num: filename}}
        self.multi_disc_groups = {}
        # Lista para el modo manual: [ruta_completa_archivo_1, ruta_completa_archivo_2, ...]
        self.manual_listbox_files = []

        # Referencias a widgets
        self.dir_entry = None
        self.m3u_name_manual = None
        self.manual_listbox = None
        self.game_listbox = None
        self.notebook = None

        # Lógica de construcción de la GUI
        self._setup_main_window()
        self._create_notebook()
        self._setup_manual_tab_content()
        self._setup_automatic_tab_content()

    ## --- CONFIGURACIÓN DE LA VENTANA PRINCIPAL ---

    def _setup_main_window(self):
        """Configura el título, icono y tamaño de la ventana principal."""
        self.master.title("Retro M3U Organizer")
        try:
            icon_path = resource_path("images/m3u-logo.ico")
            if os.path.exists(icon_path):
                self.master.iconbitmap(icon_path)
        except Exception:
            pass
        self.master.geometry("700x550")
        self.master.minsize(550, 450)

    def _create_notebook(self):
        """Crea el contenedor de pestañas (Notebook)."""
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(pady=10, padx=10, fill="both", expand=True)

        self.tab_manual = ttk.Frame(self.notebook)
        self.tab_automatic = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_manual, text="Modo Manual 🧑‍💻")
        self.notebook.add(self.tab_automatic, text="Modo Automático 🤖")

    ## --- MODOS DE INTERFAZ (Contenido) ---

    def _setup_manual_tab_content(self):
        """Configura los widgets para el Modo Manual."""
        manual_frame = ttk.LabelFrame(self.tab_manual, text="Archivos a incluir en el M3U")
        manual_frame.pack(pady=10, padx=10, fill="x")

        # Listbox y Scrollbar
        list_frame = ttk.Frame(manual_frame)
        list_frame.pack(padx=10, pady=5, fill="x", expand=True)

        manual_scrollbar = ttk.Scrollbar(list_frame)
        manual_scrollbar.pack(side="right", fill="y")

        self.manual_listbox = tk.Listbox(list_frame, height=10, selectmode=tk.EXTENDED,
                                         yscrollcommand=manual_scrollbar.set)
        self.manual_listbox.pack(side="left", fill="x", expand=True)
        manual_scrollbar.config(command=self.manual_listbox.yview)

        # Botones
        button_frame = ttk.Frame(manual_frame)
        button_frame.pack(pady=5, padx=10)

        ttk.Button(button_frame, text="➕ Añadir Archivos Disco", command=self.add_manual_files).pack(side="left",
                                                                                                     padx=5)
        ttk.Button(button_frame, text="➖ Quitar Seleccionados", command=self.remove_manual_files).pack(side="left",
                                                                                                       padx=5)
        ttk.Button(button_frame, text="⬆️ Subir", command=self.move_manual_file_up).pack(side="left", padx=5)
        ttk.Button(button_frame, text="⬇️ Bajar", command=self.move_manual_file_down).pack(side="left", padx=5)

        # Nombre del M3U
        ttk.Label(manual_frame, text="Nombre del archivo M3U (y de la subcarpeta de discos):").pack(pady=(10, 0))
        self.m3u_name_manual = ttk.Entry(manual_frame)
        self.m3u_name_manual.pack(pady=5, fill="x", padx=10)

        # Botón Generar
        ttk.Button(self.tab_manual, text="💾 GENERAR M3U MANUAL", command=self.generate_manual_m3u).pack(pady=10)

    def _setup_automatic_tab_content(self):
        """Configura los widgets para el Modo Automático."""
        dir_frame = ttk.LabelFrame(self.tab_automatic, text="Selección de Directorio de ROMs")
        dir_frame.pack(pady=10, padx=10, fill="x")

        self.dir_entry = ttk.Entry(dir_frame, state='readonly')
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(dir_frame, text="📁 Seleccionar Carpeta", command=self.select_roms_directory).pack(side="left",
                                                                                                     padx=5)

        list_frame = ttk.LabelFrame(self.tab_automatic,
                                    text="Juegos Multi-Disco Encontrados (Seleccione para generar M3U)")
        list_frame.pack(pady=10, padx=10, fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.game_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set)
        self.game_listbox.pack(padx=10, pady=5, fill="both", expand=True)
        scrollbar.config(command=self.game_listbox.yview)

        ttk.Button(self.tab_automatic, text="💾 GENERAR M3U SELECCIONADOS", command=self.generate_automatic_m3u).pack(
            pady=10)

    ## --- LÓGICA DE EVENTOS Y MANEJO DE DATOS (Modo Manual) ---

    def add_manual_files(self):
        """Abre un diálogo para seleccionar archivos y los añade a la lista."""
        file_types_list = [
            ("Archivos de Disco", [f"*{ext}" for ext in VALID_EXTENSIONS]),
            ("Todos los archivos", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Seleccionar archivos de disco (en orden)",
            filetypes=file_types_list
        )
        if files:
            for f in files:
                self.manual_listbox_files.append(f)
                self.manual_listbox.insert(tk.END, os.path.basename(f))
            messagebox.showinfo("Añadido", f"{len(files)} archivos añadidos. Asegúrese de que el orden es correcto.")

    def remove_manual_files(self):
        """Elimina los archivos seleccionados de la lista."""
        selected_indices = self.manual_listbox.curselection()
        if not selected_indices:
            return

        for i in selected_indices[::-1]:
            self.manual_listbox.delete(i)
            del self.manual_listbox_files[i]

    def move_manual_file_up(self):
        """Mueve el archivo seleccionado una posición hacia arriba."""
        selected = self.manual_listbox.curselection()
        if not selected: return

        index = selected[0]
        if index > 0:
            self.manual_listbox_files.insert(index - 1, self.manual_listbox_files.pop(index))
            item = self.manual_listbox.get(index)
            self.manual_listbox.delete(index)
            self.manual_listbox.insert(index - 1, item)
            self.manual_listbox.select_set(index - 1)

    def move_manual_file_down(self):
        """Mueve el archivo seleccionado una posición hacia abajo."""
        selected = self.manual_listbox.curselection()
        if not selected: return

        index = selected[0]
        if index < self.manual_listbox.size() - 1:
            self.manual_listbox_files.insert(index + 1, self.manual_listbox_files.pop(index))
            item = self.manual_listbox.get(index)
            self.manual_listbox.delete(index)
            self.manual_listbox.insert(index + 1, item)
            self.manual_listbox.select_set(index + 1)

    def generate_manual_m3u(self):
        """Genera el M3U a partir de la selección manual."""
        if not self.manual_listbox_files:
            messagebox.showerror("Error", "No ha seleccionado ningún archivo de disco.")
            return

        m3u_base_name = self.m3u_name_manual.get().strip()
        if not m3u_base_name:
            messagebox.showerror("Error", "Debe introducir un nombre para el archivo M3U.")
            return

        output_dir = filedialog.askdirectory(title="Seleccionar carpeta de destino (donde se guardará el M3U)")
        if not output_dir:
            return

        # Llama a la lógica de negocio (CORE)
        process_m3u_generation(m3u_base_name, output_dir, self.manual_listbox_files)

        messagebox.showinfo("Éxito",
                            f"Archivo M3U '{m3u_base_name}.m3u' creado correctamente en {output_dir}.\nLos discos se movieron a la subcarpeta '{m3u_base_name}'.")

        # Limpieza de la interfaz después del éxito
        self.manual_listbox.delete(0, tk.END)
        self.manual_listbox_files = []
        self.m3u_name_manual.delete(0, tk.END)

    ## --- LÓGICA DE EVENTOS Y MANEJO DE DATOS (Modo Automático) ---

    def select_roms_directory(self):
        """Abre un diálogo para seleccionar el directorio raíz de ROMs y escanea."""
        new_dir = filedialog.askdirectory(title="Seleccionar el directorio principal de ROMs (Ej: /roms/psx)")
        if new_dir:
            self.roms_directory = new_dir
            self.dir_entry.config(state='normal')
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, self.roms_directory)
            self.dir_entry.config(state='readonly')
            self.scan_for_multi_disc_games()

    def scan_for_multi_disc_games(self):
        """Escanea el directorio para encontrar y agrupar juegos multidisco."""
        self.multi_disc_groups = {}
        self.game_listbox.delete(0, tk.END)

        if not self.roms_directory: return

        for filename in os.listdir(self.roms_directory):
            # Ignorar carpetas y archivos que no son discos válidos
            if os.path.isdir(os.path.join(self.roms_directory, filename)) or \
                    not filename.lower().endswith(VALID_EXTENSIONS):
                continue

            match_disc = DISC_PATTERN.search(filename)

            # Solo procesar archivos que tienen un marcador de disco
            if match_disc:
                game_name_clean = clean_game_name(filename)

                if not game_name_clean: continue

                disc_number = int(match_disc.group(2))

                if game_name_clean not in self.multi_disc_groups:
                    self.multi_disc_groups[game_name_clean] = {}

                self.multi_disc_groups[game_name_clean][disc_number] = filename

        # Filtrar solo los grupos con 2 o más discos
        final_groups = {
            name: discs for name, discs in self.multi_disc_groups.items() if len(discs) >= 2
        }
        self.multi_disc_groups = final_groups

        if not self.multi_disc_groups:
            self.game_listbox.insert(tk.END, "--- No se encontraron juegos multidisco ---")
            return

        # Rellenar Listbox para la selección
        for name in sorted(self.multi_disc_groups.keys()):
            count = len(self.multi_disc_groups[name])
            self.game_listbox.insert(tk.END, f"{name} ({count} Discos)")

        messagebox.showinfo("Escaneo Completo",
                            f"Se identificaron {len(self.multi_disc_groups)} juegos multidisco listos para el M3U.")

    def generate_automatic_m3u(self):
        """Genera los M3U para los juegos seleccionados automáticamente."""
        selected_indices = self.game_listbox.curselection()
        if not selected_indices:
            messagebox.showerror("Error", "Debe seleccionar al menos un juego del listado.")
            return

        if not self.roms_directory:
            messagebox.showerror("Error", "Debe seleccionar un directorio de ROMs primero.")
            return

        game_names_keys = list(self.multi_disc_groups.keys())
        processed_count = 0

        for i in selected_indices:
            game_name_base = game_names_keys[i]
            discs = self.multi_disc_groups[game_name_base]

            # Crear la lista ordenada de rutas completas para el CORE
            files_to_process = [os.path.join(self.roms_directory, filename)
                                for _, filename in sorted(discs.items())]

            # Llama a la lógica de negocio (CORE)
            process_m3u_generation(game_name_base, self.roms_directory, files_to_process)
            processed_count += 1

        messagebox.showinfo("Generación Completa",
                            f"Se generaron {processed_count} archivos M3U en el directorio {self.roms_directory}.\nLos discos se movieron a subcarpetas individuales nombradas con el juego.")
        self.scan_for_multi_disc_games()