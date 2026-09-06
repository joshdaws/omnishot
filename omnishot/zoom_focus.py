"""Visual source framing for an editable recording zoom."""
from .theme import color as theme_color
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class ZoomFocus(QWidget):
    changed = Signal(float, float, float)

    def __init__(self, image=None, parent=None):
        super().__init__(parent)
        self.image = QImage(image) if image is not None else QImage()
        self.scale = 2.; self.cx = .5; self.cy = .5; self.drag = None
        self.setMinimumSize(480, 240); self.setMaximumHeight(340)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Zoom focus frame")
        self.setToolTip("Drag the frame to move the focus. Drag a corner to resize. Arrow keys move the frame; Shift moves farther.")

    def set_image(self, image):
        self.image = QImage(image); self.update()

    def set_values(self, scale, x, y):
        self.scale = max(1., min(5., scale)); half = .5 / self.scale
        self.cx = max(half, min(1-half, x)); self.cy = max(half, min(1-half, y)); self.update()

    def image_rect(self):
        area = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        ratio = self.image.width()/self.image.height() if not self.image.isNull() else 16/9
        width = min(area.width(), area.height()*ratio); height = width/ratio
        return QRectF(area.center().x()-width/2, area.center().y()-height/2, width, height)

    def focus_rect(self):
        r = self.image_rect(); w = r.width()/self.scale; h = r.height()/self.scale
        return QRectF(r.left()+r.width()*self.cx-w/2, r.top()+r.height()*self.cy-h/2, w, h)

    def corners(self):
        r = self.focus_rect()
        return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]

    def normalized(self, point):
        r = self.image_rect()
        return QPointF((point.x()-r.left())/r.width(), (point.y()-r.top())/r.height())

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme_color("base")); r = self.image_rect()
        if self.image.isNull():
            p.setPen(theme_color("muted"));p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Loading recording frame…")
        else:p.drawImage(r, self.image)
        focus = self.focus_rect(); shade = QPainterPath(); shade.addRect(r); shade.addRect(focus)
        p.fillPath(shade, QColor(0,0,0,140));p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(theme_color('accent' if self.isEnabled() else 'muted'),2));p.drawRect(focus)
        if self.isEnabled():
            p.setBrush(QColor("#ffffff"))
            for c in self.corners():p.drawRoundedRect(QRectF(c.x()-4,c.y()-4,8,8),2,2)
        p.setPen(QColor("white"));p.drawText(focus.adjusted(8,6,-8,-6),Qt.AlignmentFlag.AlignTop,f"{self.scale:.2f}×")

    def announce(self):
        self.changed.emit(self.scale,self.cx,self.cy);self.update()

    def mousePressEvent(self, event):
        if event.button()!=Qt.MouseButton.LeftButton or not self.isEnabled():return
        self.before=(self.scale,self.cx,self.cy);self.setFocus(); point=event.position(); normalized=self.normalized(point)
        for i,corner in enumerate(self.corners()):
            if (point-corner).manhattanLength()<15:
                anchor=self.normalized(self.corners()[(i+2)%4])
                self.drag=("resize",anchor,-1 if i in (0,3) else 1,-1 if i in (0,1) else 1);return
        if not self.image_rect().contains(point):return
        if not self.focus_rect().contains(point):
            self.set_values(self.scale,normalized.x(),normalized.y());self.announce()
        self.drag=("move",normalized,self.cx,self.cy)

    def mouseMoveEvent(self, event):
        if not self.drag:return
        point=self.normalized(event.position())
        if self.drag[0]=="move":
            _,origin,x,y=self.drag;self.set_values(self.scale,x+point.x()-origin.x(),y+point.y()-origin.y())
        else:
            _,anchor,sx,sy=self.drag
            size=max((point.x()-anchor.x())*sx,(point.y()-anchor.y())*sy)
            limit=min(anchor.x() if sx<0 else 1-anchor.x(),anchor.y() if sy<0 else 1-anchor.y())
            size=max(.2,min(limit,size));self.set_values(1/size,anchor.x()+sx*size/2,anchor.y()+sy*size/2)
        self.announce()

    def mouseReleaseEvent(self, event):self.drag=None

    def keyPressEvent(self, event):
        if event.key()==Qt.Key.Key_Escape and self.drag:
            self.drag=None;self.set_values(*self.before);self.announce();event.accept();return
        directions={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}
        if event.key() in directions:
            dx,dy=directions[event.key()];step=.01 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else .001
            self.set_values(self.scale,self.cx+dx*step,self.cy+dy*step);self.announce()
        else:super().keyPressEvent(event)
