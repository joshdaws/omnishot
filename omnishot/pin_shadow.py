"""A noninteractive Wayland subsurface keeps shadows outside pin hit bounds."""
from PySide6.QtCore import Qt,QRect,QRectF,QEvent
from PySide6.QtGui import QWindow,QBackingStore,QSurfaceFormat,QPainter,QRegion,QColor,QPlatformSurfaceEvent


class PinShadow(QWindow):
    def __init__(self,pin):
        super().__init__(pin.windowHandle());self.pin=pin
        self.setFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowTransparentForInput)
        fmt=QSurfaceFormat();fmt.setAlphaBufferSize(8);self.setFormat(fmt)
        self.backing=QBackingStore(self)
    def release_backing(self):
        # The Wayland backing-store destructor still reads its QWindow. Release
        # it before native-window destruction, not later during Python GC.
        backing=getattr(self,'backing',None);self.backing=None
        if backing is not None:
            from shiboken6 import delete,isValid
            if isValid(backing):delete(backing)
    def event(self,event):
        if event.type()==QEvent.Type.PlatformSurface and event.surfaceEventType()==QPlatformSurfaceEvent.SurfaceEventType.SurfaceAboutToBeDestroyed:self.release_backing()
        return super().event(event)
    def sync(self):
        self.setGeometry(-12,-12,self.pin.width()+24,self.pin.height()+24)
        self.setVisible(self.pin.isVisible() and self.pin.store.settings.get('pin_shadow',False));self.render()
    def exposeEvent(self,event):self.render()
    def resizeEvent(self,event):
        if self.backing is not None:self.backing.resize(event.size())
        self.render()
    def render(self):
        if not self.isExposed():return
        if self.backing is None:self.backing=QBackingStore(self)
        region=QRegion(QRect(0,0,self.width(),self.height()));self.backing.resize(self.size());self.backing.beginPaint(region)
        painter=QPainter(self.backing.paintDevice());painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.fillRect(QRect(0,0,self.width(),self.height()),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setOpacity(self.pin.opacity)
        rect=QRect(12,12,self.pin.width(),self.pin.height());painter.setClipRegion(region.subtracted(QRegion(rect)));painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(0,0,0,6));radius=8 if self.pin.store.settings.get('pin_rounded',True) else 0
        for spread in range(10,0,-1):painter.drawRoundedRect(QRectF(rect).adjusted(-spread,-spread/2,spread,spread),radius+spread,radius+spread)
        painter.end();self.backing.endPaint();self.backing.flush(region)
