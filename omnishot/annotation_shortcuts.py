"""Window-scoped annotation shortcuts and conflict validation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence


def validate_pin(value,global_shortcuts):
    if not value:return
    sequence=QKeySequence(value)
    if sequence.count()!=1 or sequence[0].key() in (Qt.Key.Key_unknown,Qt.Key.Key_Shift,Qt.Key.Key_Control,Qt.Key.Key_Alt,Qt.Key.Key_Meta):
        raise ValueError('Choose one key combination for Pin in Annotate.')
    from .editor_toolbar import TOOLS
    reserved=[shortcut for _,_,shortcut in TOOLS]+['C','Ctrl+O','Ctrl+S','Ctrl+Shift+S','Ctrl+I','Ctrl+C','Ctrl+V','Ctrl+P','Ctrl+Z','Ctrl+Shift+Z','Delete','Backspace','Ctrl+D','Space','Escape','Return','Enter','Left','Right','Up','Down','Ctrl+Return','Ctrl+Enter','Ctrl+A','Ctrl+X','Ctrl+Y']
    if sequence[0].key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down) or any(sequence==QKeySequence(key) for key in reserved):raise ValueError('That shortcut is already used for an annotation or text-editing command.')
    if any(key and sequence==QKeySequence(key) for key in global_shortcuts.values()):raise ValueError('That shortcut is already assigned to a global OmniShot action.')


def available_while_typing(sequence):
    if sequence.isEmpty():return False
    key=sequence[0]
    return bool(key.keyboardModifiers()&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier)) or Qt.Key.Key_F1<=key.key()<=Qt.Key.Key_F35
