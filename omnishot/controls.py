"""Native Qt controls with narrowly scoped input compatibility fixes."""
from PySide6.QtCore import Qt,QEvent,QTimer
from PySide6.QtWidgets import QComboBox


class Choice(QComboBox):
    """Commit a popup with Enter without reopening it with the same key.

    Qt 6.11 closes/selects the popup during ShortcutOverride. Themes that include
    Return in ButtonPressKeys then reopen it in the following keyPressEvent.
    Remember only that one event dispatch; later Enter presses still open it.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._committing_popup=False
        self.view().installEventFilter(self)
    def eventFilter(self,target,event):
        if (event.type()==QEvent.Type.ShortcutOverride
                and event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter)
                and self.view().window().isVisible()):
            self._committing_popup=True;QTimer.singleShot(0,self._clear_commit)
        return super().eventFilter(target,event)
    def _clear_commit(self):self._committing_popup=False
    def keyPressEvent(self,event):
        if self._committing_popup and event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
            self._committing_popup=False;event.accept();return
        super().keyPressEvent(event)
