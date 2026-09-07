"""Adjustable, transactional image cropping and canvas expansion."""
from . import ui_scale as ui
from PySide6.QtCore import Qt,QRectF,QPointF,QSizeF,QSize
from PySide6.QtGui import QColor,QPainterPath,QPen,QKeySequence,QShortcut
from PySide6.QtWidgets import QToolBar,QDoubleSpinBox,QLabel,QWidget,QSizePolicy,QPushButton,QToolButton,QMenu,QApplication
from .controls import Choice


def background_color(image):
    """Use a uniform image border for expansion; otherwise preserve transparency."""
    points=[]
    for i in range(16):
        x=round(i*(image.width()-1)/15);y=round(i*(image.height()-1)/15)
        points.extend((image.pixelColor(x,0),image.pixelColor(x,image.height()-1),image.pixelColor(0,y),image.pixelColor(image.width()-1,y)))
    if not points:return QColor(Qt.GlobalColor.transparent)
    colors=[p.rgba() for p in points];value=max(set(colors),key=colors.count)
    return QColor.fromRgba(value) if colors.count(value)>=len(colors)*.8 else QColor(Qt.GlobalColor.transparent)


def resized(rect,handle,point,ratio=None):
    l,t,r,b=rect.left(),rect.top(),rect.right(),rect.bottom()
    if 'l' in handle:l=min(point.x(),r-2)
    if 'r' in handle:r=max(point.x(),l+2)
    if 't' in handle:t=min(point.y(),b-2)
    if 'b' in handle:b=max(point.y(),t+2)
    if ratio:
        w,h=r-l,b-t
        if handle in ('l','r'):
            h=w/ratio;t=rect.center().y()-h/2;b=t+h
        elif handle in ('t','b'):
            w=h*ratio;l=rect.center().x()-w/2;r=l+w
        else:
            w=max(w,h*ratio);h=w/ratio
            if 'l' in handle:l=r-w
            else:r=l+w
            if 't' in handle:t=b-h
            else:b=t+h
    return QRectF(QPointF(l,t),QPointF(r,b))


