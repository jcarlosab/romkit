from PySide6.QtWidgets import QTreeView
from romkit_studio.models.resource_tree_model import ResourceTreeModel


class ResourceTree(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resourceTree")
        self.resource_model = ResourceTreeModel(self)
        self.setModel(self.resource_model)
        self.setColumnWidth(0, 190)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)

    def set_resources(self, resources):
        self.resource_model.set_resources(resources)

    def clear(self):
        self.set_resources(())
