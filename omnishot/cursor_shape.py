"""Cursor geometry shared by style tiles, video preview and export."""
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QPainterPath,QPen


def paint_cursor(painter,position,size,style='Arrow',fill='#161821',outline='#ffffff'):
    p=painter;x,y=position.x(),position.y();p.save()
    p.setPen(QPen(QColor(outline),max(1,size/16)));p.setBrush(QColor(fill))
    if style=='Dot':p.drawEllipse(position,size*.3,size*.3)
    elif style=='Crosshair':
        p.drawRoundedRect(QRectF(x-size*.5,y-size*.07,size,size*.14),size*.06,size*.06)
        p.drawRoundedRect(QRectF(x-size*.07,y-size*.5,size*.14,size),size*.06,size*.06)
    else:
        points=[QPointF(x+dx*size,y+dy*size) for dx,dy in [(0,0),(0,1),(.26,.75),(.48,1.1),(.66,1),(.45,.65),(.8,.65)]]
        path=QPainterPath()
        if style=='Rounded Arrow':
            for i,point in enumerate(points):
                def toward(other):
                    delta=other-point;distance=(delta.x()**2+delta.y()**2)**.5
                    return point+delta*min(.25,size*.07/distance)
                entry=toward(points[i-1]);leave=toward(points[(i+1)%len(points)])
                if i==0:path.moveTo(entry)
                else:path.lineTo(entry)
                path.quadTo(point,leave)
        else:
            path.moveTo(points[0])
            for point in points[1:]:path.lineTo(point)
        path.closeSubpath();p.drawPath(path)
    p.restore()
