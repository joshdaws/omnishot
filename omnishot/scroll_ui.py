"""Live scrolling-capture guide and a separate, growing image preview."""
from .theme import color as theme_color
import time
from PySide6.QtCore import Qt,QRect,QPoint,QTimer
from PySide6.QtGui import QPainter,QColor,QPen,QRegion,QPixmap
from PySide6.QtWidgets import QApplication,QWidget
from .editor import qimage
from .widgets import place_window
from . import backend
from .selection_geometry import move_selection,resize_selection,size_selection


class ScrollGuide(QWidget):
    def __init__(self,screen,capture,index):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(f"OmniShot Scrolling Guide {index}");self.bounds=screen.geometry()
        self.capture=QRect(capture).translated(-self.bounds.topLeft())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(self.bounds.size())
    def showEvent(self,event):
        super().showEvent(event);self.windowHandle().setMask(QRegion(-2,-2,1,1))
        place_window(self,self.bounds.x(),self.bounds.y())
    def paintEvent(self,event):
        p=QPainter(self);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(self.rect(),Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # Leave a two-logical-pixel margin so fractional-scale rounding never
        # paints a guide or dimming pixel inside the capture itself.
        clear=self.capture.adjusted(-2,-2,2,2)
        p.setClipRegion(QRegion(self.rect()).subtracted(QRegion(clear)))
        p.fillRect(self.rect(),QColor(0,0,0,105));p.setPen(QPen(QColor("#ffffff"),2))
        p.drawRect(self.capture.adjusted(-3,-3,3,3))


class ScrollSelection(QWidget):
    """An input ring for adjusting the live area before capture starts."""
    def __init__(self,visuals):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.visuals=visuals;self.drag=None;self.local_capture=QRect();self.native_address=None
        self.placement_timer=QTimer(self);self.placement_timer.setSingleShot(True);self.placement_timer.timeout.connect(self.place)
        self.setWindowTitle("OmniShot Scrolling Selection");self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.setMouseTracking(True)
        self.setToolTip("Drag an edge to resize; Shift preserves proportions. Drag the grip to move. After clicking the frame, arrow keys move it; Ctrl+arrows resize; Shift uses 10-pixel steps. Enter starts; Escape cancels.")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    def sync(self):
        r=self.visuals.capture;self.local_capture=QRect(10,10,r.width(),r.height())
        self.setFixedSize(r.width()+20,r.height()+20);self.show();self.input_ring()
        self.place();self.placement_timer.start(120);self.update()
    def place(self):
        if not self.isVisible():return
        try:
            if not self.native_address:
                import os
                self.native_address=next((c["address"] for c in backend.hypr("clients") if c.get("pid")==os.getpid() and c.get("title")==self.windowTitle()),None)
            r=self.visuals.capture
            if self.native_address:backend.move_window(self.native_address,r.x()-10,r.y()-10)
        except Exception:pass
    def input_ring(self):
        if self.windowHandle():self.windowHandle().setMask(QRegion(self.rect()).subtracted(QRegion(self.local_capture.adjusted(7,7,-7,-7))))
    def showEvent(self,event):super().showEvent(event);self.input_ring()
    def handles(self):
        r=self.local_capture;l,t,rgt,b=5,5,r.right()+5,r.bottom()+5;cx,cy=r.center().x(),r.center().y()
        return {"lt":QPoint(l,t),"t":QPoint(cx,t),"rt":QPoint(rgt,t),"r":QPoint(rgt,cy),"rb":QPoint(rgt,b),"b":QPoint(cx,b),"lb":QPoint(l,b),"l":QPoint(l,cy)}
    def grip(self):return QRect(self.local_capture.center().x()-25,0,50,5)
    def hit(self,point):
        if self.grip().adjusted(-2,-1,2,1).contains(point):return "move"
        for edge,handle in self.handles().items():
            if abs(point.x()-handle.x())<=9 and abs(point.y()-handle.y())<=9:return edge
        r=self.local_capture;edge=""
        if point.x()<r.left()+7:edge+="l"
        elif point.x()>r.right()-7:edge+="r"
        if point.y()<r.top()+7:edge+="t"
        elif point.y()>r.bottom()-7:edge+="b"
        return edge
    def paintEvent(self,event):
        painter=QPainter(self);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver);painter.setPen(QPen(theme_color("accent"),1));painter.setBrush(QColor("white"))
        for edge,point in self.handles().items():
            if edge!="t":painter.drawRect(QRect(point.x()-3,point.y()-3,6,6))
        painter.drawRoundedRect(self.grip(),2,2)
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        edge=self.hit(event.position().toPoint())
        if not edge:return
        position=backend.hypr("cursorpos");self.drag=(edge,QPoint(position["x"],position["y"]),QRect(self.visuals.capture));event.accept()
    def mouseMoveEvent(self,event):
        if not self.drag:
            edge=self.hit(event.position().toPoint());cursor=Qt.CursorShape.SizeAllCursor if edge=="move" else Qt.CursorShape.SizeFDiagCursor if edge in ("lt","rb") else Qt.CursorShape.SizeBDiagCursor if edge in ("rt","lb") else Qt.CursorShape.SizeHorCursor if edge in ("l","r") else Qt.CursorShape.SizeVerCursor
            self.setCursor(cursor);return
        edge,start,original=self.drag;position=backend.hypr("cursorpos");delta=QPoint(position["x"],position["y"])-start
        bounds=self.bounds()
        if edge=="move":
            changed=move_selection(original,delta.x(),delta.y(),bounds)
        else:
            ratio=original.width()/original.height() if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else None
            changed=resize_selection(original,edge,delta.x(),delta.y(),bounds,ratio,40)
        self.visuals.set_capture(changed);event.accept()
    def mouseReleaseEvent(self,event):self.drag=None;event.accept()
    def bounds(self):
        bounds=QRect()
        for screen in QApplication.screens():bounds=bounds.united(screen.geometry())
        return bounds
    def keyPressEvent(self,event):
        panel=self.visuals.panel
        if panel.running or panel.stitcher.output is not None:return
        delta={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}.get(event.key())
        if delta:
            step=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1;dx,dy=delta[0]*step,delta[1]*step;r=self.visuals.capture
            changed=size_selection(r,r.width()+dx,r.height()+dy,self.bounds(),minimum=40) if event.modifiers()&Qt.KeyboardModifier.ControlModifier else move_selection(r,dx,dy,self.bounds())
            self.visuals.set_capture(changed);event.accept()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):panel.keyboard_action("accept")
        elif event.key()==Qt.Key.Key_Escape:panel.close()
        else:super().keyPressEvent(event)


