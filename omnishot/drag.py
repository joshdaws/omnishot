"""File drag with definitive Wayland completion when Qt omits the action."""
import ctypes
from PySide6.QtCore import Qt

try:
    _native=ctypes.CDLL(None)
    _native.omnishot_drag_begin.restype=ctypes.c_ulong
    _native.omnishot_drag_end.argtypes=[ctypes.c_ulong]
    _native.omnishot_drag_end.restype=ctypes.c_int
except AttributeError:
    _native=None


def execute(drag):
    token=_native.omnishot_drag_begin() if _native else None
    success=False
    try:result=drag.exec(Qt.DropAction.CopyAction)
    finally:
        if _native:success=bool(_native.omnishot_drag_end(token))
    return success or result!=Qt.DropAction.IgnoreAction