class CropSession:
    def __init__(self,editor):
        self.editor=editor;self.original=editor.snapshot();self.rect=QRectF(editor.base.rect());self.drag=None;self.transformed=False;self.fill_color=None;self.color_popup=None
        self.draft_pending=editor.draft_timer.isActive();editor.draft_timer.stop();editor.crop_session=self
        self.disabled=[]
        from PySide6.QtGui import QAction
        for action in editor.findChildren(QAction)+editor.findChildren(QShortcut):
            self.disabled.append((action,action.isEnabled()));action.setEnabled(False)
        self.hidden=[bar for bar in editor.findChildren(QToolBar) if not bar.isHidden()]
        for bar in self.hidden:bar.hide()
        self.menu_visible=editor.menuBar().isVisible();editor.menuBar().hide();editor.scene.clearSelection()
        self.top=QToolBar('Crop controls',editor);self.top.setMovable(False);ui.set(self.top,"setStyleSheet",'QToolBar QLabel { background:transparent; }');editor.addToolBar(self.top)
        self.top.addWidget(QLabel('Crop  '));self.aspect=Choice();self.aspect.addItems(['Freeform','Original','1:1','16:9','9:16','4:3','3:2','5:4','Custom']);self.aspect.setAccessibleName('Crop aspect ratio');self.top.addWidget(self.aspect)
        self.ratio_fields=[]
        for label in ('width','height'):
            spin=QDoubleSpinBox();spin.setRange(.01,100000);spin.setDecimals(2);spin.setKeyboardTracking(False);spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons);ui.set(spin,"setFixedWidth",60);spin.setAccessibleName('Aspect ratio '+label);self.top.addWidget(spin);self.ratio_fields.append(spin)
        self.top.addAction('⇄',self.swap).setToolTip('Swap width and height')
        self.fill_button=QToolButton();ui.set(self.fill_button,"setIconSize",QSize(24,24));self.fill_button.setAccessibleName('Canvas fill');self.fill_button.setToolTip('Canvas expansion fill');self.fill_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.fill_menu=QMenu(self.fill_button);self.fill_auto=self.fill_menu.addAction('Automatic',lambda:self.set_fill(None));self.fill_transparent=self.fill_menu.addAction('Transparent',lambda:self.set_fill(QColor(Qt.GlobalColor.transparent)));self.fill_menu.addSeparator();self.fill_menu.addAction('Custom color…',self.pick_fill)
        for action in (self.fill_auto,self.fill_transparent):action.setCheckable(True)
        self.fill_button.setMenu(self.fill_menu);self.top.addWidget(self.fill_button)
        self.top.addSeparator();self.top.addAction('↻',self.rotate).setToolTip('Rotate clockwise');self.top.addAction('⇋',lambda:self.flip(False)).setToolTip('Flip horizontally');self.top.addAction('⇅',lambda:self.flip(True)).setToolTip('Flip vertically')
        self.top.addSeparator();self.top.addWidget(QLabel('Image size: '));self.size_button=QPushButton();self.size_button.setAccessibleName('Crop image size');self.size_button.clicked.connect(self.open_size);self.top.addWidget(self.size_button)
        from .crop_controls import CropSizePopup,SnapCheckBox
        self.size_popup=CropSizePopup(self);self.dimensions=self.size_popup.dimensions
        spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);self.top.addWidget(spacer)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.clicked.connect(self.cancel);self.top.addWidget(self.cancel_button)
        self.apply_button=QPushButton('Crop');self.apply_button.setObjectName('primary');self.apply_button.clicked.connect(self.apply);self.top.addWidget(self.apply_button)
        self.bottom=QToolBar('Crop view controls',editor);self.bottom.setMovable(False);ui.set(self.bottom,"setStyleSheet",'QToolBar QLabel,QCheckBox { background:transparent; }');editor.addToolBar(Qt.ToolBarArea.BottomToolBarArea,self.bottom)
        self.bottom.addAction('Fit',self.fit);self.bottom.addAction('100%',editor.actual_size)
        self.snap=SnapCheckBox('Snap to edges');self.snap.setChecked(editor.store.settings.get('crop_snap',False));self.snap.toggled.connect(self.save_snap);self.bottom.addWidget(self.snap);self.bottom.addWidget(QLabel('  Hold Ctrl to enable snapping'))
        spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);self.bottom.addWidget(spacer);self.reset_button=QPushButton('Revert to Original');self.reset_button.clicked.connect(self.reset);self.bottom.addWidget(self.reset_button)
        self.escape=QShortcut(QKeySequence('Escape'),editor,activated=self.escape_pressed)
        self.aspect.currentTextChanged.connect(self.aspect_changed)
        for spin in self.ratio_fields:spin.editingFinished.connect(self.custom_ratio_changed)
        editor.view.setDragMode(editor.view.DragMode.NoDrag);editor.view.setCursor(Qt.CursorShape.ArrowCursor);self.sync();self.fit();editor.view.setFocus()
    def escape_pressed(self):
        popup=QApplication.activePopupWidget()
        if popup:popup.close()
        else:self.cancel()
    def open_size(self):
        if self.size_popup.isVisible():self.size_popup.close();return
        from .crop_controls import show_below
        self.sync();show_below(self.size_popup,self.size_button,self.editor)
    def set_fill(self,color):
        if self.editor.crop_session is not self:return
        self.fill_color=QColor(color) if color is not None else None;self.sync()
    def resolved_fill(self,target=None):
        from .images import image_color_space,convert_color
        source_space=image_color_space(self.editor.base);target=target or source_space
        if self.fill_color is not None:return convert_color(self.fill_color,target)
        color=background_color(self.editor.base)
        return source_space.transformationToColorSpace(target).map(color) if source_space!=target else color
    def pick_fill(self):
        from .color_picker import ColorPicker,color_text
        from .crop_controls import show_below
        color=self.resolved_fill(self.editor.paint_space());popup=ColorPicker(color_text(color),self.editor.store,self.editor);self.color_popup=popup
        popup.changed.connect(lambda value:self.set_fill(QColor(value)));popup.screen_requested.connect(self.sample_fill);show_below(popup,self.fill_button,self.editor)
    def sample_fill(self):
        from .color_picker import sample_screen
        from .widgets import background
        from PySide6.QtCore import QTimer
        def done(value):
            if self.editor.crop_session is not self:return
            import re
            match=re.search(r'#[0-9a-fA-F]{6}',value.decode(errors='replace'))
            if match:self.set_fill(QColor(match.group()))
            self.pick_fill()
        def failed(message):
            if self.editor.crop_session is self:self.editor.statusBar().showMessage(f'Could not pick a fill color: {message}');self.pick_fill()
        QTimer.singleShot(150,lambda:background(sample_screen,done,failed) if self.editor.crop_session is self else None)
    def custom_ratio_changed(self):
        if self.editor.crop_session is not self:return
        if self.aspect.currentText()!='Custom':return
        self.rect.setHeight(self.rect.width()/self.ratio());self.sync()
    def save_snap(self,value):
        old=self.editor.store.settings.get('crop_snap',False);self.editor.store.settings['crop_snap']=value
        try:self.editor.store.save_settings()
        except Exception as exc:
            self.editor.store.settings['crop_snap']=old;self.snap.blockSignals(True);self.snap.setChecked(old);self.snap.blockSignals(False);self.editor.statusBar().showMessage(f'Could not save snapping preference: {exc}')
    def ratio(self):
        value=self.aspect.currentText()
        if value=='Freeform':return None
        if value=='Custom':return self.ratio_fields[0].value()/self.ratio_fields[1].value()
        if value=='Original':return self.editor.base.width()/self.editor.base.height()
        a,b=map(float,value.split(':'));return a/b
    def sync(self):
        self.rect=QRectF(self.rect.toRect())
        for spin,value in zip(self.dimensions,(self.rect.width(),self.rect.height())):
            spin.blockSignals(True);spin.setValue(round(value));spin.blockSignals(False)
        self.size_button.setText(f'{round(self.rect.width())} × {round(self.rect.height())} px ▾')
        value=self.aspect.currentText()
        if value!='Custom':
            if value=='Freeform':values=(1,1)
            elif value=='Original':
                import math
                w,h=self.editor.base.width(),self.editor.base.height();divisor=math.gcd(w,h);values=(w/divisor,h/divisor)
            else:values=map(float,value.split(':'))
            for spin,number in zip(self.ratio_fields,values):spin.setValue(number)
        for spin in self.ratio_fields:
            spin.setEnabled(value=='Custom')
            if value=='Freeform':spin.lineEdit().clear()
        self.fill_auto.setChecked(self.fill_color is None);self.fill_transparent.setChecked(self.fill_color is not None and self.fill_color.alpha()==0)
        from .crop_controls import fill_icon
        color=self.resolved_fill(self.editor.paint_space());self.fill_button.setIcon(fill_icon(color))
        valid=2<=self.rect.width()<=100000 and 2<=self.rect.height()<=100000 and self.rect.width()*self.rect.height()<=120_000_000
        self.apply_button.setEnabled(valid);self.editor.statusBar().showMessage(f'{round(self.rect.width())} × {round(self.rect.height())} px · Enter to crop · Escape to cancel' if valid else 'Crop is too large. The limit is 120 megapixels.')
        self.editor.view.viewport().update()
    def scene_bounds(self):
        bounds=QRectF(self.editor.base.rect()).united(self.rect);pad=max(32,min(bounds.width(),bounds.height())*.16)
        return bounds.adjusted(-pad,-pad,pad,pad)
    def fit(self):
        self.editor.scene.setSceneRect(self.scene_bounds());self.editor.view.fitInView(self.scene_bounds(),Qt.AspectRatioMode.KeepAspectRatio);self.editor.view.sync_composition_bounds()
    def aspect_changed(self):
        if self.aspect.currentText()=='Custom':
            import math
            w,h=max(2,round(self.rect.width())),max(2,round(self.rect.height()));divisor=math.gcd(w,h)
            for spin,number in zip(self.ratio_fields,(w/divisor,h/divisor)):spin.setValue(number)
        ratio=self.ratio()
        if ratio:
            center=self.rect.center();w=min(self.rect.width(),self.rect.height()*ratio);self.rect.setSize(QSizeF(w,w/ratio));self.rect.moveCenter(center)
        self.sync()
    def size_changed(self,index):
        if self.editor.crop_session is not self:return
        value=self.dimensions[index].value();ratio=self.ratio()
        if index==0:
            self.rect.setWidth(value)
            if ratio:self.rect.setHeight(value/ratio)
        else:
            self.rect.setHeight(value)
            if ratio:self.rect.setWidth(value*ratio)
        self.sync();self.editor.scene.setSceneRect(self.scene_bounds())
    def swap(self):
        w,h=self.rect.width(),self.rect.height();center=self.rect.center();self.rect.setWidth(h);self.rect.setHeight(w);self.rect.moveCenter(center)
        value=self.aspect.currentText();self.transpose_ratio()
        if value=='Original':self.aspect.blockSignals(True);self.aspect.setCurrentText('Freeform');self.aspect.blockSignals(False)
        self.sync()
    def transpose_ratio(self):
        value=self.aspect.currentText()
        if value=='Custom':
            w,h=[spin.value() for spin in self.ratio_fields];self.ratio_fields[0].setValue(h);self.ratio_fields[1].setValue(w)
        elif ':' in value:
            value=':'.join(reversed(value.split(':')));self.aspect.blockSignals(True)
            if self.aspect.findText(value)<0:self.aspect.addItem(value)
            self.aspect.setCurrentText(value);self.aspect.blockSignals(False)
    def handles(self):
        r=self.rect;cx,cy=r.center().x(),r.center().y()
        return {'lt':r.topLeft(),'t':QPointF(cx,r.top()),'rt':r.topRight(),'r':QPointF(r.right(),cy),'rb':r.bottomRight(),'b':QPointF(cx,r.bottom()),'lb':r.bottomLeft(),'l':QPointF(r.left(),cy)}
    def press(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        point=self.editor.view.mapToScene(event.position().toPoint());threshold=12/max(.01,self.editor.view.transform().m11())
        handle=next((key for key,value in self.handles().items() if (point-value).manhattanLength()<threshold),None)
        self.drag=(handle or ('move' if self.rect.contains(point) else 'new'),point,QRectF(self.rect));self.editor.view.setFocus();event.accept()
    def targets(self):
        rects=[QRectF(self.editor.base.rect())]+[o.content_bounds() for o in self.editor.objects if o.props['kind']=='image']
        return [v for r in rects for v in (r.left(),r.right())],[v for r in rects for v in (r.top(),r.bottom())]
    def snap_point(self,point):
        xs,ys=self.targets();threshold=8/max(.01,self.editor.view.transform().m11())
        def nearest(value,values):
            best=min(values,key=lambda other:abs(other-value));return best if abs(best-value)<=threshold else value
        return QPointF(nearest(point.x(),xs),nearest(point.y(),ys))
    def move(self,event):
        point=self.editor.view.mapToScene(event.position().toPoint())
        if not self.drag:
            threshold=12/max(.01,self.editor.view.transform().m11());handle=next((key for key,value in self.handles().items() if (point-value).manhattanLength()<threshold),None)
            cursor={'lt':Qt.CursorShape.SizeFDiagCursor,'rb':Qt.CursorShape.SizeFDiagCursor,'rt':Qt.CursorShape.SizeBDiagCursor,'lb':Qt.CursorShape.SizeBDiagCursor,'l':Qt.CursorShape.SizeHorCursor,'r':Qt.CursorShape.SizeHorCursor,'t':Qt.CursorShape.SizeVerCursor,'b':Qt.CursorShape.SizeVerCursor}.get(handle,Qt.CursorShape.SizeAllCursor if self.rect.contains(point) else Qt.CursorShape.CrossCursor)
            self.editor.view.setCursor(cursor);return
        handle,start,original=self.drag;snapping=self.snap.isChecked() or bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
        if handle=='move':
            delta=point-start
            if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:delta=QPointF(delta.x(),0) if abs(delta.x())>=abs(delta.y()) else QPointF(0,delta.y())
            self.rect=original.translated(delta)
            if snapping:
                xs,ys=self.targets();threshold=8/max(.01,self.editor.view.transform().m11())
                dx=min((x-edge for x in xs for edge in (self.rect.left(),self.rect.right()) if abs(x-edge)<=threshold),key=abs,default=0)
                dy=min((y-edge for y in ys for edge in (self.rect.top(),self.rect.bottom()) if abs(y-edge)<=threshold),key=abs,default=0);self.rect.translate(dx,dy)
        else:
            if snapping:point=self.snap_point(point)
            ratio=self.ratio() or (original.width()/max(1,original.height()) if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else None)
            if handle=='new':
                self.rect=QRectF(start,point).normalized()
                if ratio:self.rect.setHeight(self.rect.width()/ratio)
            else:self.rect=resized(original,handle,point,ratio)
        self.sync();event.accept()
    def release(self,event):
        if self.drag:self.move(event);self.drag=None;self.sync();event.accept()
    def key(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.apply();return True
        delta={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}.get(event.key())
        if delta:
            step=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1
            if event.modifiers()&Qt.KeyboardModifier.ControlModifier:self.rect=resized(self.rect,'r' if delta[0] else 'b',self.rect.bottomRight()+QPointF(delta[0]*step,delta[1]*step),self.ratio())
            else:self.rect.translate(delta[0]*step,delta[1]*step)
            self.sync();return True
        return False
    def draw_background(self,painter):
        area=QPainterPath();area.addRect(self.rect);source=QPainterPath();source.addRect(QRectF(self.editor.base.rect()))
        painter.fillPath(area.subtracted(source),self.resolved_fill(self.editor.paint_space()))
    def paint(self,painter,visible):
        painter.save();scale=max(.01,self.editor.view.transform().m11());outside=QPainterPath();outside.addRect(visible);hole=QPainterPath();hole.addRect(self.rect);painter.fillPath(outside.subtracted(hole),QColor(0,0,0,115))
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor('white'),1/scale));painter.drawRect(self.rect)
        painter.setPen(QPen(QColor(255,255,255,95),1/scale))
        for f in (1/3,2/3):
            x=self.rect.left()+self.rect.width()*f;y=self.rect.top()+self.rect.height()*f;painter.drawLine(QPointF(x,self.rect.top()),QPointF(x,self.rect.bottom()));painter.drawLine(QPointF(self.rect.left(),y),QPointF(self.rect.right(),y))
        painter.setPen(QPen(QColor('#626671'),1/scale));painter.setBrush(QColor('white'))
        for point in self.handles().values():painter.drawRoundedRect(QRectF(point.x()-4/scale,point.y()-4/scale,8/scale,8/scale),1/scale,1/scale)
        painter.restore()
    def rotate(self):
        r=self.rect;h=self.editor.base.height();self.editor.rotate();self.rect=QRectF(h-r.bottom(),r.left(),r.height(),r.width());self.transpose_ratio();self.transformed=True;self.sync();self.fit()
    def flip(self,vertical):
        r=self.rect;self.editor.flip(vertical)
        if vertical:r.moveTop(self.editor.base.height()-r.bottom())
        else:r.moveLeft(self.editor.base.width()-r.right())
        self.transformed=True;self.sync()
    def reset(self):
        from .image_original import restore_original
        self.editor.restore(self.original);restore_original(self.editor);self.rect=QRectF(self.editor.base.rect());self.transformed=self.editor.snapshot()!=self.original;self.fill_color=None;self.aspect.blockSignals(True);self.aspect.setCurrentText('Freeform');self.aspect.blockSignals(False);self.sync();self.fit()
    def leave(self):
        self.editor.crop_session=None;self.escape.setEnabled(False);self.escape.deleteLater()
        from shiboken6 import isValid
        for popup in (self.size_popup,self.color_popup):
            if popup is not None and isValid(popup):popup.close();popup.deleteLater()
        for bar in (self.top,self.bottom):self.editor.removeToolBar(bar);bar.deleteLater()
        for action,enabled in self.disabled:
            if isValid(action):action.setEnabled(enabled)
        for bar in self.hidden:bar.show()
        self.editor.menuBar().setVisible(self.menu_visible);self.editor.set_tool('select');self.editor.update_canvas_bounds();self.editor.fit()
    def cancel(self):
        if self.editor.crop_session is not self:return
        self.editor.restore(self.original);self.leave()
        if self.draft_pending:self.editor.draft_timer.start(1200)
    def apply(self):
        if self.editor.crop_session is not self or not self.apply_button.isEnabled():return
        changed=self.transformed or self.rect.toRect()!=self.editor.base.rect()
        if self.rect.toRect()!=self.editor.base.rect():
            if self.editor.crop(self.rect.toRect(),expand=True,fill=self.resolved_fill()) is False:return
        self.leave()
        if changed:self.editor.commit()
        elif self.draft_pending:self.editor.draft_timer.start(1200)
