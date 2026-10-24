from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class StartPage(QWidget):
    def __init__(self, open_action: QAction, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("startPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(16)
        layout.addStretch()
        eyebrow = QLabel("ROMKIT STUDIO")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Explora tu ROM")
        title.setObjectName("welcomeTitle")
        layout.addWidget(title)
        description = QLabel("Abre una ROM o imagen de disco para explorar sus recursos\ny preparar un proyecto de traducción.")
        description.setWordWrap(True)
        description.setObjectName("welcomeDescription")
        layout.addWidget(description)
        self.open_button = QPushButton("Abrir ROM/ISO")
        self.open_button.setObjectName("primaryButton")
        self.open_button.setMinimumHeight(42)
        self.open_button.setMaximumWidth(190)
        self.open_button.clicked.connect(open_action.trigger)
        layout.addWidget(self.open_button)
        hint = QLabel("La imagen original se conserva intacta.")
        hint.setObjectName("welcomeHint")
        layout.addWidget(hint)
        layout.addStretch()
