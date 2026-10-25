from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QAction, QColor, QKeySequence, QPalette, QShortcut, QFont, QFontMetrics
from PySide6.QtWidgets import (QDockWidget, QLabel, QMainWindow, QStackedWidget,
                               QVBoxLayout, QWidget, QTableView, QProgressBar,
                               QHBoxLayout, QPushButton, QLineEdit, QHeaderView,
                               QAbstractItemView, QApplication, QDialog, QDialogButtonBox,
                               QPlainTextEdit, QGroupBox, QToolButton, QStyle, QSizePolicy, QCheckBox)

from romkit_studio.models.session import SessionModel, SessionState
from romkit_studio.models.candidate_table_model import CandidateTableModel, CandidateFilterModel
from romkit_core.icons import application_icon
from romkit_core import __version__
from romkit_core.adapters.registry import enabled_adapters, profile
from romkit_core.ui_styles import BUTTON_STYLES
from romkit_studio.services import StudioServices
from romkit_studio.widgets.log_panel import LogPanel
from romkit_studio.widgets.start_page import StartPage


class MainWindow(QMainWindow):
    open_image_requested = Signal()
    extract_requested = Signal()
    analyze_requested = Signal()
    create_project_requested = Signal()
    import_translation_requested = Signal()
    export_images_requested = Signal()
    import_images_requested = Signal()
    create_delta_requested = Signal()

    def __init__(self, *, session: SessionModel | None = None, services: StudioServices | None = None):
        super().__init__()
        self.setWindowTitle("ROMKit Studio")
        if profile() != 'all':
            self.setWindowTitle('ROMKit Studio · ' + profile().title())
        self.setWindowTitle(self.windowTitle() + ' · v' + __version__)
        self.setWindowIcon(application_icon(profile() if profile() in ('digimon', 'pokapoka') else 'studio'))
        self.setFixedSize(1120, 740)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        # The stylesheet uses light surfaces. Set matching palette roles before
        # creating children so a dark OS theme cannot supply white foregrounds.
        palette = QPalette(self.palette())
        for role, color in {
            QPalette.ColorRole.Window: "#f5f7fa",
            QPalette.ColorRole.WindowText: "#172b4d",
            QPalette.ColorRole.Base: "#ffffff",
            QPalette.ColorRole.AlternateBase: "#f0f4f8",
            QPalette.ColorRole.Text: "#172b4d",
            QPalette.ColorRole.Button: "#eaf0f6",
            QPalette.ColorRole.ButtonText: "#172b4d",
            QPalette.ColorRole.ToolTipBase: "#ffffff",
            QPalette.ColorRole.ToolTipText: "#172b4d",
            QPalette.ColorRole.Highlight: "#2563eb",
            QPalette.ColorRole.HighlightedText: "#ffffff",
            QPalette.ColorRole.PlaceholderText: "#617087",
        }.items():
            palette.setColor(role, QColor(color))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#617087"))
        self.setPalette(palette)
        self.session = session if session is not None else SessionModel(self)
        self.services = services if services is not None else StudioServices()
        self._displayed_resources = ()
        self._displayed_candidates = ()

        self.open_action = QAction("Abrir ROM/ISO…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_image_requested.emit)
        self.close_image_action = QAction("Cerrar imagen", self)
        self.close_image_action.triggered.connect(self.session.clear)
        self.extract_action = QAction("Extraer archivos", self)
        self.extract_action.setToolTip("Extraer los archivos de la imagen a la carpeta de trabajo")
        self.extract_action.triggered.connect(self.extract_requested.emit)
        self.analyze_action = QAction("Buscar textos", self)
        self.analyze_action.triggered.connect(self.analyze_requested.emit)
        self.export_images_action = QAction("Buscar y extraer imágenes…", self)
        self.export_images_action.setToolTip("Abrir BND, ZIP, zlib/gzip y ARCV; convertir texturas PSP GIM y GMIO a PNG, además de imágenes comunes")
        self.export_images_action.triggered.connect(self.export_images_requested.emit)
        self.import_images_action = QAction("Importar imágenes…", self)
        self.import_images_action.setToolTip("Reinsertar PNG editados de una exportación con imagenes.json y crear una ISO nueva")
        self.import_images_action.triggered.connect(self.import_images_requested.emit)
        self.create_project_action = QAction("Exportar textos…", self)
        self.create_project_action.setToolTip("Guardar los textos seleccionados como proyecto para ROMKit Translator")
        self.create_project_action.triggered.connect(self.create_project_requested.emit)
        self.import_translation_action = QAction("Importar traducción…", self)
        self.import_translation_action.setToolTip("Abrir el proyecto guardado en Translator y generar una ISO nueva")
        self.import_translation_action.triggered.connect(self.import_translation_requested.emit)
        self.create_delta_action = QAction('Crear parche delta…', self)
        self.create_delta_action.setIcon(application_icon('export-text'))
        self.create_delta_action.triggered.connect(self.create_delta_requested.emit)
        exit_action = QAction("Salir", self)
        exit_action.setIcon(application_icon("exit"))
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("Archivo")
        file_menu.addActions([self.open_action, self.close_image_action])
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        tools_menu = self.menuBar().addMenu("Herramientas")
        tools_menu.addActions([self.extract_action, self.analyze_action, self.export_images_action, self.import_images_action,
                               self.create_project_action, self.import_translation_action, self.create_delta_action])
        self.pages = QStackedWidget()
        self.start_page = StartPage(self.open_action)
        self.pages.addWidget(self.start_page)
        self.image_page = QWidget()
        self.image_page.setObjectName("imagePage")
        layout = QVBoxLayout(self.image_page)
        layout.setContentsMargins(16, 12, 16, 12)
        heading = QHBoxLayout()
        self.image_name = QLabel()
        self.image_name.setObjectName("imageName")
        self.image_name.setWordWrap(True)
        self.image_name.setTextFormat(Qt.TextFormat.PlainText)
        self.image_details = QLabel(self.image_page)
        self.image_details.setPalette(palette)
        self.image_details.setWordWrap(True)
        self.image_details.setTextFormat(Qt.TextFormat.PlainText)
        self.image_details.hide()
        heading.addWidget(self.image_name, 1)
        self.info_button = QPushButton("i")
        self.info_button.setObjectName("infoButton")
        self.info_button.setFixedSize(30, 30)
        self.info_button.setAccessibleName("Información de la imagen y del texto seleccionado")
        self.info_button.setToolTip("Información de la imagen, del archivo y del texto seleccionado")
        self.info_button.clicked.connect(self._show_information)
        heading.addWidget(self.info_button)
        layout.addLayout(heading)
        self.adapter_label = QLabel()
        self.adapter_label.setTextFormat(Qt.TextFormat.PlainText)
        self.adapter_label.setWordWrap(True)
        layout.addWidget(self.adapter_label)
        hint = QLabel("Selecciona filas con clic, Ctrl o Mayús. Espacio marca o desmarca; las casillas indican qué se exportará.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.candidate_model = CandidateTableModel(self)
        self.candidate_proxy = CandidateFilterModel(self)
        self.candidate_proxy.setSourceModel(self.candidate_model)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar texto, archivo o codificación…")
        self.search_input.setAccessibleName("Buscar textos")
        self.search_input.setClearButtonEnabled(True)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_input.textChanged.connect(lambda: self.search_timer.start())
        self.search_timer.timeout.connect(self._apply_search)
        self.search_input.returnPressed.connect(self._apply_search)
        layout.addWidget(self.search_input)
        self.candidate_table = QTableView()
        self.candidate_table.setModel(self.candidate_proxy)
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.candidate_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.candidate_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.candidate_table.setAlternatingRowColors(True)
        self.candidate_table.setWordWrap(False)
        self.candidate_table.verticalHeader().hide()
        self.candidate_table.setColumnWidth(0, 65)
        self.candidate_table.setColumnWidth(2, 220)
        self.candidate_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.candidate_table.setColumnHidden(3, True)
        self.candidate_table.setColumnHidden(4, True)
        self.candidate_table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.copy_action = QAction("Copiar texto", self.candidate_table)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.copy_action.triggered.connect(self._copy_texts)
        self.candidate_table.addAction(self.copy_action)
        self.mark_action = QAction("Marcar selección", self.candidate_table)
        self.mark_action.triggered.connect(self._mark_selection)
        self.candidate_table.addAction(self.mark_action)
        self.unmark_action = QAction("Desmarcar selección", self.candidate_table)
        self.unmark_action.triggered.connect(self._unmark_selection)
        self.candidate_table.addAction(self.unmark_action)
        self.remove_action = QAction("Quitar de la lista", self.candidate_table)
        self.remove_action.triggered.connect(self._remove_selection)
        self.candidate_table.addAction(self.remove_action)
        self.restore_action = QAction("Restaurar última eliminación", self.candidate_table)
        self.restore_action.triggered.connect(self.candidate_model.restore_removal)
        self.candidate_table.addAction(self.restore_action)
        # Keep shortcut labels out of the context menu's text column.
        self.toggle_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self.candidate_table)
        self.toggle_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.toggle_shortcut.setAutoRepeat(False)
        self.toggle_shortcut.activated.connect(self._toggle_selection)
        self.remove_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self.candidate_table)
        self.remove_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.remove_shortcut.activated.connect(self._remove_selection)
        self.restore_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self.candidate_table)
        self.restore_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.restore_shortcut.activated.connect(self.candidate_model.restore_removal)
        self.candidate_table.selectionModel().selectionChanged.connect(self._update_create_action)
        selection_bar = QHBoxLayout()
        self.mark_selection_button = QPushButton("Marcar selección")
        self.mark_selection_button.clicked.connect(self._mark_selection)
        self.mark_selection_button.setToolTip("Marcar las filas seleccionadas. Espacio alterna sus marcas")
        self.unmark_selection_button = QPushButton("Desmarcar selección")
        self.unmark_selection_button.clicked.connect(self._unmark_selection)
        self.remove_selection_button = QPushButton("Quitar de la lista")
        self.remove_selection_button.setToolTip("Quitar solo de esta lista. Ctrl+Z restaura la última eliminación; no se modifica el juego")
        self.remove_selection_button.clicked.connect(self._remove_selection)
        self.select_texts_button = QPushButton("Marcar resultados")
        self.select_texts_button.setToolTip("Marca los resultados de la búsqueda, evitando duplicados que ocupen los mismos bytes")
        self.select_texts_button.clicked.connect(self._mark_results)
        self.clear_texts_button = QPushButton("Desmarcar todo")
        self.clear_texts_button.clicked.connect(self.candidate_model.clear_confirmation)
        self.selection_count = QLabel()
        self.export_texts_button = QPushButton("Exportar marcados…")
        self.export_texts_button.setObjectName("primaryButton")
        export_font = QFont(self.export_texts_button.font())
        export_font.setWeight(QFont.Weight.DemiBold)
        self.export_texts_button.setMinimumWidth(QFontMetrics(export_font).horizontalAdvance(self.export_texts_button.text()) + 48)
        self.export_texts_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.export_texts_button.clicked.connect(self.create_project_action.trigger)
        selection_bar.addWidget(self.mark_selection_button)
        selection_bar.addWidget(self.unmark_selection_button)
        selection_bar.addWidget(self.remove_selection_button)
        selection_bar.addStretch()
        layout.addLayout(selection_bar)
        export_bar = QHBoxLayout()
        export_bar.addWidget(self.select_texts_button)
        export_bar.addWidget(self.clear_texts_button)
        export_bar.addStretch()
        export_bar.addWidget(self.export_texts_button)
        layout.addLayout(export_bar)
        layout.addWidget(self.selection_count)
        layout.addWidget(self.candidate_table, 1)
        self.candidate_model.confirmation_changed.connect(self._update_create_action)
        self.pages.addWidget(self.image_page)
        self.setCentralWidget(self.pages)

        resource_panel = QWidget()
        resource_layout = QVBoxLayout(resource_panel)
        resource_layout.setContentsMargins(10, 10, 10, 10)
        self.workflow_buttons = {}
        for title, actions in (
            ("1 · Extraer textos", (
                (self.open_action, "open-rom"),
                (self.extract_action, "extract"),
                (self.analyze_action, "search-text"))),
            ("2 · Aplicar traducción", (
                (self.import_translation_action, "import-translation"),)),
            ("Imágenes", (
                (self.export_images_action, "search-images"),
                (self.import_images_action, "import-translation"),)),
            ("3 · Compartir", ((self.create_delta_action, "export-text"),)),
        ):
            group = QGroupBox(title)
            group_layout = QVBoxLayout(group)
            for action, icon in actions:
                action.setIcon(application_icon(icon))
                button = QToolButton()
                button.setObjectName("workflowButton")
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setDefaultAction(action)
                button.setIconSize(QSize(24, 24))
                button.setMinimumHeight(38)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                group_layout.addWidget(button)
                self.workflow_buttons[action] = button
            if title.startswith("2"):
                self.experimental_reinsert = QCheckBox("Pruebas: textos más largos")
                self.experimental_reinsert.setToolTip("Digimon BTX: redistribuir el espacio entre cadenas de una tabla. Rechaza bloques que no caben; no trunca textos ni sobrescribe otros recursos. Probar en emulador.")
                group_layout.addWidget(self.experimental_reinsert)
                description = QLabel("Proyecto de Translator → ISO nueva")
                description.setWordWrap(True)
                group_layout.addWidget(description)
            resource_layout.addWidget(group)
        for widget, name in (
            (self.close_image_action, "close"), (self.create_project_action, "export-text"),
            (self.copy_action, "copy"), (self.mark_action, "mark"), (self.unmark_action, "unmark"),
            (self.remove_action, "remove"), (self.restore_action, "restore"),
            (self.mark_selection_button, "mark"), (self.unmark_selection_button, "unmark"),
            (self.remove_selection_button, "remove"), (self.select_texts_button, "mark"),
            (self.clear_texts_button, "unmark"), (self.export_texts_button, "export-text"),
            (self.info_button, "info"), (self.start_page.open_button, "open-rom"),
        ):
            widget.setIcon(application_icon(name))
        self.info_button.setText("")
        resource_layout.addStretch(1)
        self.resources_dock = QDockWidget("Acciones", self)
        self.resources_dock.setObjectName("resourcesDock")
        self.resources_dock.setWidget(resource_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.resources_dock)
        self.log_panel = LogPanel()
        self.activity_dock = QDockWidget("Actividad", self)
        self.activity_dock.setObjectName("activityDock")
        self.activity_dock.setWidget(self.log_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.activity_dock)
        self.resizeDocks([self.resources_dock], [280], Qt.Orientation.Horizontal)
        self.resizeDocks([self.activity_dock], [150], Qt.Orientation.Vertical)
        for dock in (self.resources_dock, self.activity_dock):
            dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            dock.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(160)
        self.progress_bar.setValue(0)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.setStyleSheet("""
            QWidget { color: #172b4d; }
            QWidget:disabled { color: #617087; }
            QMainWindow, QDialog, QWidget#startPage, QWidget#imagePage { background: #f5f7fa; color: #172b4d; }
            QMenuBar, QMenu { background: #ffffff; color: #172b4d; }
            QMenuBar::item:selected, QMenu::item:selected { background: #2563eb; color: #ffffff; }
            QMenu::item:disabled { color: #617087; }
            QMenu::item { padding: 8px 44px 8px 12px; }
            QToolBar { spacing: 8px; padding: 8px; background: #ffffff; border-bottom: 1px solid #dce2ea; }
            QDockWidget::title { background: #eaf0f6; padding: 8px; font-weight: 600; }
            QTreeView, QTableView, QPlainTextEdit { background: #ffffff; color: #172b4d; border: 1px solid #dce2ea; }
            QHeaderView::section { background: #eaf0f6; color: #172b4d; padding: 4px; border: none; }
            QLabel#eyebrow { color: #3663a0; font-weight: 600; font-size: 12px; }
            QLabel#welcomeTitle { color: #172b4d; font-size: 32px; font-weight: 600; }
            QLabel#welcomeDescription { color: #52657d; font-size: 14px; }
            QLabel#welcomeHint { color: #617087; font-size: 12px; }
            QLabel#imageName { font-size: 24px; font-weight: 600; }
            QLineEdit, QComboBox { background: #ffffff; color: #172b4d; border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px; }
            QGroupBox { border: 1px solid #cbd5e1; border-radius: 8px; margin-top: 12px; padding-top: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QToolButton#workflowButton { text-align: left; }
            QPushButton#infoButton { border: 1px solid #94a3b8; border-radius: 15px; padding: 0; font-weight: bold; color: #2563eb; background: #ffffff; }
            QStatusBar { background: #ffffff; color: #52657d; }
        """ + BUTTON_STYLES)
        self.session.changed.connect(self._apply_session)
        self._apply_session(self.session.state)

    @Slot(object)
    def _apply_session(self, state: SessionState) -> None:
        self.open_action.setEnabled(not state.busy)
        self.start_page.open_button.setEnabled(not state.busy)
        self.close_image_action.setEnabled(state.has_image and not state.busy)
        self.extract_action.setEnabled(state.has_image and state.workspace is not None and not state.busy and not state.resources)
        self.analyze_action.setEnabled(bool(state.resources) and not state.busy)
        self.export_images_action.setEnabled(bool(state.resources) and state.workspace is not None and not state.busy)
        self.import_images_action.setEnabled(state.has_image and state.workspace is not None and not state.busy)
        self.import_translation_action.setEnabled(state.has_image and state.workspace is not None and not state.busy and bool(enabled_adapters()))
        paths = {r.logical_path for r in state.resources}
        can_repack = any(a.id == 'digimon' and a.matches(paths) for a in enabled_adapters())
        self.experimental_reinsert.setEnabled(not state.busy and can_repack)
        if not can_repack:
            self.experimental_reinsert.setChecked(False)
        self.create_delta_action.setEnabled(state.has_image and not state.busy)
        if state.resources != self._displayed_resources:
            self._displayed_resources = state.resources
        if state.candidates is not self._displayed_candidates:
            self._displayed_candidates = state.candidates
            self.candidate_model.set_candidates(state.candidates)
        self._update_create_action()
        if state.image is None:
            self.pages.setCurrentWidget(self.start_page)
            self.statusBar().showMessage("Listo · Sin imagen abierta")
        else:
            image = state.image
            self.image_name.setText(image.path.name)
            paths = {r.logical_path for r in state.resources}
            detected = [a.title for a in enabled_adapters() if a.matches(paths)]
            self.adapter_label.setText('Adaptador: ' + (' · '.join(detected) + ' · Extraer / importar textos'
                if detected else 'Base genérica · Extrae archivos para detectar el juego'))
            platform = image.selected_platform or image.detected_platform or "Sin seleccionar"
            self.image_details.setText(f"{image.size_bytes:,} bytes · Plataforma: {platform}\n{image.path}\nSHA-256: {image.sha256}")
            self.pages.setCurrentWidget(self.image_page)
            self.statusBar().showMessage(f"Imagen abierta · {image.path.name}")

    @Slot()
    def _update_create_action(self):
        if not hasattr(self, "export_texts_button"):
            return
        selected = len(self.candidate_model.checked)
        total = len(self.candidate_model.candidates)
        busy = self.session.state.busy
        self.create_project_action.setEnabled(bool(selected) and not busy)
        self.export_texts_button.setEnabled(self.create_project_action.isEnabled())
        self.select_texts_button.setEnabled(bool(total) and not busy)
        self.clear_texts_button.setEnabled(bool(selected) and not busy)
        highlighted = bool(self.candidate_table.selectionModel().selectedRows())
        self.mark_selection_button.setEnabled(highlighted and not busy)
        self.mark_action.setEnabled(highlighted and not busy)
        self.unmark_selection_button.setEnabled(highlighted and not busy)
        self.unmark_action.setEnabled(highlighted and not busy)
        self.remove_selection_button.setEnabled(highlighted and not busy)
        self.remove_action.setEnabled(highlighted and not busy)
        self.restore_action.setEnabled(self.candidate_model.can_restore_removal and not busy)
        self.toggle_shortcut.setEnabled(highlighted and not busy)
        self.remove_shortcut.setEnabled(highlighted and not busy)
        self.restore_shortcut.setEnabled(self.candidate_model.can_restore_removal and not busy)
        self.copy_action.setEnabled(highlighted)
        self.search_input.setEnabled(not busy)
        self.candidate_table.setEnabled(not busy)
        visible = self.candidate_proxy.rowCount()
        self.select_texts_button.setEnabled(bool(visible) and not busy)
        self.selection_count.setText(f"{visible:,} resultados de {total:,} textos · {selected:,} marcados para exportar")

    def _apply_search(self):
        self.search_timer.stop()
        self.candidate_proxy.setFilterFixedString(self.search_input.text().strip())
        self._update_create_action()

    def _selected_source_rows(self):
        return sorted(self.candidate_proxy.mapToSource(index).row()
                      for index in self.candidate_table.selectionModel().selectedRows())

    def _mark_selection(self):
        self.candidate_model.select_compatible(self._selected_source_rows(), add=True)

    def _unmark_selection(self):
        self.candidate_model.uncheck_rows(self._selected_source_rows())

    def _toggle_selection(self):
        rows = self._selected_source_rows()
        if rows and all(row in self.candidate_model.checked for row in rows):
            self.candidate_model.uncheck_rows(rows)
        else:
            self.candidate_model.select_compatible(rows, add=True)

    def _remove_selection(self):
        self.candidate_model.remove_rows(self._selected_source_rows())
        self.candidate_table.setFocus(Qt.FocusReason.OtherFocusReason)

    def _mark_results(self):
        self._apply_search()
        rows = [self.candidate_proxy.mapToSource(self.candidate_proxy.index(row, 0)).row()
                for row in range(self.candidate_proxy.rowCount())]
        self.candidate_model.select_compatible(rows, add=True)

    def _copy_texts(self):
        QApplication.clipboard().setText("\n".join(self.candidate_model.candidates[row].text
                                                   for row in self._selected_source_rows()))

    def _show_information(self):
        dialog = QDialog(self)
        dialog.setPalette(QPalette(self.palette()))
        dialog.setAutoFillBackground(True)
        dialog.setStyleSheet("""
            QDialog { background: #f5f7fa; color: #172b4d; }
            QPlainTextEdit { background: #ffffff; color: #172b4d; border: 1px solid #cbd5e1; }
        """ + BUTTON_STYLES)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("Información")
        dialog.setFixedSize(640, 460)
        layout = QVBoxLayout(dialog)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        sections = [self.image_name.text(), self.image_details.text()]
        current = self.candidate_table.currentIndex()
        if current.isValid():
            candidate = self.candidate_model.candidates[self.candidate_proxy.mapToSource(current).row()]
            sections.append(f"TEXTO SELECCIONADO\n{candidate.text}\n\n{candidate.logical_path}\n"
                            f"Codificación: {candidate.encoding} · Confianza: {candidate.confidence:.0%}\n"
                            f"Offset: {candidate.offset} · {candidate.length_bytes} bytes\n" + "\n".join(candidate.evidence))
        details.setPlainText("\n\n".join(sections))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        self.information_dialog = dialog
        dialog.open()

    def closeEvent(self, event):
        controller = getattr(self, "controller", None)
        if controller is not None and not controller.request_close():
            event.ignore()
        else:
            event.accept()
