from __future__ import annotations
from . import ui_scale as ui
import time
import shutil
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,Signal,QObject,QRunnable,QThreadPool,QRect,QRectF,QPoint,QPointF,QMimeData,QUrl,QSize
from PySide6.QtGui import QPixmap,QImage,QCursor,QPainter,QPainterPath,QColor,QPen,QFont,QDrag,QKeySequence,QShortcut,QRegion
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,
    QLabel,QDialog,QFormLayout,QSpinBox,QCheckBox,QLineEdit,QListWidget,
    QListWidgetItem,QFileDialog,QDialogButtonBox,QSlider,QMenu,QInputDialog,QStackedWidget,QScrollArea,QGridLayout,QKeySequenceEdit)
from .media_player import MediaPlayer
from .controls import Choice as QComboBox
from . import backend
from .editor import qimage,error
from .images import load_image, save_image,convert_image
from .stitch import ScrollStitcher


from .theme import STYLE


class Signals(QObject):
    done=Signal(object)
    failed=Signal(str)


class Job(QRunnable):
    def __init__(self,func):super().__init__();self.func=func;self.signals=Signals()
    def run(self):
        from shiboken6 import isValid
        try:
            result=self.func()
            if isValid(self.signals):self.signals.done.emit(result)
        except Exception as exc:
            if isValid(self.signals):self.signals.failed.emit(str(exc))


JOBS=set()
def background(func,done,failed):
    job=Job(func);JOBS.add(job)
    def finish(value):
        try:done(value)
        finally:JOBS.discard(job)
    def fail(value):
        try:failed(value)
        finally:JOBS.discard(job)
    job.signals.done.connect(finish);job.signals.failed.connect(fail);QThreadPool.globalInstance().start(job)
    return job


def button(label,slot,primary=False):
    b=QPushButton(label);b.clicked.connect(slot)
    if primary:b.setObjectName("primary")
    return b


def cursor_position():
    # Wayland only updates Qt's pointer position for surfaces receiving events.
    # A compositor focus warp or a pointer in another app can leave it stale.
    if QApplication.platformName()=="wayland":
        try:
            point=backend.hypr("cursorpos");return QPoint(point["x"],point["y"])
        except Exception:pass
    return QCursor.pos()


def place_window(widget,x,y):
    widget.move(int(x),int(y))
    # Wayland intentionally ignores client-side top-level positioning. Hyprland
    # places our own identified window only; no foreign windows are manipulated.
    def move():
        try:
            clients=backend.hypr("clients")
            for c in clients:
                if c.get("pid")==__import__("os").getpid() and c.get("title")==widget.windowTitle():
                    backend.move_window(c['address'],x,y)
                    break
        except Exception:pass
    QTimer.singleShot(120,move)


def place_outside(widget,rect):
    x,y,w,h=rect
    screen=QApplication.screenAt(QPoint(x+w//2,y+h//2)) or QApplication.primaryScreen();bounds=screen.availableGeometry()
    for px,py in [(x+w+12,y),(x-widget.width()-12,y),(x,y+h+12),(x,y-widget.height()-12)]:
        if bounds.contains(QRect(px,py,widget.width(),widget.height())):
            place_window(widget,px,py);return True
    return False


class DragPreview(QLabel):
    activated=Signal()
    drag_started=Signal();drag_finished=Signal(bool,bool)
    def __init__(self,path):super().__init__();self.path=Path(path);self.start=None;self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def mousePressEvent(self,event):self.start=event.position().toPoint()
    def mouseMoveEvent(self,event):
        if self.start and (event.position().toPoint()-self.start).manhattanLength()>10:
            keep=bool(event.modifiers()&Qt.KeyboardModifier.AltModifier)
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.path))]);drag=QDrag(self);drag.setMimeData(mime)
            if self.pixmap():drag.setPixmap(self.pixmap().scaledToWidth(140))
            self.start=None;self.drag_started.emit()
            from .drag import execute
            accepted=execute(drag)
            # A Wayland drop can move keyboard focus to the receiving app.
            # Preserve Alt held when the drag began across that focus change.
            self.drag_finished.emit(accepted,keep or bool(QApplication.queryKeyboardModifiers()&Qt.KeyboardModifier.AltModifier))
    def mouseReleaseEvent(self,event):
        if self.start is not None:self.activated.emit()
        self.start=None


