"""Native window picker with a frozen desktop and capture-time modifiers."""
from .theme import color as theme_color
from PySide6.QtCore import Qt,QRect,QRectF,Signal
from PySide6.QtGui import QPainter,QColor,QPen,QCursor
from PySide6.QtWidgets import QWidget,QApplication
from .editor import qimage


class WindowSelector(QWidget):
    selected=Signal(object,bool)
    cancelled=Signal()
    def __init__(self,monitor,frame,clients):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle(f"OmniShot Window Selection — {monitor['name']}");self.image=qimage(frame);self.monitor=monitor;self.terminal=False;self.current=None;self.force_copy=False
        screen=next((s for s in QApplication.screens() if s.name()==monitor['name']),QApplication.primaryScreen())
        self.setGeometry(screen.geometry());self.winId();self.windowHandle().setScreen(screen);self.setMouseTracking(True);self.setCursor(Qt.CursorShape.CrossCursor)
        self.clients=sorted([c for c in clients if QRect(*c['at'],*c['size']).intersects(screen.geometry())],key=lambda c:c.get('focusHistoryID',9999) if c.get('focusHistoryID',-1)>=0 else 9999)
    def bounds(self,client):return QRect(*client['at'],*client['size']).translated(-self.geometry().topLeft())
    def hover(self,point):
        self.current=next((c for c in self.clients if self.bounds(c).contains(point)),None);self.update()
    def showEvent(self,event):
        super().showEvent(event);self.hover(self.mapFromGlobal(QCursor.pos()))
        if self.monitor.get("focused"):self.activateWindow();self.setFocus()
    def paintEvent(self,event):
        p=QPainter(self);p.drawImage(self.rect(),self.image);p.fillRect(self.rect(),QColor(0,0,0,100))
        if self.current:
            r=self.bounds(self.current).intersected(self.rect());sx=self.image.width()/self.width();sy=self.image.height()/self.height()
            p.drawImage(QRectF(r),self.image,QRectF(r.x()*sx,r.y()*sy,r.width()*sx,r.height()*sy));p.setPen(QPen(theme_color("accent"),2));p.drawRect(r.adjusted(1,1,-1,-1))
        p.fillRect(12,12,min(760,self.width()-24),58,theme_color("background"));p.setPen(theme_color('foreground'))
        p.drawText(24,36,'Click a window · Shift for transparency · Tab switches windows · Esc cancels')
        if self.current:p.drawText(24,57,self.fontMetrics().elidedText(self.current.get('title',''),Qt.TextElideMode.ElideRight,min(710,self.width()-48)))
    def mouseMoveEvent(self,event):self.hover(event.position().toPoint())
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.hover(event.position().toPoint());self.finish(event.modifiers())
        elif event.button()==Qt.MouseButton.RightButton:self.cancel()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.cancel()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.finish(event.modifiers())
        elif event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab) and self.clients:
            index=self.clients.index(self.current) if self.current in self.clients else -1
            step=-1 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1
            self.current=self.clients[(index+step)%len(self.clients)];self.update()
    def event(self,event):
        from PySide6.QtCore import QEvent
        if event.type()==QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):self.keyPressEvent(event);return True
        return super().event(event)
    def finish(self,modifiers):
        if self.current and not self.terminal:
            self.force_copy=bool(modifiers&Qt.KeyboardModifier.ControlModifier)
            self.terminal=True;self.selected.emit(self.current,bool(modifiers&Qt.KeyboardModifier.ShiftModifier))
    def cancel(self):
        if not self.terminal:self.terminal=True;self.cancelled.emit()
    def closeEvent(self,event):self.cancel();super().closeEvent(event)
