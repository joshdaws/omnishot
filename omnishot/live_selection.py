"""Small clean desktop samples for the live selection magnifier."""
from PySide6.QtCore import QTimer,QRect,QRectF
from shiboken6 import isValid
from . import backend
from .editor import qimage


class LiveMagnifier:
    def __init__(self,selector):
        self.selector=selector;self.busy=False;self.frame=None;self.region=None;self.error=None
        self.timer=QTimer(selector);self.timer.setInterval(80);self.timer.timeout.connect(self.refresh);self.timer.start()
    def stop(self):self.timer.stop()
    def refresh(self):
        s=self.selector
        if not isValid(s) or s.terminal or not s.isVisible() or self.busy:return
        mode=s.settings.get('crosshair_mode','always')
        if s.capture_mode.currentText()=='Window' or not s.settings.get('show_magnifier',True) or mode=='disabled' or (mode=='selecting' and not s.selecting()):return
        from .widgets import background
        bounds=QRect(s.monitor['x'],s.monitor['y'],s.width(),s.height())
        region=QRect(s.monitor['x']+s.pointer.x()-32,s.monitor['y']+s.pointer.y()-32,64,64).intersected(bounds)
        if region.isEmpty():return
        self.busy=True
        def done(frame):
            self.busy=False
            if not isValid(s) or s.terminal:return
            self.frame=qimage(frame);self.region=region;self.error=None;s.update()
        def failed(message):
            self.busy=False
            if isValid(s) and not s.terminal:self.error=message;self.frame=None;s.update()
        background(lambda:backend.grab(region.getRect(),scale=s.monitor['scale']),done,failed)
    def sample(self):
        s=self.selector
        if self.frame is None or self.region is None:return None
        x=s.monitor['x']+s.pointer.x()-self.region.x();y=s.monitor['y']+s.pointer.y()-self.region.y()
        sx=self.frame.width()/self.region.width();sy=self.frame.height()/self.region.height()
        source=QRectF(x*sx-12,y*sy-12,24,24)
        if not QRectF(self.frame.rect()).intersects(source):return None
        return self.frame,source
