"""One logical selection shared by the per-output Wayland surfaces."""
from PySide6.QtCore import QRect,QRectF,QPoint
from PySide6.QtGui import QImage,QPainter
from .clean_capture import monitor_bounds


class SelectionGroup:
    def __init__(self,selectors,previous=None):
        self.selectors=list(selectors);self.active=None;self.desktop=QRect();self.syncing_mode=False
        for selector in self.selectors:
            self.desktop=self.desktop.united(QRect(*monitor_bounds(selector.monitor)))
            selector.group=self
            selector.capture_mode.currentTextChanged.connect(lambda kind,s=selector:self.mode(s,kind))
        if previous:
            region=QRect(*previous).intersected(self.desktop)
            if not region.isEmpty():self.set_region(region)

    def bounds(self,selector):
        return self.desktop.translated(-selector.monitor['x'],-selector.monitor['y'])

    def region(self,selector):
        return selector.selection.translated(selector.monitor['x'],selector.monitor['y'])

    def set_region(self,region,source=None):
        for selector in self.selectors:
            if selector is source:continue
            selector.selection=region.translated(-selector.monitor['x'],-selector.monitor['y'])
            selector.sync_size(share=False);selector.update()

    def sync(self,source):
        if source.capture_mode.currentText() not in ('Window','Fullscreen'):
            for selector in self.selectors:
                selector.aspect.blockSignals(True);selector.aspect.setCurrentText(source.aspect.currentText());selector.aspect.blockSignals(False)
            self.set_region(self.region(source),source)

    def mode(self,source,kind):
        if self.syncing_mode:return
        self.syncing_mode=True
        try:
            for selector in self.selectors:
                if selector is source:continue
                previous=selector.capture_mode.currentText()
                if kind=='Window' and previous!='Window':selector.area_selection=QRect(selector.selection)
                elif previous=='Window' and kind!='Window' and selector.area_selection is not None:selector.selection=QRect(selector.area_selection)
                selector.capture_mode.setCurrentText(kind)
                for widget in (selector.width_box,selector.height_box,selector.aspect):widget.setEnabled(kind not in ('Window','Fullscreen'))
                if kind=='Window':selector.hover_window(selector.pointer)
                elif kind=='Fullscreen':selector.selection=QRect(selector.rect())
                selector.sync_size(share=False);selector.update()
        finally:self.syncing_mode=False

    def pointer(self,source):
        global_point=source.pointer+QPoint(source.monitor['x'],source.monitor['y'])
        for selector in self.selectors:
            if selector is source:continue
            selector.pointer=global_point-QPoint(selector.monitor['x'],selector.monitor['y']);selector.update()

    def scale(self,selector):
        region=self.region(selector)
        return max((s.image.width()/s.width() for s in self.selectors if region.intersects(QRect(*monitor_bounds(s.monitor)))),default=selector.image.width()/selector.width())

    def image(self,selector):
        region=self.region(selector);scale=self.scale(selector)
        image=QImage(round(region.width()*scale),round(region.height()*scale),QImage.Format.Format_RGB32);image.fill(0)
        painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for s in self.selectors:
            bounds=QRect(*monitor_bounds(s.monitor));part=region.intersected(bounds)
            if part.isEmpty():continue
            x0=round((part.x()-region.x())*scale);y0=round((part.y()-region.y())*scale)
            x1=round((part.x()+part.width()-region.x())*scale);y1=round((part.y()+part.height()-region.y())*scale)
            sx=s.image.width()/bounds.width();sy=s.image.height()/bounds.height()
            painter.drawImage(QRectF(x0,y0,x1-x0,y1-y0),s.image,QRectF((part.x()-bounds.x())*sx,(part.y()-bounds.y())*sy,part.width()*sx,part.height()*sy))
        painter.end();return image
