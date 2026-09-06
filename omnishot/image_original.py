"""Preserve a source bitmap and map annotations back through canvas edits."""
import math
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QTransform


def values(transform):
    return [transform.m11(),transform.m12(),transform.m21(),transform.m22(),transform.dx(),transform.dy()]


def remember(editor,operation):
    if editor.original_image is None:editor.original_image=QImage(editor.base)
    editor.source_transform=editor.source_transform*operation


def restore_original(editor):
    if editor.original_image is None:return False
    inverse,valid=editor.source_transform.inverted()
    if not valid:raise ValueError('Cannot restore invalid source geometry')
    linear=QTransform(inverse.m11(),inverse.m12(),inverse.m21(),inverse.m22(),0,0)
    props=[obj.data_dict() for obj in editor.objects]
    for prop in props:
        point=inverse.map(QPointF(prop.get('x',0),prop.get('y',0)));prop['x'],prop['y']=point.x(),point.y()
        prop['transform']=values(QTransform(*prop.get('transform',[1,0,0,1,0,0]))*linear)
    editor.base=QImage(editor.original_image);editor.source_transform=QTransform()
    editor.expand_canvas=False;editor.expand_action.blockSignals(True);editor.expand_action.setChecked(False);editor.expand_action.blockSignals(False)
    editor.rebuild(props);return True


def parse_transform(raw):
    if not isinstance(raw,list) or len(raw)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e12 for v in raw):raise ValueError('Invalid original image geometry')
    transform=QTransform(*raw)
    if not transform.isInvertible():raise ValueError('Invalid original image geometry')
    return transform
