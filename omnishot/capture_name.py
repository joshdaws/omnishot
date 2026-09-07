"""Choose a capture's name before running any After Capture actions."""
from . import ui_scale as ui
from pathlib import Path
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QDialogButtonBox


class CaptureNameDialog(QDialog):
    DISCARDED=2

    def __init__(self,store,path,parent=None):
        super().__init__(parent);self.store=store;self.path=Path(path)
        self.setWindowTitle('Name capture');ui.set(self,"setMinimumWidth",440)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('File name'))
        self.name=QLineEdit(Path(store.display_name(path)).stem);self.name.setAccessibleName('File name');layout.addWidget(self.name)
        hint=QLabel('Cancel keeps the automatic name. Discard removes this capture.');hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint)
        self.message=QLabel();self.message.setWordWrap(True);self.message.hide();layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.discard_button=self.buttons.addButton('Discard',QDialogButtonBox.ButtonRole.DestructiveRole)
        self.discard_button.setAutoDefault(False);self.discard_button.clicked.connect(self.discard)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True);self.name.selectAll();self.name.setFocus()

    def accept(self):
        try:self.store.rename(self.path,self.name.text())
        except (OSError,ValueError) as exc:self.show_error(exc);return
        super().accept()

    def discard(self):
        try:self.store.remove(self.path)
        except (OSError,ValueError) as exc:self.show_error(exc);return
        self.done(self.DISCARDED)

    def show_error(self,error):
        self.message.setText(str(error));self.message.show();self.name.setFocus()