class QuickOverlay(QWidget):
    annotate=Signal(str);pin=Signal(str);dismissed=Signal(str);transform_requested=Signal(str,str);save_all_requested=Signal();close_all_requested=Signal();trash_requested=Signal(str)
    def __init__(self,path,store,index=0):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.path=Path(path);self.store=store;self.setWindowTitle(f"OmniShot Preview {index}")
        self.collapsed=False;self.swipe=QPoint();self.hover_player=None;self.quicklook=None;self.dragging=False;self.target_screen=None;self.copying=False
        self.is_video=self.path.suffix.lower() in (".mp4",".gif",".webm",".mov",".mkv")
        self.content_path=self.path if self.is_video else store.display_image(self.path)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout=QVBoxLayout(self);ui.set(layout,"setContentsMargins",10,10,10,10)
        top=QHBoxLayout();self.title=QLabel("Recording ready" if self.is_video else "Capture ready");ui.set(self.title,"setStyleSheet","font-weight:600");top.addWidget(self.title);top.addStretch()
        from .editor_toolbar import icon
        self.trash_button=button('',lambda:self.trash_requested.emit(str(self.path)));self.trash_button.setIcon(icon('trash'));ui.set(self.trash_button,"setIconSize",QSize(20,20));ui.set(self.trash_button,"setFixedSize",36,36);self.trash_button.setAccessibleName('Move to Trash');self.trash_button.setToolTip('Move capture and automatically saved file to Trash');top.addWidget(self.trash_button)
        top.addWidget(button("×",self.close));layout.addLayout(top)
        self.preview=DragPreview(self.content_path);width=store.settings["overlay_size"];ui.set(self.preview,"setMinimumHeight",110)
        self.preview.activated.connect(lambda:self.annotate.emit(str(self.path)));layout.addWidget(self.preview)
        self.info=QLabel();self.info.setObjectName("muted");layout.addWidget(self.info);self.refresh_content()
        actions=QHBoxLayout()
        entries=[("Edit" if self.is_video else "Annotate",lambda:self.annotate.emit(str(self.path))),("Copy",self.copy),("Save",self.save)]
        if not self.is_video:entries.append(("Pin",lambda:self.pin.emit(str(self.path))))
        for text,slot in entries:actions.addWidget(button(text,slot,text in ("Annotate","Edit")))
        layout.addLayout(actions);ui.set(self,"setFixedWidth",max(335,width+20))
        self.restore_button=button("↑ Show capture",lambda:self.set_collapsed(False));layout.addWidget(self.restore_button);self.restore_button.hide()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.auto_close)
        self.preview.drag_started.connect(self.drag_started);self.preview.drag_finished.connect(self.drag_finished)
        if store.settings["overlay_timeout"]:self.timer.start(store.settings["overlay_timeout"]*1000)
        self.index=index
        ui.watch(self,"rescale_preview")
        from .overlay_keys import OverlayKeys
        self.hover_keys=OverlayKeys(self);self.hover_keys.activated.connect(self.keyboard_action)
        self.setToolTip("While hovered: Ctrl+C copy · Ctrl+S save · Ctrl+E annotate · Ctrl+P pin · Ctrl+W close · Space preview")
    def rescale_preview(self):
        self.refresh_content();self.adjustSize()
        if self.isVisible():QTimer.singleShot(0,lambda:self.position_on(self.target_screen or self.screen()))
    def drag_started(self):
        self.dragging=True;self.timer.stop();self.hover_keys.stop()
    def drag_finished(self,accepted,keep):
        self.dragging=False
        if accepted and self.store.settings.get("overlay_close_after_drag",True) and not keep:self.close()
        else:self.resume_timer();self.rearm_hover_keys()
    def rearm_hover_keys(self):
        from shiboken6 import isValid
        if isValid(self) and self.isVisible() and self.underMouse() and not (self.collapsed or self.dragging or self.copying or self.quicklook):self.hover_keys.start()
    def resume_timer(self):
        if self.isVisible() and not self.dragging and not self.copying and not self.underMouse() and self.store.settings["overlay_timeout"]:
            self.timer.start(self.store.settings["overlay_timeout"]*1000)
    def auto_close(self):
        if self.copying or self.dragging or self.quicklook or QApplication.activeModalWidget():self.resume_timer();return
        if self.store.settings.get("overlay_auto_action","close")=="save":
            try:self.export_to()
            except Exception as exc:error(self,exc);return
        self.close()
    def keyboard_action(self,action):
        if action=="copy":self.copy()
        elif action=="save":self.save()
        elif action=="close":self.close()
        elif action=="annotate":self.annotate.emit(str(self.path))
        elif action=="pin" and not self.is_video:self.pin.emit(str(self.path))
        elif action=="preview":self.preview_large()
        QTimer.singleShot(0,self.rearm_hover_keys)
    def refresh_content(self):
        self.trash_button.setVisible(bool(self.store.metadata(self.path).get('autosaved_files')))
        self.content_path=self.path if self.is_video else self.store.display_image(self.path);self.preview.path=self.content_path
        pix=QPixmap.fromImage(convert_image(load_image(self.content_path)));duration=""
        if self.is_video:
            import cv2
            cap=cv2.VideoCapture(str(self.path));valid,frame=cap.read()
            if valid:pix=QPixmap.fromImage(qimage(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)));duration=f" · {cap.get(cv2.CAP_PROP_FRAME_COUNT)/(cap.get(cv2.CAP_PROP_FPS) or 30):.1f} s"
            cap.release()
        self.thumbnail=pix.scaled(ui.px(self.store.settings["overlay_size"]),ui.px(185),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation);self.preview.setPixmap(self.thumbnail)
        self.info.setText(f"{pix.width()} × {pix.height()}{duration} · {self.content_path.stat().st_size//1024} KB")
        self.title.setText("Recording ready" if self.is_video else "Capture ready")
        self.title.setToolTip(self.store.display_name(self.path));self.preview.setToolTip(self.store.display_name(self.path))
        if self.store.display_name(self.path)!=self.path.name:
            self.title.setText(self.title.fontMetrics().elidedText(Path(self.store.display_name(self.path)).stem,Qt.TextElideMode.ElideRight,ui.px(240)))
    def rename(self):
        name,accepted=QInputDialog.getText(self,"Rename capture","Name",text=Path(self.store.display_name(self.path)).stem)
        if accepted:
            try:self.store.rename(self.path,name);self.refresh_content()
            except Exception as exc:error(self,exc)
    def export_to(self,folder=None):
        target=self.store.export_target(self.path,folder,extension=None if self.is_video else self.store.settings["format"])
        if self.is_video:shutil.copy2(self.path,target)
        else:save_image(load_image(self.content_path),target,convert_srgb=self.store.settings.get("convert_srgb",True))
        return target
    def enterEvent(self,event):
        super().enterEvent(event);self.timer.stop()
        self.rearm_hover_keys()
        if self.collapsed or not self.is_video:return
        if self.hover_player is None:
            from PySide6.QtMultimedia import QMediaPlayer,QVideoSink
            from .video_decoder import configure_preview_decoder
            configure_preview_decoder()
            self.hover_player=MediaPlayer(self);self.hover_sink=QVideoSink(self);self.hover_player.setVideoOutput(self.hover_sink);self.hover_player.setLoops(QMediaPlayer.Loops.Infinite);self.hover_player.setSource(QUrl.fromLocalFile(str(self.path.resolve())))
            def frame_changed(frame):
                image=frame.toImage()
                if not image.isNull():self.preview.setPixmap(QPixmap.fromImage(image).scaled(ui.px(self.store.settings["overlay_size"]),ui.px(185),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.hover_sink.videoFrameChanged.connect(frame_changed)
        self.hover_player.play()
    def leaveEvent(self,event):
        super().leaveEvent(event);self.hover_keys.stop()
        if self.hover_player:self.hover_player.pause();self.preview.setPixmap(self.thumbnail)
        self.resume_timer()
    def set_collapsed(self,value):
        self.collapsed=value
        if value:self.hover_keys.stop()
        if value and self.hover_player:self.hover_player.pause()
        for child in self.findChildren(QWidget,options=Qt.FindChildOption.FindDirectChildrenOnly):
            if child is not self.restore_button:child.setVisible(not value)
        self.restore_button.setVisible(value);self.adjustSize();self.showEvent(__import__("PySide6.QtGui",fromlist=["QShowEvent"]).QShowEvent())
    def wheelEvent(self,event):
        # Pixel deltas identify a touchpad swipe; ordinary mouse-wheel steps
        # should not accidentally dismiss a capture.
        delta=event.pixelDelta()
        if delta.isNull():event.ignore();return
        if event.inverted():delta=-delta
        self.swipe+=delta
        if abs(self.swipe.x())>90:self.close();self.swipe=QPoint()
        elif self.swipe.y()<-90:self.set_collapsed(True);self.swipe=QPoint()
        elif self.swipe.y()>90:self.set_collapsed(False);self.swipe=QPoint()
        if event.phase()==Qt.ScrollPhase.ScrollEnd:self.swipe=QPoint()
        event.accept()
    def preview_large(self):
        if self.quicklook:self.quicklook.show();return
        dialog=QDialog(self);dialog.setWindowTitle("OmniShot — Preview");ui.set(dialog,"resize",960,700);layout=QVBoxLayout(dialog)
        if self.is_video:
            from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            from .video_decoder import configure_preview_decoder
            configure_preview_decoder()
            video=QVideoWidget();layout.addWidget(video);player=MediaPlayer(dialog);audio=QAudioOutput(dialog);player.setAudioOutput(audio);player.setVideoOutput(video);player.setSource(QUrl.fromLocalFile(str(self.path.resolve())));player.play();dialog.finished.connect(player.stop)
        else:
            label=QLabel();label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setPixmap(QPixmap.fromImage(convert_image(load_image(self.content_path))).scaled(920,620,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));layout.addWidget(label)
        layout.addWidget(button("Close",dialog.close));QShortcut(QKeySequence("Space"),dialog,activated=dialog.close);QShortcut(QKeySequence("Escape"),dialog,activated=dialog.close)
        self.quicklook=dialog;dialog.finished.connect(lambda _:(setattr(self,"quicklook",None),QTimer.singleShot(0,self.rearm_hover_keys)));dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.show()
    def showEvent(self,event):
        super().showEvent(event);screen=QApplication.screenAt(cursor_position()) or QApplication.primaryScreen()
        if self.store.settings.get("overlay_active_screen",True):
            for window in QApplication.topLevelWidgets():
                if isinstance(window,QuickOverlay) and window.store is self.store and window.isVisible():window.position_on(screen)
        else:self.position_on(self.target_screen if self.target_screen in QApplication.screens() else screen)
        self.resume_timer()
    def position_on(self,screen):
        self.target_screen=screen
        r=screen.availableGeometry();corner=self.store.settings["overlay_corner"]
        x=r.left()+ui.px(18) if "left" in corner else r.right()-self.width()-ui.px(18)
        y=r.top()+ui.px(18) if "top" in corner else r.bottom()-self.height()-ui.px(18)
        y+=self.index*ui.px(18) if "top" in corner else -self.index*ui.px(18)
        place_window(self,x,y);self.update()
    def copy(self):
        if self.copying:return
        if self.is_video:
            from shiboken6 import isValid
            keep=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier)
            path,store,name=self.path,self.store,self.store.display_name(self.path)
            self.copying=True;self.timer.stop();self.hover_keys.stop();self.title.setText("Copying recording…")
            def done(_):
                if not isValid(self):return
                self.copying=False
                if not keep:self.close()
                else:self.refresh_content();self.resume_timer();self.rearm_hover_keys()
            def failed(message):
                if isValid(self):self.copying=False;self.refresh_content();error(self,message)
                else:error(None,message)
            background(lambda:backend.copy_file(path,store,name=name),done,failed);return
        try:
            backend.copy_image(self.content_path,self.store,name=self.store.display_name(self.path))
        except Exception as exc:error(self,exc);return
        if not QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier:self.close()
    def save(self,save_as=False):
        ask=self.store.settings.get("ask_save_destination",False)
        if QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier:ask=not ask
        if not save_as and not ask:
            try:self.export_to();self.close()
            except Exception as exc:error(self,exc)
            return
        if self.is_video:
            path,_=QFileDialog.getSaveFileName(self,"Save recording",str(self.store.export_target(self.path)),"Recordings (*.mp4 *.gif *.webm *.mov *.mkv)")
            if path:
                try:
                    if Path(path).resolve()!=self.path.resolve():shutil.copy2(self.path,path)
                    self.close()
                except Exception as exc:error(self,exc)
            return
        path,_=QFileDialog.getSaveFileName(self,"Save capture",str(self.store.export_target(self.path,extension=self.store.settings["format"])),"PNG (*.png);;JPEG (*.jpg);;WebP (*.webp);;HEIC (*.heic)")
        if path:
            try:save_image(load_image(self.content_path),path,convert_srgb=self.store.settings.get("convert_srgb",True));self.close()
            except Exception as exc:error(self,exc)
    def print_image(self):
        from .printing import print_image
        self.timer.stop();self.hover_keys.stop()
        try:print_image(load_image(self.store.display_image(self.path)),self,self.store.display_name(self.path))
        except Exception as exc:error(self,exc)
        finally:self.resume_timer();self.rearm_hover_keys()
    def contextMenuEvent(self,event):
        menu=QMenu(self);menu.addAction("Edit" if self.is_video else "Annotate",lambda:self.annotate.emit(str(self.path)))
        menu.addAction("Preview",self.preview_large)
        if not self.is_video:
            menu.addAction("Pin",lambda:self.pin.emit(str(self.path)))
            transforms=menu.addMenu("Transform")
            for label,action in [("Rotate clockwise","rotate"),("Rotate counterclockwise","rotate-left"),("Flip horizontally","flip"),("Flip vertically","flip-vertical"),("Scale to 1×","scale")]:
                item=transforms.addAction(label,lambda checked=False,a=action:self.transform_requested.emit(str(self.path),a))
                if action=="scale":item.setEnabled(self.store.metadata(self.path).get("pixel_ratio",1)>1)
        menu.addAction("Copy",self.copy);menu.addAction("Save",self.save);menu.addAction("Save as…",lambda:self.save(True));menu.addAction("Save all captures…",self.save_all_requested.emit)
        if not self.is_video:menu.addAction("Print…",self.print_image)
        menu.addAction("Rename…",self.rename);menu.addAction("Move to Trash",lambda:self.trash_requested.emit(str(self.path)));menu.addSeparator();menu.addAction("Temporarily hide",lambda:self.set_collapsed(True));menu.addAction("Dismiss",self.close);menu.addAction("Close all previews",self.close_all_requested.emit);menu.exec(event.globalPos())
    def hideEvent(self,event):
        self.timer.stop();self.hover_keys.stop();super().hideEvent(event)
    def closeEvent(self,event):
        self.hover_keys.stop()
        if self.hover_player:self.hover_player.stop()
        if self.quicklook:self.quicklook.close()
        self.dismissed.emit(str(self.path));super().closeEvent(event)


class Pin(QWidget):
    annotate_requested=Signal(str)
    def __init__(self,path,index=0,store=None):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.path=Path(path);self.store=store or backend.Store()
        self.normal_title=f"OmniShot Pin {index}";self.setWindowTitle(self.normal_title);self.content_path=self.store.display_image(path);self.image=load_image(self.content_path);self.offset=None
        if self.image.isNull():raise ValueError("Only images can be pinned")
        self.display_pixels=convert_image(self.image)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.opacity=1.0
        self.locked=False;self.shadow_window=None;self.dragging=False;self.last_position=None
        self.setFixedSize(self.image.size().scaled(520,520,Qt.AspectRatioMode.KeepAspectRatio))
        from .pin_controls import PinControls
        self.controls=PinControls(self)
        self.setToolTip("Drag to move · Scroll to resize · Two-finger scroll or Alt+scroll changes opacity · Right click for options")
    def content_rect(self):return self.rect()
    def setFixedSize(self,*args):
        super().setFixedSize(*args)
        if hasattr(self,'image'):self.display_scale=self.width()/self.image.width()
    def refresh_content(self):
        path=self.store.display_image(self.path);image=load_image(path)
        if image.isNull():return False
        scale=self.display_scale;self.content_path=path
        if image==self.image:return True
        try:position=next(c['at'] for c in backend.hypr('clients') if c['pid']==__import__('os').getpid() and c['title']==self.windowTitle())
        except (RuntimeError,StopIteration):position=None
        self.image=image;self.display_pixels=convert_image(image)
        QWidget.setFixedSize(self,max(1,round(image.width()*scale)),max(1,round(image.height()*scale)));self.controls.layout();self.refresh_appearance()
        if position:place_window(self,*position)
        self.controls.schedule_position();return True
    def refresh_appearance(self):
        if self.windowHandle() and self.shadow_window is None:
            from .pin_shadow import PinShadow
            self.shadow_window=PinShadow(self)
        if self.shadow_window:self.shadow_window.sync()
        self.update_input();self.update()
    def update_input(self):
        if self.windowHandle():self.windowHandle().setMask(QRegion(-2,-2,1,1) if self.locked else QRegion(self.content_rect()))
    def enterEvent(self,event):
        super().enterEvent(event);self.controls.hovered=True;self.controls.sync()
    def leaveEvent(self,event):
        super().leaveEvent(event);self.controls.hovered=False;self.controls.sync()
    def showEvent(self,event):
        super().showEvent(event);self.refresh_appearance();self.controls.sync()
        if self.last_position:place_window(self,*self.last_position)
        self.controls.schedule_position()
    def hideEvent(self,event):
        try:self.last_position=next(c['at'] for c in backend.hypr('clients') if c['pid']==__import__('os').getpid() and c['title']==self.windowTitle())
        except (RuntimeError,StopIteration):pass
        if self.shadow_window:self.shadow_window.hide()
        self.controls.unlock.hide();self.controls.position_timer.stop()
        super().hideEvent(event)
    def closeEvent(self,event):
        if self.shadow_window:self.shadow_window.release_backing()
        super().closeEvent(event)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'controls'):self.controls.layout();self.controls.schedule_position()
        self.update_input()
        if self.shadow_window:self.shadow_window.sync()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform|QPainter.RenderHint.Antialiasing);p.setOpacity(self.opacity)
        rect=QRectF(self.content_rect());radius=8 if self.store.settings.get("pin_rounded",True) else 0
        clip=QPainterPath();clip.addRoundedRect(rect,radius,radius);p.setClipPath(clip);p.drawImage(rect,self.display_pixels);p.setClipping(False)
        if self.store.settings.get("pin_border",False):
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(255,255,255,190),1));p.drawRoundedRect(rect.adjusted(.5,.5,-.5,-.5),radius,radius)
    def mousePressEvent(self,event):
        if self.locked:return
        if event.button()==Qt.MouseButton.LeftButton:self.offset=event.position().toPoint()
        elif event.button()==Qt.MouseButton.MiddleButton:self.close()
    def mouseMoveEvent(self,event):
        if self.offset is not None and event.buttons()&Qt.MouseButton.LeftButton and (event.position().toPoint()-self.offset).manhattanLength()>=QApplication.startDragDistance():
            self.offset=None;self.windowHandle().startSystemMove()
    def mouseReleaseEvent(self,event):self.offset=None
    def wheelEvent(self,event):
        if self.locked:event.ignore();return
        pixels=event.pixelDelta();angle=event.angleDelta();alt=bool(event.modifiers()&Qt.KeyboardModifier.AltModifier)
        # Qt can translate Alt+vertical wheel into the horizontal angle axis.
        delta=pixels.y() if not pixels.isNull() else angle.y() or (angle.x() if alt else 0)
        if not delta:event.ignore();return
        if alt or not pixels.isNull():
            amount=delta/120*.08 if pixels.isNull() else delta/500
            self.opacity=max(.1,min(1,self.opacity+amount));self.refresh_appearance()
        else:
            factor=1.1**max(-10,min(10,delta/120));w=max(50,min(3000,round(self.width()*factor)));self.setFixedSize(w,max(1,round(w*self.image.height()/self.image.width())))
        event.accept()
    def keyPressEvent(self,event):
        delta={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}.get(event.key())
        if delta:
            try:
                client=next(c for c in backend.hypr("clients") if c.get("pid")==__import__("os").getpid() and c["title"]==self.windowTitle());x,y=client["at"]
            except (RuntimeError,StopIteration):x,y=self.x(),self.y()
            step=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1
            place_window(self,x+delta[0]*step,y+delta[1]*step)
        elif event.key()==Qt.Key.Key_Escape:self.close()
    def contextMenuEvent(self,event):
        menu=QMenu(self);menu.addAction("Annotate",lambda:self.annotate_requested.emit(str(self.path)));menu.addAction("Copy",self.copy);menu.addAction("Save…",self.save);menu.addAction("Text / QR",self.extract)
        menu.addSeparator();menu.addAction("Actual size",lambda:self.setFixedSize(self.image.size()));menu.addAction("Lock Mode",self.lock);menu.addAction("Hide",self.hide);menu.addAction("Close",self.close);menu.exec(event.globalPos())
    def copy(self):
        try:backend.copy_image(self.content_path,self.store,name=self.store.display_name(self.path))
        except Exception as exc:error(self,exc)
    def save(self):
        dest=Path(self.store.settings["output_dir"]);dest.mkdir(parents=True,exist_ok=True)
        path,_=QFileDialog.getSaveFileName(self,"Save pinned image",str(dest/self.path.name),"PNG (*.png);;JPEG (*.jpg);;WebP (*.webp);;HEIC (*.heic)")
        if path:
            try:save_image(self.image,path,convert_srgb=self.store.settings.get("convert_srgb",True))
            except Exception as exc:error(self,exc)
    def extract(self):
        languages=self.store.settings["ocr_languages"];linebreaks=self.store.settings["ocr_linebreaks"];path=self.content_path
        from .text_result import extract,present
        settings=dict(self.store.settings)
        background(lambda:extract(path,languages,linebreaks),lambda value:present(value,settings),lambda msg:error(None,msg))
    def drag_image(self):
        from .drag import execute
        keep=bool(QApplication.keyboardModifiers()&Qt.KeyboardModifier.AltModifier)
        self.dragging=True;self.controls.sync()
        try:
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.content_path.resolve()))]);mime.setImageData(self.image)
            drag=QDrag(self);drag.setMimeData(mime);drag.setPixmap(QPixmap.fromImage(self.display_pixels).scaled(160,120,Qt.AspectRatioMode.KeepAspectRatio))
            if execute(drag) and not keep:self.close()
        except Exception as exc:error(self,exc)
        finally:self.dragging=False;self.controls.sync()
    def lock(self):
        self.set_clickthrough(True)
    def unlock(self):self.set_clickthrough(False)
    def set_clickthrough(self,enabled):
        try:
            client=next(c for c in backend.hypr("clients") if c.get("pid")==__import__("os").getpid() and c["title"]==self.windowTitle());x,y=client["at"]
        except (RuntimeError,StopIteration):x,y=self.x(),self.y()
        self.locked=enabled
        self.setWindowTitle(self.normal_title.replace("OmniShot Pin","OmniShot Locked Pin") if enabled else self.normal_title)
        # Keep only the separate unlock control interactive while the image passes through.
        self.controls.sync()
        self.update_input()
        place_window(self,x,y);self.update()
        self.controls.schedule_position()


