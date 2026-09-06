"""Independent camera track, so framing remains editable after recording."""
import subprocess
import threading
import time
from pathlib import Path
import cv2
from PySide6.QtCore import Qt,QTimer,QRectF,Signal
from PySide6.QtGui import QPainter,QPainterPath
from PySide6.QtWidgets import QWidget,QMenu,QApplication
from .editor import qimage
from .widgets import place_window,place_outside


class CameraTrack:
    def __init__(self,device,path,fps=30,lease_fd=None):
        self.device=device;self.path=Path(path);self.fps=fps;self.latest=None;self.first_time=None;self.error=None
        self.stop_event=threading.Event();self.paused=False;self.thread=None;self.process=None
        self.lease_fd=lease_fd
        from .camera_framing import CameraFraming
        self.framing=CameraFraming()
    def start(self):
        self.thread=threading.Thread(target=self._record,name="omnishot-camera",daemon=True);self.thread.start()
    def _record(self):
        camera=cv2.VideoCapture(self.device,cv2.CAP_V4L2)
        try:
            if not camera.isOpened():raise RuntimeError("Could not open the camera. Check that another app isn't using it.")
            camera.set(cv2.CAP_PROP_FRAME_WIDTH,640);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,480);camera.set(cv2.CAP_PROP_FPS,self.fps)
            valid,frame=camera.read()
            if not valid:raise RuntimeError("The camera did not provide an image")
            if self.stop_event.is_set():return
            h,w=frame.shape[:2]
            with self.path.with_suffix(".camera-log").open("wb") as log:
                from .recording_process import launch_encoder
                self.process=launch_encoder(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","bgr24","-video_size",f"{w}x{h}","-framerate",str(self.fps),"-i","pipe:0","-an","-c:v","libx264","-preset","ultrafast","-crf","22","-pix_fmt","yuv420p","-g",str(self.fps),"-movflags","+frag_keyframe+empty_moov","-frag_duration","1000000","-flush_packets","1",str(self.path)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log,lease_fd=self.lease_fd)
                next_frame=time.monotonic()
                while valid and not self.stop_event.is_set():
                    self.latest=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                    if not self.paused:
                        now=time.monotonic()
                        if self.first_time is None:self.first_time=now
                        if now>=next_frame:
                            count=min(3,int((now-next_frame)*self.fps)+1)
                            for _ in range(count):self.process.stdin.write(frame.tobytes())
                            next_frame+=count/self.fps
                    else:next_frame=time.monotonic()
                    valid,frame=camera.read()
                self.process.stdin.close();code=self.process.wait(timeout=15)
                if code:raise RuntimeError("Camera encoding failed")
        except Exception as exc:self.error=str(exc)
        finally:
            camera.release()
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=20)
        if self.thread and self.thread.is_alive():self.error="Camera did not finish saving in time"
        return self.path if self.path.exists() and self.path.stat().st_size>100 else None


