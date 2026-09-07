"""Zoomable, scrolling source-time tracks shared by Studio preview and export."""
from . import ui_scale as ui
import copy,math,time
from PySide6.QtCore import Qt, Signal, QRectF, QSignalBlocker,QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget, QDialog, QFormLayout, QDoubleSpinBox, QDialogButtonBox,QCheckBox,QScrollBar

SCROLLBAR_STYLE='''
QScrollBar { background:transparent;border:none; }
QScrollBar:horizontal { height:10px;margin:0; }
QScrollBar:vertical { width:10px;margin:0; }
QScrollBar::handle { background:palette(mid);border-radius:4px;min-width:28px;min-height:28px; }
QScrollBar::handle:hover { background:palette(placeholder-text); }
QScrollBar::add-line,QScrollBar::sub-line { width:0;height:0;border:none; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
'''

from .timeline_zooms import ZoomActions


class Timeline(QWidget,ZoomActions):
    seek=Signal(int)
    seek_started=Signal()
    seek_finished=Signal()
    edited=Signal()
    editing_focus=Signal()
    zoom_changed=Signal(int)
    cut_mode_changed=Signal(bool)
    selection_changed=Signal()
    source_changed=Signal(QImage)
    ZOOM_Y=property(lambda self:ui.px(32))
    VIDEO_Y=property(lambda self:ui.px(64))
    VIDEO_HEIGHT=property(lambda self:ui.px(48))

    def __init__(self,parent=None):
        super().__init__(parent);self.duration=0.;self.position=0.;self.start=0.;self.end=0.;self.fps=30.
        self.zooms=[];self.cuts=[];self.splits=[];self.cut_mode=False;self.selected=None;self.drag=None;self.before=None;self.last_pointer=None
        self.source_image=QImage();self.focus_editor=None;self.thumbnails=None;self.zoom_level=0;self.playing=False;self.internal_scroll=False;self.manual_scroll_until=0.
        self.scroll=QScrollBar(Qt.Orientation.Horizontal,self);self.scroll.setAccessibleName('Timeline horizontal scroll');self.scroll.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.scroll.valueChanged.connect(self.scrolled)
        ui.set(self.scroll,"setStyleSheet",SCROLLBAR_STYLE)
        self.auto_scroll=QTimer(self);self.auto_scroll.setInterval(40);self.auto_scroll.timeout.connect(self.drag_scroll)
        ui.set(self,"setFixedHeight",136);self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip('B selects the cut tool; Ctrl+B splits at the playhead. Select a clip and drag its edges to trim or restore frames. Escape cancels a drag or returns to selection. Ctrl+wheel zooms; wheel scrolls. Delete removes a selected clip or zoom, or restores a cut.')

    def clips(self):
        from .video_splits import clips
        return clips(self.start,self.end or self.duration,self.cuts,self.splits)

    def set_cut_mode(self,enabled):
        if self.drag:self.finish_drag(cancel=True)
        self.cut_mode=bool(enabled);self.cut_mode_changed.emit(self.cut_mode);self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor);self.update()

    def split_at(self,seconds=None):
        if self.drag:self.finish_drag()
        candidate=round((self.position if seconds is None else seconds)*self.fps)/self.fps
        minimum=1/self.fps-1e-7
        if not any(candidate-a>=minimum and b-candidate>=minimum for a,b in self.clips()):return False
        self.editing_focus.emit();self.splits.append(candidate);self.splits.sort();self.select(None);self.edited.emit();self.update();return True

    def delete_selected(self):
        if not self.selected:return
        if self.drag:self.finish_drag()
        kind,i=self.selected
        if kind=='zoom':self.zooms.pop(i)
        elif kind=='cut':self.cuts.pop(i)
        elif kind=='clip':self.cuts.append(list(self.clips()[i]))
        else:return
        self.editing_focus.emit();self.select(None);self.edited.emit();self.update()

    def contextMenuEvent(self,event):
        from PySide6.QtWidgets import QMenu
        menu=QMenu(self);found=self.hit(event.pos())
        if found and found[0]=='zoom':
            self.zoom_menu(menu,found[1]);menu.exec(event.globalPos());menu.deleteLater();return
        menu.addAction('Split at playhead',lambda:self.split_at())
        near=next((s for s in self.splits if abs(self.x(s)-event.pos().x())<8),None)
        if near is not None:
            def merge():self.splits.remove(near);self.select(None);self.edited.emit();self.update()
            menu.addAction('Remove split',merge)
        if self.selected and self.selected[0]=='clip':menu.addAction('Delete clip',self.delete_selected)
        menu.exec(event.globalPos());menu.deleteLater()

    def set_source(self,path):
        from .timeline_thumbnails import ThumbnailCache
        if self.thumbnails:self.thumbnails.close()
        self.thumbnails=ThumbnailCache(path,self);self.thumbnails.changed.connect(self.update);self.thumbnails.failed.connect(lambda msg:self.setToolTip(msg));self.update()

    def set_source_image(self,image):
        self.source_image=QImage(image);self.source_changed.emit(self.source_image)
        if self.focus_editor:self.focus_editor.set_image(image)
        self.update()

    def plot_rect(self):return QRectF(ui.px(16),0,max(1,self.width()-ui.px(32)),ui.px(120))
    def offset(self):return self.scroll.value()/1000
    def max_zoom(self):return max(1.,self.duration*self.fps*8/self.plot_rect().width())
    def factor(self):return self.max_zoom()**(self.zoom_level/100)
    def visible_span(self):return max(.001,self.duration/self.factor())
    def pixels_per_second(self):return self.plot_rect().width()/self.visible_span()
    def x(self,seconds):return self.plot_rect().left()+(seconds-self.offset())*self.pixels_per_second()
    def time_at(self,x):return max(0,min(self.duration,self.offset()+(x-self.plot_rect().left())/self.pixels_per_second()))

    def set_zoom(self,value,anchor=None):
        value=max(0,min(100,round(value)))
        if value==self.zoom_level:return
        anchor=self.x(self.position) if anchor is None and self.offset()<=self.position<=self.offset()+self.visible_span() else self.plot_rect().center().x() if anchor is None else anchor
        before=self.time_at(anchor);self.zoom_level=value;self.update_scroll(before-(anchor-self.plot_rect().left())/self.pixels_per_second());self.manual_scroll_until=time.monotonic()+2;self.zoom_changed.emit(value);self.update()

    def update_scroll(self,offset=None):
        offset=self.offset() if offset is None else offset;self.internal_scroll=True
        self.scroll.setRange(0,max(0,round((self.duration-self.visible_span())*1000)))
        self.scroll.setPageStep(max(1,round(self.visible_span()*1000)));self.scroll.setSingleStep(max(1,round(self.visible_span()*100)))
        self.scroll.setValue(round(offset*1000));self.scroll.setEnabled(self.scroll.maximum()>0);self.scroll.setVisible(self.scroll.maximum()>0);self.internal_scroll=False

    def scrolled(self,*_):
        if not self.internal_scroll:self.manual_scroll_until=time.monotonic()+2
        self.update()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.scroll.setGeometry(ui.px(12),ui.px(122),max(1,self.width()-ui.px(24)),ui.px(12));self.update_scroll();self.update()

    def set_frame_rate(self,fps):
        if fps and float(fps)>0:self.fps=float(fps);self.update_scroll();self.update()

    def set_duration(self,milliseconds):self.duration=max(0,milliseconds/1000);self.update_scroll();self.update()
    def set_playing(self,playing):self.playing=playing
    def set_position(self,milliseconds):
        self.position=milliseconds/1000
        if self.playing and time.monotonic()>self.manual_scroll_until and not self.drag and not self.scroll.isSliderDown() and not (self.offset()<=self.position<=self.offset()+self.visible_span()):self.update_scroll(self.position-self.visible_span()*.1)
        self.update()

    def thumbnail_tiles(self):
        if self.duration<=0:return []
        aspect=self.source_image.width()/self.source_image.height() if not self.source_image.isNull() else 16/9
        width=max(48,min(150,self.VIDEO_HEIGHT*aspect));frames=max(1,math.ceil(width/self.pixels_per_second()*self.fps));step=frames/self.fps
        edges=[0]+[s for s in self.splits if 0<s<self.duration]+[self.duration];tiles=[];left=self.offset();right=left+self.visible_span();groups=[]
        for a,b in zip(edges,edges[1:]):
            small=(b-a)*self.pixels_per_second()<48
            if small and groups and groups[-1][2]:groups[-1]=(groups[-1][0],b,True)
            else:groups.append((a,b,small))
        for a,b,_ in groups:
            if b<left or a>right:continue
            first=max(0,math.floor((left-a)/step));last=min(math.ceil((b-a)/step),math.ceil((right-a)/step)+1)
            tiles.extend((round((a+i*step)*1000),a+i*step,min(b,a+(i+1)*step)) for i in range(first,last))
        return tiles

    def bounds(self,kind,index=0):
        if kind=='trim':return self.start,self.end or self.duration
        if kind=='zoom':return self.zooms[index]['start'],self.zooms[index]['end']
        if kind=='clip':return self.clips()[index]
        return self.cuts[index]

    def clip_rect(self,kind,index=0):
        a,b=self.bounds(kind,index);y=self.ZOOM_Y if kind=='zoom' else self.VIDEO_Y;height=ui.px(24) if kind=='zoom' else self.VIDEO_HEIGHT
        return QRectF(self.x(a),y,max(2,self.x(b)-self.x(a)),height)

    def paintEvent(self,event):
        if self.thumbnails:self.thumbnails.request([key for key,_,_ in self.thumbnail_tiles()])
        from .timeline_paint import paint
        paint(self)

    def hit(self,point):
        if not self.plot_rect().contains(point):return None
        if self.selected and self.selected[0]=='clip' and self.selected[1]<len(self.clips()):
            i=self.selected[1];r=self.clip_rect('clip',i)
            if r.adjusted(-4,0,4,0).contains(point):
                distances=[(abs(point.x()-r.left()),'start'),(abs(point.x()-r.right()),'end')]
                distance,edge=min(distances)
                if distance<9:return 'clip',i,edge
        for kind,count in [('zoom',len(self.zooms)),('cut',len(self.cuts)),('trim',1)]:
            for i in reversed(range(count)):
                r=self.clip_rect(kind,i)
                if r.adjusted(-4,0,4,0).contains(point):
                    edge='start' if abs(point.x()-r.left())<9 else 'end' if abs(point.x()-r.right())<9 else 'move'
                    if kind=='trim' and edge=='move' and (self.splits or self.cuts):
                        for index,(a,b) in enumerate(self.clips()):
                            if a<=self.time_at(point.x())<b:return 'clip',index,'select'
                    return kind,i,edge
        return None

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self.plot_rect().contains(event.position()):return
        self.setFocus();point=event.position();self.drag=None;self.before=(self.start,self.end,copy.deepcopy(self.zooms),copy.deepcopy(self.cuts));found=self.hit(point)
        if self.cut_mode and self.VIDEO_Y<=point.y()<=self.VIDEO_Y+self.VIDEO_HEIGHT:
            self.split_at(self.time_at(point.x()));self.before=None;return
        if not found and self.ZOOM_Y<=point.y()<=self.ZOOM_Y+ui.px(24):
            gap=self.zoom_gap(self.time_at(point.x()))
            index=self.add_zoom_at(self.time_at(point.x()))
            if index is not None:
                self.drag=('zoom',index,'create',self.zooms[index]['start'],*self.bounds('zoom',index),*gap)
                self.last_pointer=point;self.auto_scroll.start();self.update()
            return
        if found:
            kind,i,edge=found;new_selection=self.selected!=(kind,i);self.select((kind,i))
            if kind=='zoom' and new_selection:self.seek.emit(round(sum(self.bounds(kind,i))*500))
            if kind=='clip' and edge=='select':self.editing_focus.emit();self.seek.emit(round(self.time_at(point.x())*1000));self.update();return
            if kind!='trim' or edge!='move':
                self.editing_focus.emit();self.drag=(kind,i,edge,self.time_at(point.x()),*self.bounds(kind,i))
        else:self.select(None)
        if self.drag is None:self.seek_started.emit();self.drag=('seek',);self.seek.emit(round(self.time_at(point.x())*1000))
        self.last_pointer=point;self.auto_scroll.start();self.update()

    def apply_drag(self,point):
        if not self.drag:return
        if self.drag[0]=='seek':self.seek.emit(round(self.time_at(point.x())*1000));return
        kind,i,edge,origin,a,b=self.drag[:6];delta=self.time_at(point.x())-origin;minimum=min(1/self.fps,self.duration)
        if kind=='clip':
            from .video_splits import trim_clip
            cuts,bounds=trim_clip(self.start,self.end or self.duration,self.before[3],self.splits,(a,b),edge,(a if edge=='start' else b)+delta,self.fps)
            self.cuts[:]=cuts;anchor=sum(bounds)/2
            self.select(next((('clip',index) for index,(x,y) in enumerate(self.clips()) if x<=anchor<y),None))
            self.seek.emit(round((bounds[0] if edge=='start' else max(bounds[0],bounds[1]-minimum))*1000))
            self.edited.emit();self.update();return
        if edge=='create':
            if abs(self.x(origin)-point.x())<4:return
            lo,hi=self.drag[6:];current=round(self.time_at(point.x())*self.fps)/self.fps
            a=max(lo,min(origin,current));b=min(hi,max(origin,current))
            if b-a<minimum:b=min(hi,a+minimum);a=max(lo,b-minimum)
        elif edge=='start':a=max(0,min(b-minimum,a+delta))
        elif edge=='end':b=min(self.duration,max(a+minimum,b+delta))
        else:delta=max(-a,min(self.duration-b,delta));a+=delta;b+=delta
        if kind=='trim':self.start=a;self.end=b
        elif kind=='zoom':
            if edge!='create':
                lo,hi=self.zoom_limits(i);snap=8/self.pixels_per_second()
                if edge=='start':a=max(lo,a);a=lo if abs(a-lo)<snap else a
                elif edge=='end':b=min(hi,b);b=hi if abs(b-hi)<snap else b
                else:
                    length=b-a;a=max(lo,min(hi-length,a));b=a+length
                    if abs(a-lo)<snap:a=lo;b=a+length
                    elif abs(b-hi)<snap:b=hi;a=b-length
            self.zooms[i].update(start=a,end=b)
        else:self.cuts[i]=[a,b]
        self.edited.emit();self.update()

    def mouseMoveEvent(self,event):
        self.last_pointer=event.position()
        if self.drag:self.apply_drag(event.position())
        else:
            found=self.hit(event.position());self.setCursor(Qt.CursorShape.CrossCursor if self.cut_mode else Qt.CursorShape.SizeHorCursor if found and found[2] in ('start','end') else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self,event):
        if not self.drag:self.last_pointer=None;self.update()
        super().leaveEvent(event)

    def drag_scroll(self):
        if not self.drag or self.last_pointer is None:return
        x=self.last_pointer.x();direction=-1 if x<28 else 1 if x>self.width()-28 else 0
        if direction:self.update_scroll(self.offset()+direction*18/self.pixels_per_second());self.apply_drag(self.last_pointer)

    def finish_drag(self,cancel=False):
        self.auto_scroll.stop();seek=self.drag and self.drag[0]=='seek'
        if cancel and self.before and not seek:
            self.start,self.end,zooms,cuts=self.before;self.zooms[:]=zooms;self.cuts[:]=cuts
            if self.selected and self.selected[0]=="zoom" and self.selected[1]>=len(self.zooms):self.select(None)
            if self.drag and self.drag[0]=='clip':self.select(('clip',self.drag[1]))
            self.edited.emit()
        self.drag=None;self.before=None
        if seek:self.seek_finished.emit()
        self.update()

    def mouseReleaseEvent(self,event):self.finish_drag()

    def wheelEvent(self,event):
        delta=event.pixelDelta();angle=event.angleDelta()
        if event.modifiers()&Qt.KeyboardModifier.ControlModifier:self.set_zoom(self.zoom_level+(angle.y()/120*8 if angle.y() else delta.y()/8),event.position().x())
        else:
            pixels=delta.x() or delta.y() or (angle.x() or angle.y())/120*90
            self.update_scroll(self.offset()-pixels/self.pixels_per_second());self.manual_scroll_until=time.monotonic()+2;self.update()
        event.accept()

    def mouseDoubleClickEvent(self,event):
        if not self.selected or self.selected[0]!="zoom":return
        if self.drag:self.finish_drag()
        zoom=self.zooms[self.selected[1]];dialog=QDialog(self);dialog.setWindowTitle("Edit zoom")
        self.editing_focus.emit();self.seek.emit(round((zoom["start"]+zoom["end"])*500))
        from .zoom_focus import ZoomFocus
        form=QFormLayout(dialog);controls={}
        focus=ZoomFocus(self.source_image);focus.set_values(zoom["scale"],zoom.get("x",.5),zoom.get("y",.5));self.focus_editor=focus
        form.addRow(focus)
        for key,label,low,high in [("start","Start (seconds)",0,self.duration),("end","End (seconds)",0,self.duration),("scale","Magnification",1,5),("x","Horizontal focus (%)",0,100),("y","Vertical focus (%)",0,100)]:
            control=QDoubleSpinBox();control.setRange(low,high);control.setDecimals(2);control.setValue(zoom.get(key,.5)*(100 if key in ("x","y") else 1));form.addRow(label,control);controls[key]=control
        follow=QCheckBox("Follow cursor");follow.setChecked(zoom.get("follow",False));form.addRow(follow)
        def visual(scale,x,y):
            for key,value in (("scale",scale),("x",x*100),("y",y*100)):
                with QSignalBlocker(controls[key]):controls[key].setValue(value)
        focus.changed.connect(visual)
        def numeric(*args):focus.set_values(controls["scale"].value(),controls["x"].value()/100,controls["y"].value()/100)
        for key in ("scale","x","y"):controls[key].valueChanged.connect(numeric)
        def tracking(checked):
            focus.setEnabled(not checked)
            for key in ("x","y"):controls[key].setEnabled(not checked)
        follow.toggled.connect(tracking);tracking(follow.isChecked())
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec() and controls["end"].value()>controls["start"].value():
            zoom.update({k:c.value()/(100 if k in ("x","y") else 1) for k,c in controls.items()});zoom["follow"]=follow.isChecked();self.edited.emit();self.update()
        self.focus_editor=None;dialog.deleteLater()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and self.drag:self.finish_drag(cancel=True);event.accept();return
        if event.key()==Qt.Key.Key_Escape and self.cut_mode:self.set_cut_mode(False);return
        if event.key()==Qt.Key.Key_B:
            if event.modifiers()&Qt.KeyboardModifier.ControlModifier:
                if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:self.split_zoom_at_playhead()
                else:self.split_at()
            elif not event.modifiers():self.set_cut_mode(True)
            else:super().keyPressEvent(event)
            return
        if event.modifiers()&Qt.KeyboardModifier.ControlModifier and event.key()==Qt.Key.Key_0:self.set_zoom(0);return
        if event.key() in (Qt.Key.Key_Plus,Qt.Key.Key_Equal,Qt.Key.Key_Minus):self.set_zoom(self.zoom_level+(10 if event.key()!=Qt.Key.Key_Minus else -10));return
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and self.selected:
            self.delete_selected()
        elif event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            self.editing_focus.emit();step=1 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1/self.fps
            self.seek.emit(round(max(0,min(self.duration,self.position+step*(1 if event.key()==Qt.Key.Key_Right else -1)))*1000))
        else:super().keyPressEvent(event)

    def shutdown(self):
        self.auto_scroll.stop()
        if self.thumbnails:self.thumbnails.close()
    def closeEvent(self,event):self.shutdown();super().closeEvent(event)