from .history import History


class Settings(QDialog):
    def __init__(self,store,tab="general"):
        super().__init__();self.store=store;self.setWindowTitle("OmniShot — Settings");ui.set(self,"resize",800,640);self.fields={};self.forms={};self.wallpaper_data=store.settings["wallpaper_data"];self.wallpaper_follow_at_open=store.settings["wallpaper_follow_changes"];self.filename_options={key:store.settings[key] for key in ("filename_format","filename_utc","filename_remove_illegal")}
        layout=QVBoxLayout(self);body=QHBoxLayout();layout.addLayout(body,1)
        self.sections=QListWidget();ui.set(self.sections,"setFixedWidth",165);body.addWidget(self.sections)
        self.pages=QStackedWidget();body.addWidget(self.pages,1);self.page_names=[]
        descriptions={
            "general":"Choose where captures go and what happens after you capture.",
            "wallpaper":"Choose the wallpaper behind window screenshots.",
            "screenshots":"Adjust image capture and scrolling behavior.",
            "quickaccess":"Keep your captures within reach without interrupting your work.",
            "recording":"Set defaults for new recordings. Each recording can override them.",
            "annotate":"Customize annotation tools, shortcuts and automatic backgrounds.",
            "text":"Extract text on your device, including when you are offline.",
            "advanced":"Customize filenames, clipboard representations and capture history.",
            "shortcuts":"Choose the keyboard shortcuts that fit your workflow.",
            "about":"Capture, annotate and record on Omarchy."}
        for key,title in [("general","General"),("wallpaper","Wallpaper"),("screenshots","Screenshots"),("quickaccess","Quick Access"),("recording","Recording"),("annotate","Annotate"),("text","Text Recognition"),("advanced","Advanced"),("shortcuts","Shortcuts"),("about","About")]:
            self.sections.addItem(title);self.page_names.append(key);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            page=QWidget();form=QFormLayout(page);ui.set(form,"setVerticalSpacing",15);ui.set(form,"setContentsMargins",20,12,16,20)
            heading=QLabel(title);ui.set(heading,"setStyleSheet","font-size:22px;font-weight:600");form.addRow(heading)
            description=QLabel(descriptions[key]);description.setWordWrap(True);description.setObjectName("muted");form.addRow(description)
            self.forms[key]=form;scroll.setWidget(page);self.pages.addWidget(scroll)
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        labels={"overlay":"Show Quick Access","annotate":"Open Annotate","copy":"Copy to clipboard","save":"Save to folder","pin":"Pin to screen","edit":"Open video editor",
                "bottom-left":"Bottom left","bottom-right":"Bottom right","top-left":"Top left","top-right":"Top right","dark":"Dark","light":"Light","medium":"Medium","high":"High","very_high":"Very high","ultra":"Maximum","png":"PNG","jpg":"JPEG","webp":"WebP","heic":"HEIC"}
        def combo(page,key,label,choices):
            box=QComboBox()
            for choice in choices:box.addItem(labels.get(str(choice),str(choice)),choice)
            box.setCurrentIndex(max(0,box.findData(store.settings.get(key,choices[0]))));self.fields[key]=box;self.forms[page].addRow(label,box);return box
        def spin(page,key,label,lo,hi,suffix=""):
            box=QSpinBox();box.setRange(lo,hi);box.setValue(store.settings[key]);box.setSuffix(suffix);self.fields[key]=box;self.forms[page].addRow(label,box)
        def check(page,key,label):
            box=QCheckBox(label);box.setChecked(store.settings.get(key,False));self.fields[key]=box;self.forms[page].addRow(box)
        folder=QWidget();row=QHBoxLayout(folder);ui.set(row,"setContentsMargins",0,0,0,0);self.fields["output_dir"]=QLineEdit(store.settings["output_dir"]);row.addWidget(self.fields["output_dir"]);row.addWidget(button("Choose…",self.choose_folder));self.forms["general"].addRow("Save folder",folder)
        self.forms["general"].addRow("Appearance",QLabel("Follows your Omarchy theme"));spin("advanced","history_days","Keep capture history",1,30," days")
        labels.update(both="File and image",file="File only",image="Image only")
        combo("advanced","clipboard_mode","Copy to clipboard",["both","image","file"])
        for key,label in [("pin_rounded","Round pinned screenshot corners"),("pin_shadow","Show shadows behind pinned screenshots"),("pin_border","Show borders on pinned screenshots")]:check("advanced",key,label)
        check("advanced","url_api_enabled","Enable URL scheme API")
        check("advanced","ask_capture_name","Ask for a name after every capture")
        check("advanced","filename_scale_suffix","Append display scale to image filenames (@2x, @1.6x)")
        self.forms["advanced"].addRow("File name format",button("Customize…",self.customize_filename))
        self.filename_preview=QLabel(self.filename_options["filename_format"]);self.filename_preview.setTextFormat(Qt.TextFormat.PlainText);self.filename_preview.setWordWrap(True);self.forms["advanced"].addRow(self.filename_preview)
        title=QLabel("After Capture");ui.set(title,"setStyleSheet","font-size:16px;font-weight:600");self.forms["general"].addRow(title)
        matrix=QWidget();grid=QGridLayout(matrix);ui.set(grid,"setContentsMargins",0,0,0,0);ui.set(grid,"setVerticalSpacing",14);grid.setColumnStretch(0,1);self.action_boxes={}
        for column,(kind,title) in enumerate((("capture","Screenshot"),("recording","Recording")),1):
            grid.addWidget(QLabel(title),0,column,alignment=Qt.AlignmentFlag.AlignCenter);self.action_boxes[kind]={}
        for row,(action,label) in enumerate((("overlay","Show Quick Access Overlay"),("copy","Copy to clipboard"),("save","Save"),("annotate","Open Annotate"),("pin","Pin to screen"),("edit","Open Video Editor")),1):
            grid.addWidget(QLabel(label),row,0)
            for column,kind in enumerate(("capture","recording"),1):
                if (kind=="capture" and action=="edit") or (kind=="recording" and action in ("annotate","pin")):continue
                box=QCheckBox();box.setAccessibleName(f"{label} after {kind}");box.setChecked(action in backend.capture_actions(store.settings,kind=="recording"));grid.addWidget(box,row,column,alignment=Qt.AlignmentFlag.AlignCenter);self.action_boxes[kind][action]=box
        self.forms["general"].addRow(matrix)
        labels.update(desktop="Desktop wallpaper",custom="Custom image")
        combo("wallpaper","wallpaper_source","Wallpaper",["desktop","custom"])
        check("wallpaper","wallpaper_follow_changes","Follow desktop wallpaper changes")
        self.wallpaper_choose=button("Choose custom image…",self.choose_wallpaper);self.forms["wallpaper"].addRow(self.wallpaper_choose)
        self.wallpaper_preview=QLabel();self.wallpaper_preview.setAlignment(Qt.AlignmentFlag.AlignCenter);ui.set(self.wallpaper_preview,"setMinimumHeight",180);self.forms["wallpaper"].addRow(self.wallpaper_preview)
        self.fields["wallpaper_source"].currentIndexChanged.connect(self.refresh_wallpaper);self.fields["wallpaper_follow_changes"].toggled.connect(self.refresh_wallpaper);self.refresh_wallpaper()
        combo("screenshots","format","Image format",["png","jpg","webp","heic"])
        for key,label in [("include_cursor","Include cursor"),("freeze","Freeze the screen during selection"),("window_shadow","Add shadows to window captures")]:check("screenshots",key,label)
        check("screenshots","window_wallpaper","Use wallpaper behind window screenshots (Shift makes it transparent)")
        padding_row=QWidget();padding_layout=QHBoxLayout(padding_row);ui.set(padding_layout,"setContentsMargins",0,0,0,0)
        padding=QSlider(Qt.Orientation.Horizontal);padding.setRange(0,200);padding.setPageStep(20);padding.setValue(store.settings["window_padding"]);padding.setAccessibleName("Window capture padding")
        padding_value=QLabel(f"{padding.value()} px");ui.set(padding_value,"setMinimumWidth",55);padding.valueChanged.connect(lambda value:padding_value.setText(f"{value} px"))
        padding_layout.addWidget(padding);padding_layout.addWidget(padding_value);self.fields["window_padding"]=padding;self.forms["screenshots"].addRow("Window padding",padding_row)
        check("screenshots","capture_ctrl_copy","Copy screenshots when holding Ctrl at capture")
        check("screenshots","convert_srgb","Convert exported images to sRGB")
        check("screenshots","scale_screenshots","Scale screenshots to 1×")
        check("screenshots","screenshot_border","Add a 1 px border inside the image")
        labels.update(always="Always",selecting="While selecting",disabled="Disabled")
        combo("screenshots","crosshair_mode","Crosshair",["always","selecting","disabled"])
        check("screenshots","show_magnifier","Show magnifier with the crosshair")
        check("screenshots","remember_selection","Remember the All-In-One selection")
        spin("screenshots","delay","Self timer",0,60," seconds");spin("screenshots","scroll_interval","Auto-scroll interval",150,3000," ms");spin("screenshots","scroll_step","Auto-scroll step",1,10)
        combo("quickaccess","overlay_corner","Position",["bottom-left","bottom-right","top-left","top-right"])
        check("quickaccess","overlay_active_screen","Move previews to the active screen")
        spin("quickaccess","overlay_size","Preview width",240,550," px");spin("quickaccess","overlay_timeout","Close after (0 = keep)",0,120," seconds")
        labels.update(close="Close",save="Save and close")
        combo("quickaccess","overlay_auto_action","Auto-close action",["close","save"])
        check("quickaccess","overlay_close_after_drag","Close after dragging")
        check("quickaccess","ask_save_destination","Ask for a destination when saving")
        help=QLabel("Hold Alt as you start dragging to keep the preview, or when clicking Save to switch between choosing a destination and saving directly.\n\nHover a preview to use Ctrl+C, Ctrl+S, Ctrl+E, Ctrl+P, Ctrl+W or Space.\nSwipe sideways to dismiss, or down to temporarily hide it.");help.setWordWrap(True);self.forms["quickaccess"].addRow(help)
        self.forms["recording"].addRow(QLabel("General"))
        for key,label in [("record_show_controls","Show controls while recording"),("record_dim_screen","Dim outside the recording area"),("record_remember_selection","Remember last recording selection"),("record_show_time","Display recording time in the bar"),("record_dnd","Do not disturb while recording")]:check("recording",key,label)
        spin("recording","record_countdown","Countdown (0 = off)",0,30," seconds")
        self.forms["recording"].addRow(QLabel("Cursor and keystrokes"))
        for key,label in [("record_cursor","Show cursor"),("record_clicks","Highlight clicks"),("record_keys","Show keystrokes"),("record_commands_only","Show command shortcuts only")]:check("recording",key,label)
        self.forms["recording"].addRow(QLabel("Video"))
        combo("recording","fps","Frames per second",[15,24,30,60]);combo("recording","quality","Quality",["medium","high","very_high","ultra"])
        from .recording_options import RESOLUTIONS
        labels["Native"]="Original"
        combo("recording","record_max_resolution","Maximum resolution",RESOLUTIONS)
        check("recording","record_scale_video","Scale videos to 1×")
        for key,label in [("record_system_audio","Record computer audio"),("record_microphone","Record microphone"),("record_audio_mono","Record audio in mono")]:check("recording",key,label)
        labels.update(single="Single track",separate="Separate tracks")
        combo("recording","record_audio_tracks","Audio tracks",["single","separate"])
        from .gif_options import WIDTHS,FPS
        self.forms["recording"].addRow(QLabel("GIF"))
        combo("recording","gif_fps","Frame rate",FPS)
        labels.update({0:"Original",**{width:f"{width} × auto" for width in WIDTHS if width}})
        combo("recording","gif_width","Resolution",WIDTHS);check("recording","gif_optimize","Optimize GIFs")
        quality=QSlider(Qt.Orientation.Horizontal);quality.setRange(1,100);quality.setValue(store.settings["gif_quality"]);quality.setAccessibleName("GIF quality");quality.setToolTip("Lower quality uses fewer colors and creates smaller files.");self.fields["gif_quality"]=quality;self.forms["recording"].addRow("Quality",quality)
        from .backgrounds import PRESETS
        combo("annotate","background_preset","Automatic background",["None",*PRESETS,*store.settings.get("background_presets",{})])
        for key,label in [("inverse_arrows","Reverse arrow direction (Alt reverses while drawing)"),("smooth_drawing","Smooth pencil drawing"),("annotation_shadow","Draw shadows on annotations"),("auto_expand_canvas","Automatically expand the canvas")]:check("annotate",key,label)
        pin_key=QKeySequenceEdit(QKeySequence(store.settings.get('annotation_pin_shortcut','')));pin_key.setMaximumSequenceLength(1);pin_key.setClearButtonEnabled(True);pin_key.setAccessibleName('Pin in Annotate');pin_key.setToolTip('Pin the current edited image while Annotate is active. Clear the field to disable.');self.fields['annotation_pin_shortcut']=pin_key;self.forms['annotate'].addRow('Pin shortcut',pin_key)
        hint=QLabel("Customize padding, shadows, corners, colors and image backgrounds in Annotate. Saved presets are available here.\n\nHold Shift when confirming a selection to skip the automatic background for that capture.");hint.setWordWrap(True);self.forms["annotate"].addRow(hint)
        check("text","ocr_linebreaks","Preserve line breaks")
        check("text","ocr_detect_links","Detect links")
        self.fields["ocr_languages"]=QLineEdit(store.settings["ocr_languages"]);self.forms["text"].addRow("Languages",self.fields["ocr_languages"])
        hint=QLabel("Use auto to detect the script, or language codes such as eng+spa.");hint.setWordWrap(True);self.forms["text"].addRow(hint)
        self.ocr_install=button("Install / update 36 offline languages",self.install_ocr);self.forms["text"].addRow(self.ocr_install)
        self.hint=QLabel();self.hint.setWordWrap(True);self.hint.setObjectName("muted");self.forms["shortcuts"].addRow(self.hint);self.update_shortcut_hint()
        def shortcuts():
            from .shortcuts import ShortcutsDialog
            ShortcutsDialog(self.store,self).exec();self.update_shortcut_hint()
        self.forms["shortcuts"].addRow(button("Customize shortcuts…",shortcuts))
        check("shortcuts","capture_shortcut_actions","Also run After Capture actions with area shortcuts")
        hint=QLabel("Capture Area & Copy, Save, Annotate and Pin always perform their named action. Enable this to also use the screenshot actions selected in General.");hint.setWordWrap(True);self.forms["shortcuts"].addRow(hint)
        from . import __version__
        name=QLabel("OmniShot");ui.set(name,"setStyleSheet","font-size:30px;font-weight:600");self.forms["about"].addRow(name)
        version=QLabel(f"Version {__version__}");version.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);self.forms["about"].addRow(version)
        for text in ("Screenshots, scrolling capture, annotation and screen recording — saved locally.",
                     "Appearance follows your current Omarchy theme.",
                     "OmniShot is independent software, released under the MIT license."):
            label=QLabel(text);label.setWordWrap(True);self.forms["about"].addRow(label)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.show_page(tab)
    def show_page(self,tab):
        self.sections.setCurrentRow(self.page_names.index(tab) if tab in self.page_names else 0)
    def refresh_wallpaper(self):
        import base64
        from .wallpaper import desktop_path
        custom=self.fields["wallpaper_source"].currentData()=="custom";self.wallpaper_choose.setEnabled(custom);self.fields["wallpaper_follow_changes"].setEnabled(not custom)
        path=desktop_path();cached=self.store.root/"wallpaper-desktop.png"
        if not custom and not self.wallpaper_follow_at_open and not self.fields["wallpaper_follow_changes"].isChecked() and cached.is_file():path=cached
        image=QImage.fromData(base64.b64decode(self.wallpaper_data)) if custom and self.wallpaper_data else load_image(path) if not custom and path else QImage()
        if image.isNull():self.wallpaper_preview.clear();self.wallpaper_preview.setText("Choose an image" if custom else "No desktop wallpaper available")
        else:self.wallpaper_preview.setPixmap(QPixmap.fromImage(convert_image(image)).scaled(ui.px(420),ui.px(230),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def choose_wallpaper(self):
        from .images import IMAGE_FILTER
        path,_=QFileDialog.getOpenFileName(self,"Choose capture wallpaper","",IMAGE_FILTER)
        if path:
            try:
                from .wallpaper import image_data
                self.wallpaper_data=image_data(path);self.refresh_wallpaper()
            except Exception as exc:error(self,exc)
    def customize_filename(self):
        from .filenames import customize
        result=customize({**self.store.settings,**self.filename_options},self)
        if result:self.filename_options=result;self.filename_preview.setText(result["filename_format"])
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Save captures to",str(Path(self.fields["output_dir"].text()).expanduser()))
        if folder:self.fields["output_dir"].setText(folder)
    def update_shortcut_hint(self):
        from .shortcuts import DEFAULTS,ACTIONS
        values=self.store.settings.get("shortcuts",DEFAULTS);self.hint.setText(" · ".join(key.replace("Meta","Super")+": "+ACTIONS[command] for command,key in values.items() if key and command in ACTIONS))
    def install_ocr(self):
        from .ocr import install_models
        self.ocr_install.setEnabled(False);self.ocr_install.setText("Downloading language packs…")
        # Keep this dialog alive while its worker is connected to its controls.
        self.downloading=True;self.closed_during_download=False;self.delete_after_download=self.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,False)
        def cleanup():
            self.downloading=False;self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,self.delete_after_download)
            if self.closed_during_download and self.delete_after_download:self.deleteLater()
        def done(count):self.ocr_install.setEnabled(True);self.ocr_install.setText(f"{count} OCR languages installed");cleanup()
        def fail(msg):self.ocr_install.setEnabled(True);self.ocr_install.setText("Retry language download");error(None if self.closed_during_download else self,msg);cleanup()
        background(install_models,done,fail)
    def done(self,result):
        if getattr(self,"downloading",False):self.closed_during_download=True
        super().done(result)
    def save(self):
        from .annotation_shortcuts import validate_pin
        from .shortcuts import DEFAULTS
        try:validate_pin(self.fields['annotation_pin_shortcut'].keySequence().toString(QKeySequence.SequenceFormat.PortableText),self.store.settings.get('shortcuts',DEFAULTS))
        except ValueError as exc:error(self,exc);return
        folder=self.fields["output_dir"].text().strip()
        if not folder:error(self,"Choose a folder for saved captures.");return
        if self.fields["wallpaper_source"].currentData()=="custom" and not self.wallpaper_data:error(self,"Choose a custom wallpaper image first.");return
        self.fields["output_dir"].setText(str(Path(folder).expanduser().absolute()))
        if self.fields["wallpaper_source"].currentData()=="desktop" and not self.fields["wallpaper_follow_changes"].isChecked():
            from .wallpaper import capture_wallpaper
            capture_wallpaper(self.store)
        self.store.settings["wallpaper_data"]=self.wallpaper_data
        for kind,boxes in self.action_boxes.items():
            self.store.settings["after_"+kind]=""
            self.store.settings["after_"+kind+"_extra"]=[key for key,box in boxes.items() if box.isChecked()]
        self.store.settings.update(self.filename_options)
        for key,box in self.fields.items():
            if isinstance(box,QKeySequenceEdit):value=box.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            elif isinstance(box,QComboBox):value=box.currentData()
            elif isinstance(box,(QSpinBox,QSlider)):value=box.value()
            elif isinstance(box,QCheckBox):value=box.isChecked()
            else:value=box.text()
            self.store.settings[key]=value
        self.store.save_settings();self.accept()