class CameraPreview(QWidget):
    fullscreen_changed=Signal(bool)
    shape_changed=Signal(str)
    placement_changed=Signal(object)
    def __init__(self,track,shape="Circle",size=200,rect=None,allow_fullscreen=True,mirror=False):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.track=track;self.shape=shape;self.mirror=mirror;self.setWindowTitle("OmniShot Camera Preview");self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.setFixedSize(size,size if shape in ("Circle","Square") else int(size*.75))
        self.capture_rect=rect;self.allow_fullscreen=allow_fullscreen;self.fullscreen=False;self.drag_start=None;self.normal_placement=None;self.preferred_width=size
        self.placement_after=0;self.last_placement=None
        self.placement_timer=QTimer(self);self.placement_timer.setInterval(100);self.placement_timer.timeout.connect(self.poll_placement)
        self.setToolTip('Click to toggle fullscreen camera. Drag to move the overlay.' if allow_fullscreen else 'Drag to move the overlay. Fullscreen camera is available after recording in the editor.');self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh_frame);self.timer.start(33)

    def overlay_aspect(self):
        frame=self.track.latest
        return 1 if self.shape in ('Circle','Square') else frame.shape[0]/frame.shape[1] if frame is not None else .75

    def overlay_height(self,width):
        return max(1,round(width*self.overlay_aspect()))

    def overlay_size(self):
        width=self.preferred_width
        if self.capture_rect:
            _,_,cw,ch=self.capture_rect
            width=min(width,cw-min(40,cw*.1),(ch-min(120,ch*.2))/self.overlay_aspect())
        width=max(1,int(width))
        return width,self.overlay_height(width)

    def fitted_placement(self,placement):
        x,y,w,h=placement;size=self.overlay_size()
        if size!=(w,h) and self.capture_rect and self.allow_fullscreen:
            cx,cy,cw,ch=self.capture_rect
            x=max(cx,min(x,cx+cw-size[0]));y=max(cy,min(y,cy+ch-size[1]))
        return x,y,*size

    def current_placement(self):
        try:
            from . import backend
            import os
            native=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==self.windowTitle())
            return *native['at'],self.width(),self.height()
        except (OSError,RuntimeError,StopIteration):return self.x(),self.y(),self.width(),self.height()

    def refresh_frame(self):
        if self.fullscreen and self.normal_placement:
            self.normal_placement=self.fitted_placement(self.normal_placement)
        elif not self.fullscreen and self.size().toTuple()!=self.overlay_size():
            old=self.current_placement() if self.isVisible() else (self.x(),self.y(),self.width(),self.height())
            x,y,w,h=self.fitted_placement(old);self.setFixedSize(w,h)
            if (x,y)!=old[:2]:place_window(self,x,y)
            if self.isVisible() and self.allow_fullscreen:
                self.remember_placement(x,y,w);self.placement_after=time.monotonic()+.25
            elif self.isVisible() and self.capture_rect:
                # A resized fallback must remain outside the unexcluded source.
                if not place_outside(self,self.capture_rect):self.hide()
        self.update()
    def paintEvent(self,event):
        if self.track.latest is None:return
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);r=QRectF(self.rect());mask=QPainterPath()
        if self.fullscreen:mask.addRect(r)
        elif self.shape=="Circle":mask.addEllipse(r)
        else:mask.addRoundedRect(r,18 if self.shape in ("Rounded","Square") else 0,18 if self.shape in ("Rounded","Square") else 0)
        image=qimage(self.track.latest)
        if self.mirror:image=image.flipped(Qt.Orientation.Horizontal)
        ratio=r.width()/r.height();sw=min(image.width(),image.height()*ratio);sh=min(image.height(),image.width()/ratio)
        source=QRectF((image.width()-sw)/2,(image.height()-sh)/2,sw,sh)
        p.setClipPath(mask);p.drawImage(r,image,source);p.end()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.drag_start=event.position().toPoint();event.accept()
    def mouseMoveEvent(self,event):
        if self.drag_start is not None and not self.fullscreen and (event.position().toPoint()-self.drag_start).manhattanLength()>=QApplication.startDragDistance():
            self.drag_start=None;self.windowHandle().startSystemMove();event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.drag_start is not None:
            self.drag_start=None;self.toggle_fullscreen();event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and self.fullscreen:self.toggle_fullscreen();event.accept()
        else:super().keyPressEvent(event)
    def toggle_fullscreen(self):
        # An outside-region fallback must never cover the source when exclusion
        # is unavailable (for example, a selection spanning multiple displays).
        if not self.allow_fullscreen:return
        if not self.fullscreen:
            self.poll_placement()
            x,y=self.x(),self.y()
            try:
                from . import backend
                import os
                native=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==self.windowTitle());x,y=native['at']
            except (OSError,RuntimeError,StopIteration):pass
            self.normal_placement=(x,y,self.width(),self.height());x,y,w,h=self.capture_rect or self.screen().geometry().getRect()
        else:x,y,w,h=self.normal_placement
        self.fullscreen=not self.fullscreen;self.placement_after=time.monotonic()+.25;self.setFixedSize(round(w),round(h));place_window(self,x,y)
        if not self.fullscreen:self.remember_placement(x,y,w)
        self.update();self.fullscreen_changed.emit(self.fullscreen)

    def remember_placement(self,x,y,w):
        if not self.capture_rect:return
        cx,cy,cw,ch=self.capture_rect;value=(round(max(-1,min(1,(x-cx)/cw)),6),round(max(-1,min(1,(y-cy)/ch)),6),round(max(.001,min(1,w/cw)),6))
        if value!=self.last_placement:self.last_placement=value;self.placement_changed.emit(value)

    def poll_placement(self):
        if not self.isVisible() or self.fullscreen or time.monotonic()<self.placement_after:return
        from . import backend
        import os
        try:
            native=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==self.windowTitle())
            self.remember_placement(*native['at'],native['size'][0])
        except (OSError,RuntimeError,StopIteration):pass

    def closeEvent(self,event):
        self.placement_timer.stop();super().closeEvent(event)
    def contextMenuEvent(self,event):
        menu=QMenu(self)
        if self.allow_fullscreen:menu.addAction('Return to camera overlay' if self.fullscreen else 'Fullscreen camera',self.toggle_fullscreen)
        for shape in ("Circle","Square","Rounded","Rectangle"):
            action=menu.addAction(shape,lambda checked=False,s=shape:self.set_shape(s));action.setCheckable(True);action.setChecked(shape==self.shape)
        menu.addAction("Hide preview",self.hide);menu.exec(event.globalPos())
    def set_shape(self,shape):
        if shape==self.shape:return
        self.shape=shape
        self.shape_changed.emit(shape);self.refresh_frame()
