"""Temporary Space-drag navigation without changing annotations or crop state."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QCursor


class CanvasPan:
    def __init__(self,view):
        self.view=view;self.held=False;self.origin=None;self.cursor=None

    def key_press(self,event):
        if event.key()!=Qt.Key.Key_Space:return False
        if self.held:return True
        if self.origin is not None:self.held=True;return True
        editor=self.view.editor
        if editor.inline or self.view.draft is not None or getattr(editor.crop_session,'drag',None):return False
        if event.modifiers()&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier):return False
        self.held=True;self.cursor=QCursor(self.view.cursor());self.view.setCursor(Qt.CursorShape.OpenHandCursor)
        return True

    def key_release(self,event):
        if event.key()!=Qt.Key.Key_Space or not self.held:return False
        if not event.isAutoRepeat():
            self.held=False
            if self.origin is None:self.restore_cursor()
        return True

    def press(self,event):
        if not self.held or event.button()!=Qt.MouseButton.LeftButton:return False
        self.origin=QPointF(event.position());self.scroll=(self.view.horizontalScrollBar().value(),self.view.verticalScrollBar().value())
        self.view.setCursor(Qt.CursorShape.ClosedHandCursor);return True

    def move(self,event):
        if self.origin is None:return False
        delta=event.position()-self.origin
        self.view.horizontalScrollBar().setValue(self.scroll[0]-round(delta.x()))
        self.view.verticalScrollBar().setValue(self.scroll[1]-round(delta.y()))
        return True

    def release(self,event):
        if self.origin is None or event.button()!=Qt.MouseButton.LeftButton:return False
        self.origin=None
        if self.held:self.view.setCursor(Qt.CursorShape.OpenHandCursor)
        else:self.restore_cursor()
        return True

    def restore_cursor(self):
        if self.cursor is not None:self.view.setCursor(self.cursor);self.cursor=None

    def cancel(self):
        self.held=False;self.origin=None;self.restore_cursor()