class ScrollPanel(QWidget):
    completed=Signal(object);cancelled=Signal()
    def __init__(self,rect,store,horizontal=False):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("OmniShot Scrolling Capture");self.rect_capture=rect;self.store=store
        self.stitcher=ScrollStitcher(horizontal);self.running=False;self.busy=False;self.auto=False;self.no_change=0;self.scrolled_last=False;self.generation=0;self.closed=False;self.finished=False
        layout=QVBoxLayout(self);ui.set(layout,"setContentsMargins",12,10,12,10)
        self.status=QLabel(f"{rect[2]} × {rect[3]} · Adjust the area, then start capture.");self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();self.start_btn=button("Start Capture",self.start,True);self.auto_btn=button("Auto-Scroll",self.toggle_auto);self.auto_btn.hide()
        self.done_btn=button("Done",self.finish,True);self.done_btn.hide();self.cancel_btn=button("Cancel",self.close)
        for b in (self.cancel_btn,self.start_btn,self.auto_btn,self.done_btn):row.addWidget(b)
        layout.addLayout(row);ui.set(self,"setFixedWidth",430)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);QShortcut(QKeySequence("Escape"),self,activated=self.close)
        self.horizontal=horizontal;self.reached_end=False
        from .overlay_keys import ScrollKeys
        self.keys=ScrollKeys(self);self.keys.activated.connect(self.keyboard_action)
        QShortcut(QKeySequence("Return"),self,activated=lambda:self.keyboard_action("accept"))
        from .scroll_ui import ScrollVisuals
        self.visuals=ScrollVisuals(self);self.preview=self.visuals.preview
        from .clean_capture import CursorMirror
        self.mirror=CursorMirror()
    def showEvent(self,event):
        super().showEvent(event);self.visuals.show();self.keys.start()
    def keyboard_action(self,action):
        if self.closed:return
        if action=="cancel":self.close()
        elif action=="accept":
            if self.running:self.finish()
            else:self.start();self.keys.start()
    def start(self):
        if self.running or self.closed:return
        try:self.mirror.start()
        except Exception as exc:
            self.status.setText(str(exc));self.start_btn.setText("Retry Capture");return
        self.running=True;self.visuals.selection.hide();self.start_btn.hide();self.auto_btn.show();self.auto_btn.setEnabled(True);self.done_btn.show();self.done_btn.setEnabled(True)
        self.store.settings["previous_area"]=list(self.rect_capture)
        try:self.store.save_settings()
        except OSError:pass
        self.status.setText("Scroll slowly inside the selection. Click Done when finished.")
        if self.auto:self.set_auto(True)
        self.timer.start(self.store.settings["scroll_interval"]);QTimer.singleShot(180,self.tick)
    def toggle_auto(self):self.set_auto(not self.auto)
    def set_auto(self,enabled):
        if self.closed:return
        self.auto=bool(enabled);self.no_change=0;self.scrolled_last=False;self.reached_end=False;self.auto_btn.setText("Pause Auto" if self.auto else "Auto-Scroll")
        if self.auto and self.running:
            x,y,w,h=self.rect_capture
            try:backend.move_cursor(x+w//2,y+h//2)
            except Exception as exc:self.status.setText(str(exc));self.auto=False;self.auto_btn.setText("Auto-Scroll")
    def tick(self):
        if not self.running or self.busy or time.monotonic()<self.visuals.ready_at:return
        self.busy=True;generation=self.generation
        hidden=self.visuals.before_grab()
        def work():
            if hidden:time.sleep(.15)
            frame=backend.grab(self.rect_capture)
            changed,message=self.stitcher.push(frame)
            return changed,message,self.stitcher.output.copy()
        def done(result):
            self.busy=False
            if generation!=self.generation:return
            self.visuals.after_grab()
            changed,message,frame=result
            if changed:self.reached_end=False
            self.status.setText("Reached the end. Click Done to finish." if self.reached_end else message)
            self.visuals.update(frame)
            if self.auto:
                if "Could not align" in message:self.auto=False;self.auto_btn.setText("Auto-Scroll");return
                if self.scrolled_last:self.no_change=0 if changed else self.no_change+1
                self.scrolled_last=False
                if self.no_change>=4:
                    self.auto=False;self.reached_end=True;self.auto_btn.setText("Auto-Scroll");self.status.setText("Reached the end. Click Done to finish.");return
                x,y,w,h=self.rect_capture
                try:
                    pos=backend.hypr("cursorpos")
                    if not(x<=pos["x"]<x+w and y<=pos["y"]<y+h):self.status.setText("Move the pointer inside the selected area to continue.");return
                    backend.scroll_step(self.horizontal,self.store.settings["scroll_step"])
                    self.scrolled_last=True
                except Exception as exc:self.status.setText(str(exc));self.auto=False;self.auto_btn.setText("Auto-Scroll")
        def fail(message):
            self.busy=False
            if generation!=self.generation:return
            self.visuals.after_grab();self.status.setText(message);self.timer.stop();self.auto=False;self.running=False
            self.release_mirror()
            self.start_btn.setText("Retry Capture");self.start_btn.show();self.auto_btn.setEnabled(False);self.done_btn.setEnabled(self.stitcher.output is not None)
        background(work,done,fail)
    def finish(self):
        if self.closed or self.finished:return
        self.running=False;self.timer.stop()
        if self.busy:QTimer.singleShot(80,self.finish);return
        self.finished=True
        frame=self.stitcher.output.copy() if self.stitcher.output is not None else None
        # Receivers may open a modal dialog. Release the native key lease and
        # capture surfaces before that nested event loop can receive input.
        self.close()
        if frame is not None:self.completed.emit(frame)
    def release_mirror(self):
        try:self.mirror.stop()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Could not release scrolling capture: %s",exc)
    def closeEvent(self,event):
        self.closed=True;self.running=False;self.timer.stop();self.keys.stop();self.generation+=1;self.visuals.close()
        self.release_mirror()
        if not self.finished:self.cancelled.emit()
        super().closeEvent(event)