class ScrollPreview(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("OmniShot Scrolling Preview");self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.pixmap=QPixmap()
    def showEvent(self,event):
        super().showEvent(event);self.windowHandle().setMask(QRegion(-2,-2,1,1))
    def set_frame(self,frame,maximum):
        self.pixmap=QPixmap.fromImage(qimage(frame)).scaled(*maximum,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        # Fixed constraints communicate the new surface size to Hyprland even
        # though this noninteractive preview never receives focus.
        self.setFixedSize(self.pixmap.size());self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.drawPixmap(0,0,self.pixmap)


class ScrollVisuals:
    def __init__(self,panel):
        self.panel=panel;self.capture=QRect(*panel.rect_capture);self.guides=[];self.preview=ScrollPreview();self.preview_outside=True;self.hidden=[];self.ready_at=0
        self.screen=QApplication.screenAt(self.capture.center()) or QApplication.primaryScreen()
        self.selection=ScrollSelection(self)
    def show(self):
        self.ready_at=time.monotonic()+.17
        if not self.guides:
            for i,screen in enumerate(QApplication.screens()):
                guide=ScrollGuide(screen,self.capture,i);self.guides.append(guide);guide.show()
        if not self.panel.running and self.panel.stitcher.output is None:self.selection.sync()
        else:self.selection.hide()
        bounds=self.screen.availableGeometry();r=self.capture;p=self.panel
        x=r.center().x()-p.width()//2
        choices=[(x,r.bottom()+14),(x,r.top()-p.height()-14),(r.right()+16,r.top()),(r.left()-p.width()-16,r.top())]
        p.outside=self.place(p,choices,bounds)
        if not p.outside:
            p.scroll_geometry=QRect(bounds.right()-p.width()-16,bounds.bottom()-p.height()-16,p.width(),p.height())
            place_window(p,p.scroll_geometry.x(),p.scroll_geometry.y())
    def set_capture(self,rect):
        if self.panel.running or self.panel.stitcher.output is not None:return
        self.capture=QRect(rect);self.panel.rect_capture=(rect.x(),rect.y(),rect.width(),rect.height())
        self.screen=QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
        for guide in self.guides:guide.capture=rect.translated(-guide.bounds.topLeft());guide.update()
        self.panel.status.setText(f"{rect.width()} × {rect.height()} · Adjust the area, then start capture.")
        self.show()
    @staticmethod
    def place(widget,choices,bounds,avoid=()):
        for x,y in choices:
            geometry=QRect(x,y,widget.width(),widget.height())
            if bounds.contains(geometry) and not any(geometry.intersects(other) for other in avoid):
                widget.scroll_geometry=geometry;place_window(widget,x,y);return True
        return False
    def update(self,frame):
        r=self.capture;bounds=self.screen.availableGeometry()
        previous=getattr(self.preview,"scroll_geometry",QRect()).topLeft();was_visible=self.preview.isVisible()
        maximum=(min(500,r.width()),120) if self.panel.horizontal else (160,max(100,min(r.height(),bounds.height()-40)))
        self.preview.set_frame(frame,maximum);self.preview.show()
        if self.panel.horizontal:
            choices=[(r.left(),r.top()-self.preview.height()-16),(r.left(),r.bottom()+self.panel.height()+28)]
        else:choices=[(r.left()-self.preview.width()-24,r.top()),(r.right()+24,r.top()),(r.right()+24,r.top()+self.panel.height()+16)]
        self.preview_outside=self.place(self.preview,choices,bounds,[getattr(self.panel,"scroll_geometry",QRect())])
        if not self.preview_outside:
            self.preview.scroll_geometry=QRect(bounds.left()+16,bounds.top()+16,self.preview.width(),self.preview.height())
            place_window(self.preview,self.preview.scroll_geometry.x(),self.preview.scroll_geometry.y())
        if not was_visible or previous!=self.preview.scroll_geometry.topLeft():self.ready_at=time.monotonic()+.17
    def before_grab(self):
        self.hidden=[]
        for widget,outside in ((self.panel,self.panel.outside),(self.preview,self.preview_outside)):
            if widget.isVisible() and not outside:widget.hide();self.hidden.append(widget)
        return bool(self.hidden)
    def after_grab(self):
        for widget in self.hidden:widget.show()
        self.hidden=[]
    def close(self):
        for guide in self.guides:guide.close()
        self.preview.close();self.selection.close();self.hidden=[]
