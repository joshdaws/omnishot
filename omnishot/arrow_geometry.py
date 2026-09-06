"""Editable tapered arrow geometry, generated without reference image assets."""
import math
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath,QPolygonF


def tapered_arrow(a,b,width):
    delta=b-a;length=math.hypot(delta.x(),delta.y())
    if length<.001:return QPainterPath()
    direction=delta/length;normal=QPointF(-direction.y(),direction.x())
    head=min(max(13,width*4),length*.7);base=b-direction*(head*math.cos(.5));wing=normal*(head*math.sin(.5))
    neck=normal*min(width/2,head*.15);tail=normal*min(width*.125,length*.025)
    path=QPainterPath();path.addPolygon(QPolygonF([a-tail,base-neck,base-wing,b,base+wing,base+neck,a+tail]));path.closeSubpath();return path
