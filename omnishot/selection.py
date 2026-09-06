"""Live and frozen per-display capture with crosshair, magnifier and exact region controls."""
from .theme import color as theme_color
from PySide6.QtCore import Qt,QRect,QRectF,QPoint,QTimer,Signal
from PySide6.QtGui import QPainter,QColor,QPen,QFont,QCursor
from PySide6.QtWidgets import QWidget,QApplication,QHBoxLayout,QPushButton,QSpinBox,QLabel
from .controls import Choice as QComboBox
from .editor import qimage
from .selection_geometry import move_selection,resize_selection,size_selection


class Selector(QWidget):
    selected=Signal(object,object,str)
    cancelled=Signal()
    def __init__(self,monitor,frame,mode="area",previous=None,settings=None,capture_kind=None,live=False,clients=None):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.live=live;self.magnifier=None;self.group=None
        if live:self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.settings=dict(settings or {});self.skip_background=False;self.force_copy=False;self.capture_action=None
        self.clients=list(clients or []);self.window_client=None;self.area_selection=None;self.all_in_one=mode=='select' and capture_kind is None
        self.setWindowTitle(f"OmniShot Selection — {monitor['name']}");self.monitor=monitor;self.image=qimage(frame);self.mode=mode;self.terminal=False
        self.start=None;self.selection=QRect();self.pointer=QPoint(50,50);self.drag_kind="new";self.drag_original=QRect();self.setMouseTracking(True);self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.controls=QWidget(self);layout=QHBoxLayout(self.controls);layout.setContentsMargins(8,8,8,8)
        self.width_box=QSpinBox();self.width_box.setRange(2,20000);self.width_box.setValue(640)
        self.height_box=QSpinBox();self.height_box.setRange(2,20000);self.height_box.setValue(400)
        self.width_box.setKeyboardTracking(False);self.height_box.setKeyboardTracking(False)
        layout.addWidget(QLabel("W"));layout.addWidget(self.width_box);layout.addWidget(QLabel("H"));layout.addWidget(self.height_box)
        self.aspect=QComboBox();self.aspect.addItems(["Free","1:1","16:9","4:3","9:16","5:4"]);layout.addWidget(self.aspect)
        self.capture_mode=QComboBox();self.capture_mode.addItems(["Screenshot","Fullscreen","Window","Scrolling","Horizontal scrolling","Self timer","Text (OCR)","Record video"]);layout.addWidget(self.capture_mode)
        capture=QPushButton("Capture");capture.setObjectName("primary");capture.clicked.connect(self.finish);layout.addWidget(capture)
        if capture_kind:
            self.capture_mode.setCurrentText(capture_kind);self.capture_mode.hide();capture.setText("Record" if capture_kind=="Record video" else "Capture")
        cancel=QPushButton("Cancel");cancel.clicked.connect(self.cancel);layout.addWidget(cancel)
        if self.all_in_one:
            from .selection_bar import SelectionBar
            old_controls=self.controls;self.controls=SelectionBar(self)
            self.capture_mode.setParent(self);self.capture_mode.hide();old_controls.hide();old_controls.deleteLater()
        self.width_box.valueChanged.connect(self.exact);self.height_box.valueChanged.connect(self.exact)
        self.aspect.currentTextChanged.connect(self.exact)
        screen=next((s for s in QApplication.screens() if s.name()==monitor["name"]),QApplication.primaryScreen())
        self.setGeometry(screen.geometry());self.winId();self.windowHandle().setScreen(screen)
        if previous:
            x,y,w,h=previous;self.selection=QRect(x-monitor["x"],y-monitor["y"],w,h).intersected(self.rect())
            if not self.selection.isEmpty():
                for box,value in [(self.width_box,self.selection.width()),(self.height_box,self.selection.height())]:box.blockSignals(True);box.setValue(value);box.blockSignals(False)
        if live:
            from .live_selection import LiveMagnifier
            self.magnifier=LiveMagnifier(self)
    def showEvent(self,event):
        super().showEvent(event);self.place_controls()
        if self.monitor.get("focused"):self.activateWindow();self.setFocus()
    def place_controls(self):
        if self.all_in_one:self.controls.fit(self.width())
        else:self.controls.adjustSize()
        self.controls.move(max(10,(self.width()-self.controls.width())//2),self.height()-self.controls.height()-25)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'controls'):self.place_controls()
    def choose_mode(self,kind):
        previous=self.capture_mode.currentText()
        if kind=='Window' and previous!='Window':self.area_selection=QRect(self.selection)
        elif previous=='Window' and kind!='Window' and self.area_selection is not None:self.selection=QRect(self.area_selection)
        self.capture_mode.setCurrentText(kind);self.setFocus()
        for widget in (self.width_box,self.height_box,self.aspect):widget.setEnabled(kind not in ('Window','Fullscreen'))
        if kind=='Window':self.hover_window(self.pointer);return
        if kind=='Fullscreen':self.selection=QRect(self.rect())
        self.sync_size();self.update()
        if not self.selection.isEmpty():self.finish()
    def hover_window(self,point):
        candidates=sorted(self.clients,key=lambda c:c.get('focusHistoryID',9999) if c.get('focusHistoryID',-1)>=0 else 9999)
        self.window_client=next((c for c in candidates if QRect(*c['at'],*c['size']).translated(-self.monitor['x'],-self.monitor['y']).contains(point)),None)
        self.show_window()
    def show_window(self):
        self.selection=QRect(*self.window_client['at'],*self.window_client['size']).translated(-self.monitor['x'],-self.monitor['y']).intersected(self.rect()) if self.window_client else QRect()
        self.sync_size();self.update()
    def exact(self):
        r=self.selection if not self.selection.isNull() else QRect(50,50,2,2)
        self.selection=size_selection(r,self.width_box.value(),self.height_box.value(),self.selection_bounds(),self.ratio(),"height" if self.sender() is self.height_box else "width")
        self.sync_size();self.update()
    def selection_bounds(self):
        return self.group.bounds(self) if self.group and self.capture_mode.currentText() not in ('Window','Fullscreen') else self.rect()
    def capture_scale(self):
        return self.group.scale(self) if self.group else self.image.width()/self.width()
    def selecting(self):return self.start is not None or bool(self.group and self.group.active is not None)
    def ratio(self):
        text=self.aspect.currentText()
        if text=="Free":return None
        a,b=map(float,text.split(":"));return a/b
    def sync_size(self,share=True):
        for box,value in ((self.width_box,self.selection.width()),(self.height_box,self.selection.height())):
            box.blockSignals(True);box.setValue(value);box.blockSignals(False)
        if share and self.group:self.group.sync(self)
    def paintEvent(self,event):
        p=QPainter(self)
        if self.live:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);p.fillRect(self.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        else:p.drawImage(self.rect(),self.image)
        p.fillRect(self.rect(),QColor(0,0,0,75))
        sx=self.image.width()/self.width();sy=self.image.height()/self.height()
        if not self.selection.isNull() and self.selection.intersects(self.rect()):
            r=self.selection
            if self.live:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear);p.fillRect(r,Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            else:p.drawImage(QRectF(r),self.image,QRectF(r.x()*sx,r.y()*sy,r.width()*sx,r.height()*sy))
            p.setPen(QPen(theme_color("accent"),1));p.drawRect(r)
            scale=self.capture_scale()
            text=f"{r.width()} × {r.height()}"
            if self.capture_mode.currentText()!='Record video':text+=f"   ({round(r.width()*scale)} × {round(r.height()*scale)} px)"
            label_width=p.fontMetrics().horizontalAdvance(text)+16
            label=QRect(max(8,min(r.x(),self.width()-label_width-8)),max(5,min(r.y()-28,self.height()-29)),label_width,24)
            p.fillRect(label,theme_color("background"));p.setPen(theme_color("foreground"));p.drawText(label.adjusted(8,0,-8,0),Qt.AlignmentFlag.AlignVCenter,text)
            if self.mode=="select" and self.capture_mode.currentText()!='Window':
                p.setBrush(QColor("white"));p.setPen(theme_color("accent"))
                for point in [r.topLeft(),r.topRight(),r.bottomLeft(),r.bottomRight(),QPoint(r.center().x(),r.top()),QPoint(r.center().x(),r.bottom()),QPoint(r.left(),r.center().y()),QPoint(r.right(),r.center().y())]:p.drawRect(QRect(point-QPoint(3,3),__import__("PySide6.QtCore",fromlist=["QSize"]).QSize(6,6)))
        crosshair=self.settings.get("crosshair_mode","always")
        if self.capture_mode.currentText()!='Window' and (crosshair=="always" or (crosshair=="selecting" and self.selecting())):
            x,y=self.pointer.x(),self.pointer.y();p.setPen(QPen(QColor(255,255,255,145),1));p.drawLine(0,y,self.width(),y);p.drawLine(x,0,x,self.height())
            if self.settings.get("show_magnifier",True):
                target=QRect(min(self.width()-112,x+22),max(10,min(self.height()-170,y+22)),100,100)
                sample=self.magnifier.sample() if self.live else (self.image,QRectF(x*sx-12,y*sy-12,24,24))
                if sample:p.drawImage(QRectF(target),*sample)
                else:p.fillRect(target,theme_color("background"))
                p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(theme_color("accent"),2));p.drawRect(target);p.drawLine(target.center().x()-5,target.center().y(),target.center().x()+5,target.center().y());p.drawLine(target.center().x(),target.center().y()-5,target.center().x(),target.center().y()+5)
        p.setPen(QColor("white"));p.setFont(QFont("Inter",14));p.drawText(24,36,'Click a window · Tab switches windows · Shift for transparency · Esc cancels' if self.capture_mode.currentText()=='Window' else "Drag to select · Shift locks proportions · Enter captures · Esc cancels")
    def mousePressEvent(self,event):
        # Child controls may ignore a right press before emitting their context
        # menu. Do not let that propagated event cancel the whole selection.
        if self.controls.geometry().contains(event.position().toPoint()):event.accept();return
        if event.button()==Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if self.capture_mode.currentText()=='Window':self.hover_window(event.position().toPoint());self.finish();return
            self.start=event.position().toPoint();self.drag_original=QRect(self.selection);self.drag_kind="new"
            if self.group:self.group.active=self
            if self.mode=="select" and not self.selection.isEmpty():
                r=self.selection;point=self.start
                edges=("l" if abs(point.x()-r.left())<8 else "r" if abs(point.x()-r.right())<8 else "")+("t" if abs(point.y()-r.top())<8 else "b" if abs(point.y()-r.bottom())<8 else "")
                if edges and r.adjusted(-8,-8,8,8).contains(point):self.drag_kind=edges
                elif r.contains(point):self.drag_kind="move"
            if self.drag_kind=="new":self.selection=QRect(self.start,self.start)
        elif event.button()==Qt.MouseButton.RightButton:self.cancel()
    def mouseMoveEvent(self,event):
        self.pointer=event.position().toPoint()
        if self.group and self.start is not None:self.group.pointer(self)
        if self.capture_mode.currentText()=='Window':self.hover_window(self.pointer);return
        if self.start is not None:
            end=self.pointer;dx=end.x()-self.start.x();dy=end.y()-self.start.y()
            if self.drag_kind=="move":
                self.selection=move_selection(self.drag_original,dx,dy,self.selection_bounds());self.sync_size();self.update();return
            if self.drag_kind!="new":
                ratio=self.ratio()
                if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:ratio=self.drag_original.width()/max(1,self.drag_original.height())
                self.selection=resize_selection(self.drag_original,self.drag_kind,dx,dy,self.selection_bounds(),ratio);self.sync_size();self.update();return
            ratio=1 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else self.ratio()
            edge=("r" if dx>=0 else "l")+("b" if dy>=0 else "t")
            self.selection=resize_selection(QRect(self.start.x(),self.start.y(),1,1),edge,dx,dy,self.selection_bounds(),ratio)
            self.sync_size()
        self.update()
    def mouseReleaseEvent(self,event):
        self.start=None
        if self.group:self.group.active=None
        self.sync_size()
        if self.mode=="area" and self.selection.width()>2 and self.selection.height()>2:self.finish()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.cancel()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.finish()
        elif self.all_in_one and event.key()==Qt.Key.Key_C and event.modifiers()&Qt.KeyboardModifier.ControlModifier:
            self.capture_action='copy';self.finish()
        elif self.capture_mode.currentText()=='Window' and event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):
            candidates=[c for c in self.clients if QRect(*c['at'],*c['size']).intersects(QRect(self.monitor['x'],self.monitor['y'],self.width(),self.height()))]
            if candidates:
                index=candidates.index(self.window_client) if self.window_client in candidates else -1
                self.window_client=candidates[(index+(-1 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1))%len(candidates)];self.show_window()
        elif event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down) and not self.selection.isEmpty() and self.capture_mode.currentText()!='Window':
            dx,dy={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}[event.key()];step=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1
            if event.modifiers()&Qt.KeyboardModifier.ControlModifier:
                self.selection=size_selection(self.selection,self.selection.width()+dx*step,self.selection.height()+dy*step,self.selection_bounds(),self.ratio(),"width" if dx else "height")
            else:self.selection=move_selection(self.selection,dx*step,dy*step,self.selection_bounds())
            self.sync_size();self.update()
    def event(self,event):
        from PySide6.QtCore import QEvent
        if event.type()==QEvent.Type.KeyPress and hasattr(self,'capture_mode') and self.capture_mode.currentText()=='Window' and event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):self.keyPressEvent(event);return True
        return super().event(event)
    def finish(self):
        if self.terminal:return
        r=self.selection
        if r.width()<2 or r.height()<2:return
        sx=self.image.width()/self.width();sy=self.image.height()/self.height()
        kind=self.capture_mode.currentText()
        if kind=='Window' and self.window_client is None:return
        image=self.window_client if kind=='Window' else (None if self.live or kind in ('Self timer','Record video','Scrolling','Horizontal scrolling') else self.group.image(self) if self.group else self.image.copy(round(r.x()*sx),round(r.y()*sy),round(r.width()*sx),round(r.height()*sy)))
        rect=(self.monitor["x"]+r.x(),self.monitor["y"]+r.y(),r.width(),r.height())
        self.skip_background=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.ShiftModifier)
        self.force_copy=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.ControlModifier)
        self.terminal=True;self.selected.emit(rect,image,self.capture_mode.currentText())
    def cancel(self):
        if not self.terminal:self.terminal=True;self.cancelled.emit()
    def closeEvent(self,event):
        if self.magnifier:self.magnifier.stop()
        self.cancel();super().closeEvent(event)
