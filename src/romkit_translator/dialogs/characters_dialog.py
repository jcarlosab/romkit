import unicodedata
from PySide6.QtCore import Qt,Signal,Slot
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,
    QTableWidgetItem,QLineEdit,QPushButton,QHeaderView,QProgressBar)

from romkit_core.icons import application_icon
from romkit_core.project.characters import inspect_characters,plan_substitutions
from romkit_core.qt_tasks import TaskRunner
from romkit_core.ui_styles import BUTTON_STYLES


class CharactersDialog(QDialog):
    applied=Signal(object)

    def __init__(self,units,parent=None):
        super().__init__(parent)
        self.units=tuple(units);self.plan=None;self.editors={};self._job=None;self._closing=None
        self.setWindowTitle('Caracteres especiales · Translator')
        self.setWindowIcon(application_icon('special-characters'))
        self.setFixedSize(960,680)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setStyleSheet('QWidget {background:#f5f7fa;color:#172b4d;} QLineEdit,QTableView {background:white;color:#172b4d;border:1px solid #94a3b8;} QHeaderView::section {background:#eaf0f6;padding:6px;} QTableView {selection-background-color:#2563eb;selection-color:white;}'+BUTTON_STYLES)
        layout=QVBoxLayout(self)
        intro=QLabel('Asigna sustituciones para todas las traducciones con texto del proyecto, también las pendientes.\nLos originales, las variables y los iconos de control se conservan. Los textos modificados pierden la marca Revisada.')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.table=QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(['Carácter','Unicode','Usos','Textos','Compatibilidad','Sustituir por'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        for column,width in enumerate((72,100,60,65,230)):self.table.setColumnWidth(column,width)
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,3)
        help_text=QLabel('Un campo vacío elimina ese carácter. Los cambios no se encadenan: á → ñ y ñ → n produce ñ y n, respectivamente.')
        help_text.setWordWrap(True);layout.addWidget(help_text)
        self.summary=QLabel('Buscando caracteres…');self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.preview_table=QTableWidget(0,3)
        self.preview_table.setHorizontalHeaderLabels(['ID','Antes','Después'])
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.preview_table,2)
        self.progress=QProgressBar();layout.addWidget(self.progress)
        buttons=QHBoxLayout()
        self.preview_button=QPushButton('Previsualizar')
        self.apply_button=QPushButton('Aplicar a traducciones');self.apply_button.setObjectName('primaryButton')
        self.cancel_button=QPushButton('Cerrar')
        buttons.addWidget(self.preview_button);buttons.addStretch();buttons.addWidget(self.apply_button);buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.runner=TaskRunner(self)
        self.runner.result.connect(self._result);self.runner.error.connect(self._error)
        self.runner.progress.connect(self._progress);self.runner.finished.connect(self._finished)
        self.preview_button.clicked.connect(self.preview)
        self.apply_button.clicked.connect(self._apply);self.cancel_button.clicked.connect(self.reject)
        self._job=self.runner.submit(inspect_characters,self.units,with_progress=True)
        self._buttons()

    def mapping(self):
        return {c:editor.text() for c,editor in self.editors.items() if editor.text()!=c}

    def _buttons(self):
        busy=self.runner.busy
        self.table.setEnabled(not busy)
        self.preview_button.setEnabled(not busy and bool(self.mapping()))
        self.apply_button.setEnabled(not busy and self.plan is not None and bool(self.plan.changes))
        self.progress.setVisible(busy)

    def _changed(self):
        self.plan=None;self.preview_table.setRowCount(0)
        self.summary.setText('Pulsa Previsualizar para comprobar las sustituciones. Los cambios se guardan después con Guardar.')
        self._buttons()

    def preview(self):
        if self.runner.busy:return
        self.plan=None
        self._job=self.runner.submit(plan_substitutions,self.units,self.mapping(),with_progress=True)
        self.summary.setText('Comprobando todas las traducciones…');self._buttons()

    @Slot(str,object)
    def _result(self,task,value):
        if task!=self._job or self._closing is not None:return
        if isinstance(value,tuple):
            self.table.setRowCount(len(value))
            for row,info in enumerate(value):
                c=info.character
                visible='◌'+c if unicodedata.combining(c) else '␣' if c.isspace() else '□' if unicodedata.category(c)=='Cf' else c
                compatibility='No: '+', '.join(info.unsupported) if info.unsupported else 'Compatible: '+', '.join(info.encodings) if info.encodings else 'Sin codec definido'
                for col,text in enumerate((visible,f'U+{ord(c):04X}',str(info.occurrences),str(info.entries),compatibility)):
                    item=QTableWidgetItem(text);item.setToolTip(unicodedata.name(c,'Sin nombre Unicode')+'\n'+compatibility)
                    self.table.setItem(row,col,item)
                editor=QLineEdit(c);editor.setAccessibleName(f'Sustitución de U+{ord(c):04X}')
                editor.setPlaceholderText('Vacío: eliminar');editor.textChanged.connect(self._changed)
                self.editors[c]=editor;self.table.setCellWidget(row,5,editor)
            self.summary.setText(f'{len(value)} caracteres especiales encontrados. Asigna sustituciones y pulsa Previsualizar.' if value else 'No hay caracteres especiales fuera de los controles en las traducciones.')
        else:
            self.plan=value
            self.preview_table.setRowCount(min(10,len(value.changes)))
            for row,change in enumerate(value.changes[:10]):
                for column,text in enumerate((change.before.id,change.before.target,change.after.target)):
                    item=QTableWidgetItem(text.replace('\n',' ↵ '));item.setToolTip(text)
                    self.preview_table.setItem(row,column,item)
            self.summary.setText(f'{len(value.changes)} textos y {value.occurrences} apariciones cambiarán. '
                f'{value.invalid_entries} textos modificados seguirán con errores de codec o límites.\n'
                'Vista previa de los primeros 10. Aplicar modifica la sesión; después puedes deshacer o guardar.')
        self._buttons()

    @Slot(str,object)
    def _error(self,task,error):
        if task==self._job and self._closing is None:
            self.plan=None;self.summary.setText(error.message)

    @Slot(str,object)
    def _progress(self,task,value):
        if task==self._job:
            self.progress.setRange(0,max(value.total,1));self.progress.setValue(value.completed)

    @Slot(str)
    def _finished(self,task):
        self._buttons()
        if self._closing is not None and not self.runner.busy:super().done(self._closing)

    def _apply(self):
        if self.plan is not None and self.plan.changes and not self.runner.busy:
            self.applied.emit(self.plan);self.done(QDialog.DialogCode.Accepted)

    def done(self,result):
        if self.runner.busy:
            self._closing=result;self.runner.cancel_all();self.summary.setText('Cancelando…')
        else:super().done(result)

    def reject(self):
        self.done(QDialog.DialogCode.Rejected)
