from dataclasses import dataclass, field
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

TYPE_LABELS = {"known": "Conocido", "candidate": "Candidato", "unknown": "Desconocido"}
ANALYSIS_LABELS = {"unknown": "Sin analizar", "pending": "Pendiente", "analyzed": "Analizado", "failed": "Error"}


@dataclass
class _Node:
    name: str
    parent: object = None
    children: list = field(default_factory=list)
    resource: object = None
    row: int = 0


class ResourceTreeModel(QAbstractItemModel):
    HEADERS = ("Recurso", "Tipo", "Bytes", "Análisis")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = _Node("")

    def set_resources(self, resources):
        self.beginResetModel()
        self.root = _Node("")
        nodes = {(): self.root}
        for resource in sorted(resources, key=lambda r: r.logical_path):
            parts = tuple(resource.logical_path.split("/"))
            for depth in range(1, len(parts) + 1):
                key = parts[:depth]
                if key not in nodes:
                    parent = nodes[key[:-1]]
                    node = _Node(key[-1], parent, row=len(parent.children))
                    parent.children.append(node)
                    nodes[key] = node
            nodes[parts].resource = resource
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return 0
        return len((parent.internalPointer() if parent.isValid() else self.root).children)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = parent.internalPointer() if parent.isValid() else self.root
        return self.createIndex(row, column, node.children[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        parent = index.internalPointer().parent
        return QModelIndex() if parent is self.root or parent is None else self.createIndex(parent.row, 0, parent)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def resource_for_index(self, index):
        return index.internalPointer().resource if index.isValid() else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        node, column = index.internalPointer(), index.column()
        if column == 0:
            return node.name
        if node.resource is None:
            return "Carpeta" if column == 1 else ""
        resource = node.resource
        type_label = TYPE_LABELS[resource.type_status]
        analysis_label = ANALYSIS_LABELS[resource.analysis_status.value]
        return (node.name, f"{resource.detected_type} · {type_label}", str(resource.size_bytes), analysis_label)[column]
