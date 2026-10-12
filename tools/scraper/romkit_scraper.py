"""Desktop scraper: python tools/scraper/romkit_scraper.py."""
import queue
import threading
import tkinter as tk
import webbrowser
import io
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from scraper_core import SYSTEMS, FRONTENDS, EXTENSIONS, Export, Candidate, libretro, steamgriddb, automatic_steamgriddb, automatic, search, fetch, migrate_covers, normalized, index_candidates, indexed_candidates
from scraper_config import ConfigStore

VERSION = "0.32"
APP_NAME = "ROMKit Scraper"

COLORS = {
    "background": "#b8babe", "panel": "#dedfda", "field": "#f4f3ed",
    "text": "#24272d", "muted": "#555961", "border": "#969a9f",
    "green": "#197754", "red": "#a9363d", "blue": "#2e509d", "pink": "#a74878",
}


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} · v{VERSION}")
        root.geometry("1200x900")
        root.resizable(False, False)
        self.style(root)
        assets = Path(__file__).with_name("assets")
        logo_path = assets / "romkit-logo.png"
        self.logo = tk.PhotoImage(master=root, file=str(logo_path)) if logo_path.exists() else None
        if self.logo:
            root.iconphoto(True, self.logo)
        icon_path = assets / "romkit.ico"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.files, self.catalog, self.results = [], [], []
        self.libretro_catalogs = {}
        self.libretro_indexes = {}
        self.catalog_index = {}
        self.library_system = None
        self.export = None
        self.buttons = []
        self.frontend = tk.StringVar(value="Cannoli")
        self.platform_names = {name.replace(" - ", " "): tag for tag, (name, _) in SYSTEMS.items()}
        self.platform = tk.StringVar(value="Nintendo Game Boy Advance")
        self.tag = tk.StringVar(value="GBA")
        self.roms, self.output, self.query = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.source = tk.StringVar(value="Libretro")
        self.region = tk.StringVar(value="Europe")
        self.api_key = tk.StringVar()
        self.analysis_source = tk.StringVar(value="Libretro")
        self.platform_filter = tk.StringVar(value="Sí")
        self.config_store = ConfigStore()
        self.restore_config()
        self.active_analysis_source = "Libretro"
        self.suggestions = {}
        self.pending_covers = {}
        self.analyzed_count = 0
        self.preview_token = 0
        self.grid_token = 0
        self.result_index = None
        self.result_page = 0
        self.page_size = 6
        self.image_cache = OrderedDict()
        self.image_cache_size = 0
        self.image_lock = threading.Lock()
        self.image_inflight = {}
        self.thumbnail_cache = OrderedDict()
        self.base_states = {}
        self.thumbnail_images = {}
        self.analysis_running = False
        self.analysis_progress = tk.DoubleVar(value=0)
        self.progress_text = tk.StringVar(value="0 %")
        self.status = tk.StringVar(value="Elige una consola y sus carpetas. Después pulsa Analizar.")
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(header, text="Configuración", command=self.open_settings).pack(side="right", anchor="n")
        ttk.Button(header, text="Migrar carátulas", command=self.open_migration).pack(side="right", anchor="n", padx=(0, 8))
        ttk.Label(header, text=f"{APP_NAME} (v{VERSION})", style="Accent.TLabel").pack(side="left")
        self.workspace_tabs = ttk.Notebook(frame)
        self.workspace_tabs.grid(row=1, column=0, sticky="nsew")
        self.gallery_tab = ttk.Frame(self.workspace_tabs, padding=(0, 14))
        preparation = ttk.Frame(self.workspace_tabs, padding=18)
        self.workspace_tabs.add(preparation, text="  Biblioteca y análisis  ")
        self.workspace_tabs.add(self.gallery_tab, text="  Carátulas  ")
        setup = ttk.Frame(preparation, padding=18, style="Card.TFrame")
        setup.pack(fill="x", pady=(0, 14))
        ttk.Label(setup, text="Consola y destino", style="Section.TLabel").pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(setup, style="Card.TFrame")
        row.pack(fill="x")
        for label, var, choices in (("Frontend", self.frontend, FRONTENDS), ("Consola", self.platform, list(self.platform_names))):
            ttk.Label(row, text=label, style="Card.TLabel").pack(side="left", padx=(0, 8))
            box = ttk.Combobox(row, textvariable=var, values=choices, state="readonly", width=24 if label == "Frontend" else 38)
            box.pack(side="left", padx=(0, 18))
            box.bind("<<ComboboxSelected>>", self.platform_changed if label == "Consola" else self.layout)
        ttk.Label(row, text="Carpeta del sistema", style="Card.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(row, textvariable=self.tag, width=15).pack(side="left")
        for label, var in (("ROMs · una consola", self.roms), ("Destino · raíz del frontend", self.output)):
            row = ttk.Frame(setup, style="Card.TFrame")
            row.pack(fill="x", pady=(10, 0))
            ttk.Label(row, text=label, style="Card.TLabel", width=24).pack(side="left", padx=(0, 8))
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Elegir", command=lambda v=var: self.browse(v)).pack(side="left", padx=6)
        self.hint = ttk.Label(setup, style="MutedCard.TLabel")
        self.hint.pack(anchor="w", pady=6)
        self.tag.trace_add("write", lambda *_: self.hint_text())
        self.hint_text()
        region_row = ttk.Frame(setup, style="Card.TFrame")
        region_row.pack(fill="x", pady=4)
        ttk.Label(region_row, text="Carátula preferida si la ROM no indica región", style="Card.TLabel").pack(side="left", padx=(0, 10))
        ttk.Combobox(region_row, textvariable=self.region, values=("Europe", "USA", "Japan", "World", "Sin preferencia"), state="readonly", width=18).pack(side="left")
        row = ttk.Frame(preparation)
        row.pack(fill="x", pady=(0, 14))
        ttk.Label(row, text="Fuente al analizar").pack(side="left", padx=(0, 8))
        analysis_box = ttk.Combobox(row, textvariable=self.analysis_source, values=("Libretro", "SteamGridDB"), state="readonly", width=17)
        analysis_box.pack(side="left", padx=(0, 8))
        analysis_box.bind("<<ComboboxSelected>>", self.analysis_source_changed)
        self.button(row, "Analizar biblioteca", self.analyze)
        self.button(row, "Descargar coincidencias", self.batch)
        ttk.Button(row, text="Cancelar", command=self.stop.set, style="Cancel.TButton").pack(side="left", padx=4)
        self.analysis_help = ttk.Label(preparation, text="Libretro: coincidencias automáticas. La búsqueda individual permite elegir otra fuente.", style="Muted.TLabel", wraplength=1000)
        self.analysis_help.pack(fill="x", pady=(0, 8))
        ttk.Label(preparation, text="Selecciona la consola, las carpetas y la fuente. Pulsa Analizar biblioteca para buscar carátulas. Puedes elegirlas en Carátulas o guardar las coincidencias con Descargar coincidencias.", style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=20)
        footer = ttk.Frame(frame)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_frame = ttk.Frame(footer, height=40)
        status_frame.pack(fill="x", pady=(0, 6))
        status_frame.pack_propagate(False)
        ttk.Label(status_frame, textvariable=self.status, wraplength=1100, style="Muted.TLabel").pack(anchor="w")
        progress_row = ttk.Frame(footer)
        progress_row.pack(fill="x")
        progress_row.columnconfigure(1, weight=1)
        ttk.Label(progress_row, text="Análisis", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 10))
        self.stop_analysis_button = ttk.Button(progress_row, text="Detener análisis", command=self.stop_analysis, state="disabled", style="Cancel.TButton")
        self.stop_analysis_button.grid(row=0, column=3, padx=(12, 0))
        self.progress = ttk.Progressbar(progress_row, variable=self.analysis_progress, maximum=100, mode="determinate", style="Analysis.Horizontal.TProgressbar")
        self.progress.grid(row=0, column=1, sticky="nsew", pady=4)
        ttk.Label(progress_row, textvariable=self.progress_text, width=6, anchor="e", font=("Consolas", 11, "bold")).grid(row=0, column=2, padx=(10, 0))
        panes = ttk.Frame(self.gallery_tab)
        panes.pack(fill="both", expand=True)
        panes.columnconfigure(0, weight=1, uniform="panels")
        panes.columnconfigure(1, weight=2, uniform="panels")
        panes.rowconfigure(0, weight=1)
        left, right = ttk.Frame(panes, padding=14, style="Card.TFrame"), ttk.Frame(panes, padding=14, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew")
        actions = ttk.Frame(right, style="Card.TFrame")
        actions.pack(side="bottom", fill="x", pady=(8, 0))
        self.save_button = self.button(actions, "Guardar seleccionadas (0)", self.use)
        self.button(actions, "Importar imagen", self.local)
        ttk.Button(actions, text="Ver fuente", command=self.open_source).pack(side="left", padx=4)
        ttk.Label(left, text="Juegos de tu colección", style="Section.TLabel").pack(anchor="w")
        self.summary = tk.StringVar(value="Empieza en Biblioteca y análisis.")
        ttk.Label(left, textvariable=self.summary, style="MutedCard.TLabel", wraplength=320).pack(anchor="w", pady=(4, 12))
        self.games = ttk.Treeview(left, columns=("state",), selectmode="browse")
        self.games.heading("#0", text="ROM")
        self.games.heading("state", text="Estado")
        self.games.column("#0", width=190, minwidth=100)
        self.games.column("state", width=118, minwidth=118, stretch=False, anchor="center")
        scroll = ttk.Scrollbar(left, command=self.games.yview)
        scroll.pack(side="right", fill="y")
        self.games.configure(yscrollcommand=scroll.set)
        self.games.pack(fill="both", expand=True)
        self.games.tag_configure("ready", foreground=COLORS["green"])
        self.games.tag_configure("pending", foreground=COLORS["blue"])
        self.games.tag_configure("error", foreground=COLORS["red"])
        self.games.bind("<<TreeviewSelect>>", self.select_rom)
        ttk.Label(right, text="Carátulas disponibles", style="Section.TLabel").pack(anchor="w")
        ttk.Label(right, text="Elige portadas para varios juegos y guárdalas juntas · doble clic para Preview", style="MutedCard.TLabel").pack(anchor="w", pady=(4, 12))
        search_row = ttk.Frame(right, style="Card.TFrame")
        search_row.pack(fill="x")
        query_entry = ttk.Entry(search_row, textvariable=self.query)
        query_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        query_entry.bind("<Return>", lambda _: self.find())
        row = search_row
        source_box = ttk.Combobox(row, textvariable=self.source, values=("Libretro", "SteamGridDB"), state="readonly", width=15)
        source_box.pack(side="left")
        source_box.bind("<<ComboboxSelected>>", self.source_changed)
        self.button(row, "Buscar", self.find)
        results_frame = ttk.Frame(right, style="Card.TFrame")
        self.results_frame = results_frame
        results_frame.pack(fill="both", expand=True, pady=12)
        self.grid_frame = tk.Frame(results_frame, bg=COLORS["panel"], height=390)
        self.grid_frame.pack(fill="both", expand=True)
        self.grid_frame.pack_propagate(False)
        self.grid_frame.grid_propagate(False)
        for column in range(3):
            self.grid_frame.columnconfigure(column, weight=1, uniform="covers")
        for grid_row in range(2):
            self.grid_frame.rowconfigure(grid_row, weight=1, uniform="cover_rows")
        navigation = ttk.Frame(right, style="Card.TFrame")
        navigation.pack(fill="x", pady=4)
        ttk.Button(navigation, text="‹", width=3, command=lambda: self.change_page(-1)).pack(side="left")
        self.page_label = ttk.Label(navigation, text="Sin resultados", style="Card.TLabel")
        self.page_label.pack(side="left", padx=8)
        ttk.Button(navigation, text="›", width=3, command=lambda: self.change_page(1)).pack(side="left")
        ttk.Button(navigation, text="Preview", command=self.large_preview, style="Preview.TButton").pack(side="right")
        self.art = ttk.Label(right, text="Selecciona una carátula", style="MutedCard.TLabel")
        details_frame = ttk.Frame(right, height=48, style="Card.TFrame")
        details_frame.pack(fill="x", pady=4)
        details_frame.pack_propagate(False)
        self.details = ttk.Label(details_frame, wraplength=680, style="MutedCard.TLabel")
        self.details.pack(fill="both", expand=True)
        self.workspace_tabs.select(preparation)
        self.render_grid()
        root.protocol("WM_DELETE_WINDOW", self.close)
        if self.config_store.warning:
            self.status.set(self.config_store.warning)
        root.after(100, self.poll)

    def button(self, parent, label, command):
        style = "Search.TButton" if label in ("Buscar", "Analizar biblioteca") else "Primary.TButton" if label.startswith("Guardar seleccionadas") or label == "Descargar coincidencias" else "TButton"
        button = ttk.Button(parent, text=label, command=command, style=style)
        button.pack(side="left", padx=4)
        self.buttons.append(button)
        return button

    def preference_variables(self):
        return {name: getattr(self, name) for name in ("frontend", "platform", "tag", "roms", "output", "source", "region", "analysis_source", "platform_filter")}

    def restore_config(self):
        preferences, secrets = self.config_store.load()
        valid = {"frontend": FRONTENDS, "platform": self.platform_names, "source": ("Libretro", "SteamGridDB"), "analysis_source": ("Libretro", "SteamGridDB"), "region": ("Europe", "USA", "Japan", "World", "Sin preferencia")}
        valid["platform_filter"] = ("Sí", "No")
        for name, variable in self.preference_variables().items():
            value = preferences.get(name)
            if isinstance(value, str) and (name not in valid or value in valid[name]):
                variable.set(value)
        self.api_key.set(secrets.get("steamgriddb", "") if isinstance(secrets.get("steamgriddb", ""), str) else "")

    def save_config(self):
        preferences = {name: variable.get() for name, variable in self.preference_variables().items()}
        secrets = {"steamgriddb": self.api_key.get()}
        self.config_store.save(preferences, secrets)

    def close(self):
        if self.pending_covers and not messagebox.askyesno("Carátulas pendientes", "Hay carátulas seleccionadas sin guardar. ¿Cerrar y descartar esas selecciones?", parent=self.root):
            return
        try:
            self.save_config()
        except OSError as error:
            messagebox.showerror("Guardar configuración", str(error), parent=self.root)
            return
        self.stop.set()
        self.root.destroy()

    def style(self, root):
        palette = COLORS
        root.configure(background=palette["background"])
        root.option_add("*Font", "{Segoe UI} 10")
        root.option_add("*TCombobox*Listbox.background", palette["field"])
        root.option_add("*TCombobox*Listbox.foreground", palette["text"])
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=palette["background"], foreground=palette["text"], font=("Segoe UI", 10))
        style.configure("Card.TFrame", background=palette["panel"], borderwidth=0)
        style.configure("Card.TLabel", background=palette["panel"])
        style.configure("Section.TLabel", background=palette["panel"], font=("Consolas", 12, "bold"))
        style.configure("Accent.TLabel", foreground=palette["text"], font=("Consolas", 18, "bold"))
        style.configure("Muted.TLabel", foreground=palette["muted"])
        style.configure("MutedCard.TLabel", background=palette["panel"], foreground=palette["muted"], font=("Segoe UI", 9))
        style.configure("Preview.TLabel", background=palette["text"], foreground=palette["field"])
        style.configure("TButton", background=palette["panel"], foreground=palette["text"], borderwidth=1, relief="raised", padding=(12, 8))
        style.configure("Arrow.TButton", font=("Segoe UI", 18), padding=(8, 2))
        style.map("TButton", background=[("active", palette["field"]), ("disabled", "#c7c9c8")], foreground=[("disabled", "#73767b")])
        for name, color, hover in (("Primary", "green", "#218864"), ("Search", "blue", "#3d62af"), ("Preview", "pink", "#b65b8a"), ("Cancel", "red", "#bc4650")):
            style.configure(name + ".TButton", background=palette[color], foreground="#ffffff")
            style.map(name + ".TButton", background=[("disabled", "#c7c9c8"), ("active", hover)], foreground=[("disabled", "#73767b")])
        for widget in ("TEntry", "TCombobox"):
            style.configure(widget, padding=4, fieldbackground=palette["field"], foreground=palette["text"], bordercolor=palette["border"], lightcolor=palette["border"], darkcolor=palette["border"], arrowcolor=palette["text"])
            style.map(widget, fieldbackground=[("readonly", palette["field"])], foreground=[("readonly", palette["text"])])
        style.configure("Treeview", background=palette["field"], fieldbackground=palette["field"], foreground=palette["text"], borderwidth=0, rowheight=32)
        style.configure("Treeview.Heading", background=palette["panel"], foreground=palette["text"], padding=8, font=("Consolas", 10, "bold"))
        style.map("Treeview", background=[("selected", palette["blue"])], foreground=[("selected", "#ffffff")])
        style.configure("TScrollbar", background=palette["panel"], troughcolor=palette["background"], borderwidth=1, arrowcolor=palette["text"])
        style.configure("Analysis.Horizontal.TProgressbar", background=palette["blue"], lightcolor=palette["blue"], darkcolor=palette["blue"], troughcolor=palette["field"], bordercolor=palette["muted"], borderwidth=1, thickness=20)
        style.configure("TNotebook", background=palette["background"], borderwidth=0)
        style.configure("TNotebook.Tab", background="#a3a6aa", foreground=palette["text"], padding=(18, 10), expand=(0, 0, 0, 0), font=("Consolas", 10, "bold"))
        style.map("TNotebook.Tab", padding=[], expand=[], background=[("selected", palette["panel"])], foreground=[("selected", palette["blue"])])

    def analysis_source_changed(self, *_):
        source = self.analysis_source.get()
        self.analysis_help.configure(text={"Libretro": "Libretro: coincidencias automáticas; después pulsa Descargar coincidencias.", "SteamGridDB": "SteamGridDB: requiere clave API. Analiza y pulsa Descargar coincidencias; los títulos dudosos se eligen a mano."}[source])
        self.check_source_credentials(source)

    def source_changed(self, *_):
        self.check_source_credentials(self.source.get())

    def check_source_credentials(self, source):
        missing = source == "SteamGridDB" and not self.api_key.get().strip()
        if missing:
            self.write(f"{source}: añade tus credenciales en Configuración.")
            self.open_settings()

    def open_settings(self):
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            self.center_dialog(self.settings_window)
            self.settings_window.lift()
            return
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        self.settings_window = dialog
        dialog.title("Configuración · Fuentes")
        dialog.geometry("580x420")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        content = ttk.Frame(frame)
        content.grid(row=0, column=0, sticky="nsew")
        ttk.Label(content, text="SteamGridDB", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(content, text="Las credenciales se guardan cifradas para tu usuario de Windows.", wraplength=530).pack(anchor="w", pady=(6, 12))
        ttk.Label(content, text="Clave API").pack(anchor="w")
        value = tk.StringVar(value=self.api_key.get())
        entry = ttk.Entry(content, textvariable=value, show="•")
        entry.pack(fill="x", pady=6)
        row = ttk.Frame(content)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Obtener clave", command=lambda: webbrowser.open("https://www.steamgriddb.com/profile/preferences")).pack(side="left")
        filter_value = tk.StringVar(value=self.platform_filter.get())
        ttk.Checkbutton(content, text="Filtrar SteamGridDB por el catálogo de la consola", variable=filter_value, onvalue="Sí", offvalue="No").pack(anchor="w", pady=(8, 0))
        ttk.Label(content, text="Desactívalo para buscar hacks o juegos ausentes del catálogo. SteamGridDB no identifica la consola de cada imagen.", style="Muted.TLabel", wraplength=530).pack(fill="x", pady=(4, 0))
        footer = ttk.Frame(frame)
        footer.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        def apply():
            self.api_key.set(value.get().strip())
            self.platform_filter.set(filter_value.get())
            try:
                self.save_config()
            except OSError as error:
                messagebox.showerror("Guardar configuración", str(error), parent=dialog)
                return
            self.write("Configuración guardada.")
            dialog.destroy()
        ttk.Button(footer, text="Aplicar", command=apply, style="Primary.TButton").pack(side="right")
        dialog.update_idletasks()
        dialog.geometry(f"{max(580, frame.winfo_reqwidth())}x{max(420, frame.winfo_reqheight())}")
        self.center_dialog(dialog)
        dialog.deiconify()
        entry.focus_set()

    def open_migration(self):
        if self.busy:
            self.write("Espera a que termine la operación actual para migrar carátulas.")
            return
        if hasattr(self, "migration_window") and self.migration_window.winfo_exists():
            self.migration_window.lift()
            return
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        self.migration_window = dialog
        dialog.title("Migrar carátulas")
        dialog.geometry("760x640")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Carátulas para otro frontend", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Copia las carátulas de todos los sistemas al nuevo frontend. Se adaptan las carpetas y los enlaces del listado de juegos cuando existe. Se conservan las imágenes del origen y las que ya existan en el destino.", wraplength=710).pack(fill="x", pady=(6, 12))
        source_frontend = tk.StringVar(value=self.frontend.get())
        target_frontend = tk.StringVar(value=next(f for f in FRONTENDS if f != self.frontend.get()))
        source_root = tk.StringVar(value=self.output.get())
        target_root = tk.StringVar()
        fields = []
        def row(parent, label, variable, choices=None, browse=False, width=24):
            line = ttk.Frame(parent)
            line.pack(fill="x", pady=4)
            ttk.Label(line, text=label, width=20).pack(side="left", padx=(0, 8))
            field = (ttk.Combobox(line, textvariable=variable, values=choices, state="readonly", width=width)
                     if choices else ttk.Entry(line, textvariable=variable))
            field.pack(side="left", fill="x", expand=True)
            fields.append((field, "readonly" if choices else "normal"))
            if browse:
                def choose():
                    path = filedialog.askdirectory(parent=dialog)
                    if path:
                        variable.set(path)
                button = ttk.Button(line, text="Elegir", command=choose)
                button.pack(side="left", padx=(8, 0))
                fields.append((button, "normal"))
            return field
        for heading, frontend, folder in (
            ("Origen", source_frontend, source_root),
            ("Destino", target_frontend, target_root),
        ):
            group = ttk.LabelFrame(frame, text=heading, padding=(12, 8))
            group.pack(fill="x", pady=(10, 0))
            row(group, "Frontend", frontend, FRONTENDS)
            row(group, "Raíz del frontend", folder, browse=True)
        ttk.Label(frame, text="Los nombres de sistemas conocidos se adaptan automáticamente. Los demás conservan su nombre. No se necesitan archivos ROM.", style="Muted.TLabel", wraplength=710).pack(fill="x", pady=(12, 0))
        status = tk.StringVar(value="Selecciona las carpetas de origen y destino.")
        progress = tk.DoubleVar(value=0)
        status_frame = ttk.Frame(frame, height=64)
        status_frame.pack(fill="x", pady=(12, 4))
        status_frame.pack_propagate(False)
        ttk.Label(status_frame, textvariable=status, wraplength=710).pack(anchor="w")
        ttk.Progressbar(frame, variable=progress, maximum=100, style="Analysis.Horizontal.TProgressbar").pack(fill="x", pady=4)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(8, 0))
        messages = queue.Queue()
        running = False
        def close():
            if running:
                self.stop.set()
                status.set("Deteniendo la migración…")
            else:
                dialog.destroy()
        close_button = ttk.Button(actions, text="Cerrar", command=close)
        close_button.pack(side="right")
        def start():
            nonlocal running
            if self.busy:
                status.set("Espera a que termine la operación actual.")
                return
            if not source_root.get().strip() or not target_root.get().strip():
                status.set("Selecciona las raíces de ambos frontends.")
                return
            source, source_path = source_frontend.get(), Path(source_root.get())
            target, target_path = target_frontend.get(), Path(target_root.get())
            running = True
            progress.set(0)
            status.set("Buscando carátulas guardadas…")
            for field, _ in fields:
                field.configure(state="disabled")
            start_button.configure(state="disabled")
            close_button.configure(text="Detener")
            def work():
                try:
                    result = migrate_covers(source, source_path, target, target_path, self.stop,
                        lambda done, total, name: messages.put(("progress", (done, total, name))))
                    messages.put(("result", result))
                except Exception as error:
                    messages.put(("error", str(error)))
            self.task(work)
        start_button = ttk.Button(actions, text="Copiar carátulas", command=start, style="Search.TButton")
        start_button.pack(side="right", padx=(0, 8))
        def poll():
            nonlocal running
            if not dialog.winfo_exists():
                return
            while not messages.empty():
                event, value = messages.get()
                if event == "progress":
                    done, total, name = value
                    progress.set(done / total * 100 if total else 0)
                    status.set(f"{done} / {total} · {name}")
                else:
                    running = False
                    for field, state in fields:
                        field.configure(state=state)
                    start_button.configure(state="normal")
                    close_button.configure(text="Cerrar")
                    if event == "error":
                        status.set(value)
                    else:
                        if not value["cancelled"]:
                            progress.set(100)
                        text = ("Migración detenida" if value["cancelled"] else "Migración terminada") + f": {value['copied']} copiadas · {value['existing']} ya existentes · {value['systems']} sistemas · {len(value['errors'])} errores."
                        if value["unlinked"]:
                            text += f" {value['unlinked']} carátulas sin enlace: el destino necesita un listado de juegos."
                        status.set(text)
                        self.write(text)
                        if value["errors"]:
                            messagebox.showerror("Carátulas no copiadas", "\n".join(value["errors"][:10]), parent=dialog)
            dialog.after(100, poll)
        dialog.protocol("WM_DELETE_WINDOW", close)
        self.center_dialog(dialog)
        dialog.deiconify()
        poll()

    def center_dialog(self, dialog):
        self.root.update_idletasks()
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}{x:+d}{y:+d}")

    def set_progress(self, percent):
        self.analysis_progress.set(percent)
        self.progress_text.set(f"{percent:.0f} %")

    def browse(self, var):
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def platform_changed(self, *_):
        self.layout()
        self.roms.set("")
        self.output.set("")
        self.grid_token += 1
        self.preview_token += 1
        self.games.selection_remove(*self.games.selection())
        self.results = []
        self.result_index = None
        self.render_grid()
        self.write("Plataforma cambiada. Elige sus carpetas y vuelve a analizar la biblioteca.")

    def layout(self, *_):
        tag = self.platform_names[self.platform.get()]
        self.tag.set(tag if self.frontend.get() == "Cannoli" else SYSTEMS[tag][1])

    def hint_text(self):
        folder = self.tag.get()
        text = f"Art/{folder}/<ROM>.png" if self.frontend.get() == "Cannoli" else f"downloaded_media/{folder}/covers/ + gamelists/{folder}/gamelist.xml" if self.frontend.get() == "ES-DE" else f"{folder}/images/ + {folder}/gamelist.xml (ROMs en {folder}/)"
        self.hint.configure(text="Salida: " + text)

    def write(self, text):
        self.status.set(text)

    def task(self, operation):
        if self.busy:
            return
        self.busy = True
        self.stop.clear()
        self.status.set("Procesando…")
        self.stop_analysis_button.configure(state="normal" if self.analysis_running else "disabled")
        for button in self.buttons:
            button.configure(state="disabled")
        def work():
            try:
                operation()
            except Exception as error:
                self.events.put(("log", f"Error: {error}"))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def stop_analysis(self):
        if self.analysis_running and self.busy:
            self.stop.set()
            self.stop_analysis_button.configure(state="disabled")
            self.write("Deteniendo el análisis; esperando a que termine la petición en curso…")

    def analyze(self):
        if self.busy:
            return
        if self.pending_covers and not messagebox.askyesno("Carátulas pendientes", "Hay carátulas seleccionadas sin guardar. ¿Descartar esas selecciones y analizar de nuevo?", parent=self.root):
            return
        tag = self.tag.get().strip()
        if not tag or tag in (".", "..") or any(c in tag for c in '/\\:*?"<>|'):
            self.write("La carpeta del sistema debe ser un nombre simple.")
            return
        roms, output = Path(self.roms.get()), Path(self.output.get())
        if not self.roms.get() or not roms.is_dir() or not self.output.get():
            self.write("Selecciona las carpetas de ROMs y destino.")
            return
        export = Export(self.frontend.get(), output, roms, tag, tag)
        platform = self.platform_names[self.platform.get()]
        system = SYSTEMS[platform][0]
        source, key = self.analysis_source.get(), self.api_key.get()
        region = self.region.get()
        filter_platform = self.platform_filter.get() == "Sí"
        cached_catalog = self.libretro_catalogs.get(system)
        if source == "SteamGridDB" and not key.strip():
            self.write("Introduce la clave API de SteamGridDB en Configuración.")
            return
        self.analysis_running = True
        self.set_progress(0)
        self.active_analysis_source = source
        self.library_system = system
        self.suggestions = {}
        self.pending_covers.clear()
        self.base_states.clear()
        self.analyzed_count = 0
        self.files, self.catalog = [], []
        self.catalog_index = {}
        self.refresh_summary()
        self.export = None
        self.games.delete(*self.games.get_children())
        self.results = []
        self.render_grid()
        def work():
            files = sorted(p for p in roms.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS)
            self.events.put(("analysis_start", (files, export)))
            self.events.put(("log", f"{source}: preparando análisis de {len(files)} ROMs…"))
            candidates = (cached_catalog if cached_catalog is not None else libretro(system)) if source == "Libretro" or filter_platform else []
            index_by_title = index_candidates(candidates)
            if source == "Libretro" or filter_platform:
                self.events.put(("catalog", (system, candidates, index_by_title)))
            platform_titles = {normalized(c.name) for c in candidates} if filter_platform else None
            for index, rom in enumerate(files):
                if self.stop.is_set():
                    break
                self.events.put(("log", f"{source}: {index + 1}/{len(files)} · {rom.stem}"))
                try:
                    found = steamgriddb(rom.stem, key, platform_titles) if source == "SteamGridDB" else []
                    match = automatic_steamgriddb(rom.stem, found) if source == "SteamGridDB" else automatic(rom.stem, indexed_candidates(rom.stem, index_by_title), region)
                    state = "Ya existe" if export.existing(rom) else "Coincidencia" if match else "Elegir carátula" if found else "Buscar a mano"
                    self.events.put(("analysis_item", (index, found, state)))
                except Exception as error:
                    self.events.put(("analysis_item", (index, [], "Error")))
                    self.events.put(("log", f"{rom.name}: {error}"))
                self.events.put(("progress", 100 * (index + 1) / max(1, len(files))))
                if source != "Libretro" and self.stop.wait(0.5):
                    break
            self.events.put(("analysis_complete", None))
        self.task(work)

    def select_rom(self, *_):
        selected = self.games.selection()
        if selected:
            rom = self.selected_rom()
            if rom is None:
                self.write("Vuelve a analizar la biblioteca para usar los juegos de esta plataforma.")
                return
            self.query.set(rom.stem)
            found = self.suggestions.get(rom, [])
            if not found:
                pool = indexed_candidates(rom.stem, self.catalog_index) if self.catalog_index else self.catalog
                match = automatic(rom.stem, pool, self.region.get())
                found = [match] if match else search(rom.stem, self.catalog)[:10]
                self.suggestions[rom] = found
            self.show_results(rom, found)

    def show_results(self, rom, found):
        chosen = self.pending_covers.get(rom)
        existing = self.export.existing(rom) if self.export and rom else None
        first = ([chosen] if chosen else []) + ([Candidate(rom.stem, str(existing), "Imagen guardada")] if existing else [])
        self.results = []
        seen = set()
        for candidate in [*first, *found]:
            if candidate.url not in seen:
                seen.add(candidate.url)
                self.results.append(candidate)
        self.result_index = 0 if self.results else None
        self.result_page = 0
        self.preview_token += 1
        self.render_grid()
        if self.results:
            candidate = self.results[0]
            self.details.configure(text=f"{candidate.name}\n{candidate.source}")
        else:
            self.details.configure(text="Sin resultados. Prueba otro nombre o fuente.")
            self.art.configure(image="", text="Sin coincidencia\nBusca y selecciona una carátula")

    def image_data(self, candidate):
        if candidate.source in ("Imagen guardada", "Imagen local"):
            return Path(candidate.url).read_bytes()
        with self.image_lock:
            data = self.image_cache.get(candidate.url)
            if data is not None:
                self.image_cache.move_to_end(candidate.url)
                return data
            waiting = self.image_inflight.get(candidate.url)
            owner = waiting is None
            if owner:
                waiting = Future()
                self.image_inflight[candidate.url] = waiting
        if not owner:
            return waiting.result()
        try:
            data = fetch(candidate.url)
            with self.image_lock:
                self.image_cache[candidate.url] = data
                self.image_cache_size += len(data)
                while len(self.image_cache) > 120 or self.image_cache_size > 48 * 1024 * 1024:
                    _, removed = self.image_cache.popitem(last=False)
                    self.image_cache_size -= len(removed)
            waiting.set_result(data)
            return data
        except Exception as error:
            waiting.set_exception(error)
            raise
        finally:
            with self.image_lock:
                self.image_inflight.pop(candidate.url, None)

    def selected_rom(self):
        if self.library_system and self.library_system != SYSTEMS[self.platform_names[self.platform.get()]][0]:
            return None
        selected = self.games.selection()
        return self.files[int(selected[0])] if selected else None

    def selected_result(self):
        return self.results[self.result_index] if self.result_index is not None and self.result_index < len(self.results) else None

    def change_page(self, direction):
        self.result_page = max(0, min((len(self.results)-1)//self.page_size, self.result_page + direction))
        self.result_index = self.result_page * self.page_size if self.results else None
        self.render_grid()
        if self.result_index is not None:
            candidate = self.selected_result()
            self.details.configure(text=f"{candidate.name}\n{candidate.source}")

    def select_cover(self, index, toggle=True):
        self.result_index = index
        candidate = self.selected_result()
        rom = self.selected_rom()
        if rom and candidate:
            if toggle and self.pending_covers.get(rom) == candidate:
                self.pending_covers.pop(rom, None)
                self.result_index = None
                state = "Ya existe" if self.export and self.export.existing(rom) else self.base_states.get(rom, "Sin selección")
                self.games.set(str(self.files.index(rom)), "state", state)
            elif candidate.source == "Imagen guardada":
                self.pending_covers.pop(rom, None)
                self.games.set(str(self.files.index(rom)), "state", "Ya existe")
            else:
                self.pending_covers[rom] = candidate
                self.games.set(str(self.files.index(rom)), "state", "Seleccionada")
            self.refresh_summary()
        self.update_card_selection()
        if candidate is None:
            return
        rating = f" · Valoración: {candidate.score:g}" if candidate.score is not None else ""
        self.details.configure(text=f"{candidate.name}\n{candidate.source}{rating}")

    def refresh_summary(self):
        self.save_button.configure(text=f"Guardar seleccionadas ({len(self.pending_covers)})")
        self.summary.set(f"{len(self.files)} juegos · {self.analyzed_count} analizados\n{len(self.pending_covers)} carátulas pendientes de guardar")

    def update_card_selection(self):
        chosen = self.pending_covers.get(self.selected_rom())
        for index, card in self.cards.items():
            candidate = self.results[index]
            picked = candidate == chosen
            card.configure(highlightbackground=COLORS["green"] if picked else COLORS["blue"] if index == self.result_index else COLORS["border"])
            prefix = "Guardada · " if candidate.source == "Imagen guardada" else "Seleccionada · " if picked else ""
            self.card_captions[index].configure(text=prefix + candidate.name[:65])

    def render_grid(self):
        self.grid_token += 1
        token = self.grid_token
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.cards = {}
        self.card_captions = {}
        self.thumbnail_labels = {}
        self.thumbnail_images.clear()
        self.page_label.configure(text=f"{self.result_page+1} / {max(1, (len(self.results)+self.page_size-1)//self.page_size)} · {len(self.results)} imágenes")
        start = self.result_page * self.page_size
        visible = list(enumerate(self.results[start:start+self.page_size], start))
        if not visible:
            ttk.Label(self.grid_frame, text="Tu próxima portada empieza aquí\n\nAnaliza la biblioteca y selecciona un juego,\no busca un título en el campo de arriba.", style="MutedCard.TLabel", anchor="center", justify="center").place(relx=.5, rely=.5, anchor="center")
        for position, (index, candidate) in enumerate(visible):
            card = tk.Frame(self.grid_frame, bg=COLORS["field"], highlightthickness=2, highlightbackground=COLORS["border"], cursor="hand2")
            card.grid(row=position//3, column=position%3, sticky="nsew", padx=6, pady=6)
            card.pack_propagate(False)
            image = tk.Label(card, text="Cargando…", bg=COLORS["field"], fg=COLORS["muted"], cursor="hand2")
            image.pack(fill="both", expand=True, padx=8, pady=(8, 0))
            image.bind("<Configure>", lambda event, t=token, i=index: self.root.after_idle(self.fit_thumbnail, t, i))
            prefix = "Guardada · " if candidate.source == "Imagen guardada" else "Seleccionada · " if candidate == self.pending_covers.get(self.selected_rom()) else ""
            label = tk.Label(card, text=prefix + candidate.name[:65], wraplength=190, bg=COLORS["field"], fg=COLORS["text"], font=("Segoe UI", 9), height=2, cursor="hand2")
            label.pack(fill="x")
            for widget in (card, image, label):
                widget.bind("<Button-1>", lambda event, i=index: self.select_cover(i))
                widget.bind("<Double-Button-1>", lambda event, i=index: (self.select_cover(i, toggle=False), self.large_preview()))
            self.cards[index] = card
            self.card_captions[index] = label
            self.thumbnail_labels[index] = image
        self.update_card_selection()
        def load(items):
            for index, candidate in items:
                if token != self.grid_token:
                    return
                try:
                    data = self.image_data(candidate)
                    self.events.put(("thumbnail", (token, index, data)))
                except Exception:
                    self.events.put(("thumbnail_error", (token, index)))
        for offset in range(min(3, len(visible))):
            threading.Thread(target=load, args=(visible[offset::3],), daemon=True).start()

    def fit_thumbnail(self, token, index):
        if token != self.grid_token:
            return
        target = self.thumbnail_labels.get(index)
        if target is None or not target.winfo_exists() or not hasattr(target, "cover_data"):
            return
        width, height = target.winfo_width() - 4, target.winfo_height() - 4
        if width <= 1 or height <= 1 or getattr(target, "cover_size", None) == (width, height):
            return
        try:
            key = (self.results[index].url, width, height, hash(target.cover_data))
            image = self.thumbnail_cache.get(key)
            if image is None:
                image = self.make_image(target.cover_data, width, height)
                self.thumbnail_cache[key] = image
                if len(self.thumbnail_cache) > 96:
                    self.thumbnail_cache.popitem(last=False)
            else:
                self.thumbnail_cache.move_to_end(key)
            self.thumbnail_images[index] = image
            target.cover_size = (width, height)
            target.configure(image=image, text="")
        except (ValueError, OSError, tk.TclError):
            target.configure(text="Sin miniatura")

    def large_preview(self):
        candidate = self.selected_result()
        if not candidate:
            self.write("Selecciona una carátula para abrir Preview.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.title("Preview · " + candidate.name)
        dialog.geometry("640x700")
        dialog.transient(self.root)
        candidates = list(self.results)
        dialog.preview_index = self.result_index
        dialog.preview_token = 0
        label = ttk.Label(dialog, text="Cargando…", anchor="center", style="Preview.TLabel")
        label.pack(fill="both", expand=True, padx=12, pady=12)
        controls = ttk.Frame(dialog)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        controls.columnconfigure(0, weight=1, uniform="preview_sides")
        controls.columnconfigure(4, weight=1, uniform="preview_sides")
        previous = ttk.Button(controls, text="‹", width=2, style="Arrow.TButton", command=lambda: show(dialog.preview_index - 1))
        previous.grid(row=0, column=1)
        position = ttk.Label(controls, anchor="center", width=9)
        position.grid(row=0, column=2, padx=8)
        following = ttk.Button(controls, text="›", width=2, style="Arrow.TButton", command=lambda: show(dialog.preview_index + 1))
        following.grid(row=0, column=3)
        ttk.Button(controls, text="Cerrar", command=dialog.destroy).grid(row=0, column=4, sticky="e")
        def show(index):
            if not 0 <= index < len(candidates):
                return
            dialog.preview_index = index
            dialog.preview_token += 1
            token = dialog.preview_token
            current = candidates[index]
            dialog.title("Preview · " + current.name)
            position.configure(text=f"{index + 1} / {len(candidates)}")
            previous.configure(state="normal" if index else "disabled")
            following.configure(state="normal" if index + 1 < len(candidates) else "disabled")
            label.configure(image="", text="Cargando…")
            label.image = None
            def load():
                try:
                    data = self.image_data(current)
                except Exception:
                    data = None
                self.events.put(("large_preview", (dialog, label, token, data)))
            threading.Thread(target=load, daemon=True).start()
        dialog.bind("<Left>", lambda event: (show(dialog.preview_index - 1), "break")[1])
        dialog.bind("<Right>", lambda event: (show(dialog.preview_index + 1), "break")[1])
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        self.center_dialog(dialog)
        dialog.deiconify()
        dialog.focus_set()
        show(dialog.preview_index)
        return dialog

    def batch(self):
        if not self.export:
            self.write("Analiza primero la biblioteca.")
            return
        files, candidates, export = list(self.files), list(self.catalog), self.export
        region = self.region.get()
        suggestions = dict(self.suggestions)
        catalog_index = self.catalog_index
        source = self.active_analysis_source
        def work():
            for index, rom in enumerate(files):
                if self.stop.is_set():
                    break
                match = automatic_steamgriddb(rom.stem, suggestions.get(rom, [])) if source == "SteamGridDB" else automatic(rom.stem, indexed_candidates(rom.stem, catalog_index) if catalog_index else candidates, region)
                if not match:
                    continue
                try:
                    export.save(rom, match, fetch(match.url) if not export.existing(rom) else b"\x89PNG\r\n\x1a\n")
                    self.events.put(("state", (index, "Guardada")))
                except Exception as error:
                    self.events.put(("state", (index, "Error")))
                    self.events.put(("log", f"{rom.name}: {error}"))
                if self.stop.wait(0.5):
                    break
        self.task(work)

    def find(self):
        if self.busy:
            return
        query, source = self.query.get().strip(), self.source.get()
        key = self.api_key.get()
        platform, region = self.platform_names[self.platform.get()], self.region.get()
        rom = self.selected_rom()
        system = SYSTEMS[platform][0]
        cached = self.libretro_catalogs.get(system)
        filter_platform = self.platform_filter.get() == "Sí"
        if query:
            def work():
                if source == "Libretro":
                    candidates = cached if cached is not None else libretro(system)
                    self.events.put(("catalog", (system, candidates)))
                    found = search(query, candidates)
                else:
                    candidates = (cached if cached is not None else libretro(system)) if filter_platform else []
                    if filter_platform:
                        self.events.put(("catalog", (system, candidates)))
                    found = steamgriddb(query, key, {normalized(c.name) for c in candidates} if filter_platform else None)
                self.events.put(("results", (rom, found, system)))
                if source == "SteamGridDB" and filter_platform and not found:
                    self.events.put(("log", "Sin resultados con el filtro de consola. Puedes desactivarlo en Configuración para buscar fuera del catálogo."))
            self.task(work)

    def preview(self, *_):
        candidate = self.selected_result()
        if candidate:
            self.request_preview(candidate)

    def request_preview(self, candidate, local=False):
        self.preview_token += 1
        token = self.preview_token
        rating = f" · Valoración: {candidate.score:g}" if candidate.score is not None else ""
        self.details.configure(text=candidate.source + rating)
        self.art.configure(image="", text="Cargando carátula…")
        def work():
            try:
                data = Path(candidate.url).read_bytes() if local else self.image_data(candidate)
                self.events.put(("preview", (token, data)))
            except Exception:
                self.events.put(("preview_error", token))
        threading.Thread(target=work, daemon=True).start()

    def make_image(self, data, width, height):
        try:
            from PySide6.QtGui import QImage
            from PySide6.QtCore import QBuffer, QIODevice, Qt
            image = QImage.fromData(data)
            if image.isNull():
                raise ValueError("Imagen no válida")
            image = image.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            image.save(buffer, "PNG")
            result = tk.PhotoImage(data=bytes(buffer.data()))
        except ImportError:
            try:
                from PIL import Image, ImageTk
                image = Image.open(io.BytesIO(data))
                factor = min(width / image.width, height / image.height)
                image = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))), Image.Resampling.LANCZOS)
                result = ImageTk.PhotoImage(image)
            except ImportError:
                image = tk.PhotoImage(data=data)
                factor = max(1, (image.width()+width-1)//width, (image.height()+height-1)//height)
                result = image.subsample(factor)
        return result

    def show_image(self, data):
        self.image = self.make_image(data, 330, 170)
        self.art.configure(image=self.image, text="")

    def use(self):
        if self.busy:
            return
        if not self.pending_covers or not self.export:
            self.write("Haz clic en las carátulas que quieras guardar, una por juego.")
            return
        export = self.export
        choices = [(self.files.index(rom), rom, candidate) for rom, candidate in self.pending_covers.items()]
        def work():
            saved = 0
            for index, rom, candidate in choices:
                if self.stop.is_set():
                    break
                try:
                    export.save(rom, candidate, self.image_data(candidate))
                    self.events.put(("cover_saved", (index, candidate)))
                    saved += 1
                except Exception as error:
                    self.events.put(("state", (index, "Error")))
                    self.events.put(("log", f"{rom.name}: {error}"))
            self.events.put(("log", f"{saved}/{len(choices)} carátulas guardadas. Las restantes siguen seleccionadas."))
        self.task(work)

    def local(self):
        rom = self.selected_rom()
        if not rom or not self.export:
            self.write("Selecciona una ROM.")
            return
        path = filedialog.askopenfilename(filetypes=[("Imágenes", "*.png *.jpg *.jpeg")])
        if path:
            export, index = self.export, self.files.index(rom)
            def work():
                export.save(rom, Candidate(rom.stem, path, "Imagen local"), Path(path).read_bytes())
                self.events.put(("state", (index, "Guardada")))
            self.task(work)

    def open_source(self):
        candidate = self.selected_result()
        if candidate and candidate.page.startswith("https://"):
            webbrowser.open(candidate.page)

    def poll(self):
        while not self.events.empty():
            event, value = self.events.get()
            if event == "done":
                if self.analysis_running and self.stop.is_set():
                    self.write("Análisis cancelado.")
                self.analysis_running = False
                self.busy = False
                self.stop_analysis_button.configure(state="disabled")
                for button in self.buttons:
                    button.configure(state="normal")
            elif event == "log":
                self.write(value)
            elif event == "progress":
                self.set_progress(value)
            elif event == "analysis_start":
                self.files, self.export = value
                for index, rom in enumerate(self.files):
                    self.games.insert("", "end", iid=str(index), text=rom.name, values=("Pendiente",), tags=("pending",))
                self.refresh_summary()
                self.workspace_tabs.select(self.gallery_tab)
            elif event == "catalog":
                system, candidates = value[:2]
                indexed = value[2] if len(value) > 2 else index_candidates(candidates)
                self.libretro_catalogs[system] = candidates
                self.libretro_indexes[system] = indexed
                if self.library_system is None or system == self.library_system:
                    self.catalog = candidates
                    self.catalog_index = indexed
            elif event == "analysis_item":
                index, found, state = value
                rom = self.files[index]
                self.suggestions[rom] = found
                self.base_states[rom] = state
                self.analyzed_count += 1
                if rom not in self.pending_covers:
                    self.games.set(str(index), "state", state)
                    self.games.item(str(index), tags=("error" if state == "Error" else "pending" if state in ("Buscar a mano", "Elegir carátula") else "ready",))
                if self.selected_rom() == rom:
                    self.select_rom()
                self.refresh_summary()
            elif event == "analysis_complete":
                self.write(f"{len(self.files)} ROMs · Fuente: {self.active_analysis_source}. Configuración fijada hasta el próximo análisis.")
                if not self.stop.is_set():
                    self.set_progress(100)
            elif event == "cover_saved":
                index, candidate = value
                rom = self.files[index]
                if self.pending_covers.get(rom) == candidate:
                    del self.pending_covers[rom]
                    self.games.set(str(index), "state", "Guardada")
                    self.games.item(str(index), tags=("ready",))
                self.refresh_summary()
                if self.selected_rom() == rom:
                    self.select_rom()
            elif event == "state":
                self.games.set(str(value[0]), "state", value[1])
                self.games.item(str(value[0]), tags=("error" if value[1] == "Error" else "ready",))
                self.status.set(f"{self.files[value[0]].name}: {value[1]}")
                if value[1] == "Guardada" and self.selected_rom() == self.files[value[0]]:
                    self.select_rom()
            elif event == "results":
                rom, found = value[:2]
                if len(value) > 2 and value[2] != SYSTEMS[self.platform_names[self.platform.get()]][0]:
                    continue
                if rom:
                    self.suggestions[rom] = found
                if self.selected_rom() != rom:
                    self.write("Resultados disponibles en el juego que buscaste.")
                    continue
                self.show_results(rom, found)
                self.write(f"{len(found)} resultados. Haz clic en una portada; puedes guardar todas las seleccionadas juntas.")
            elif event == "thumbnail" and value[0] == self.grid_token:
                target = self.thumbnail_labels[value[1]]
                target.cover_data = value[2]
                self.root.after_idle(self.fit_thumbnail, value[0], value[1])
            elif event == "thumbnail_error" and value[0] == self.grid_token:
                self.thumbnail_labels[value[1]].configure(text="Sin miniatura")
            elif event == "large_preview":
                dialog, label, token, data = value
                if dialog.winfo_exists() and token == dialog.preview_token:
                    try:
                        label.image = self.make_image(data, 600, 600) if data else None
                        label.configure(image=label.image or "", text="" if data else "No se pudo cargar la imagen")
                    except (ValueError, OSError, tk.TclError):
                        label.configure(text="No se pudo mostrar la imagen")
            elif event == "preview_error" and value == self.preview_token:
                self.art.configure(image="", text="No se pudo cargar la imagen")
            elif event == "preview" and value[0] == self.preview_token:
                try:
                    self.show_image(value[1])
                except (tk.TclError, ValueError, OSError):
                    self.art.configure(image="", text="Vista previa no disponible; pulsa Ver fuente")
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
