"""Bounded, cancellable thumbnail decoding away from the GUI thread."""
from collections import OrderedDict
from threading import Event
from PySide6.QtCore import QObject,Signal
from PySide6.QtGui import QImage


def decode(path,times,cancel,maximum=(320,128)):
    import cv2
    capture=cv2.VideoCapture(str(path));results={}
    try:
        if not capture.isOpened():raise ValueError('Cannot decode timeline thumbnails')
        fps=capture.get(cv2.CAP_PROP_FPS) or 30
        count=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        for milliseconds in times:
            if cancel.is_set():break
            frame=max(0,min(max(0,count-1),round(milliseconds*fps/1000)))
            capture.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,pixels=capture.read()
            if not ok:results[milliseconds]=None;continue
            height,width=pixels.shape[:2];factor=min(maximum[0]/width,maximum[1]/height)
            pixels=cv2.resize(pixels,(max(1,round(width*factor)),max(1,round(height*factor))),interpolation=cv2.INTER_AREA)
            pixels=cv2.cvtColor(pixels,cv2.COLOR_BGR2RGB)
            results[milliseconds]=QImage(pixels.data,pixels.shape[1],pixels.shape[0],pixels.strides[0],QImage.Format.Format_RGB888).copy()
        return results
    finally:capture.release()


class ThumbnailCache(QObject):
    changed=Signal()
    failed=Signal(str)
    LIMIT=192

    def __init__(self,path,parent=None):
        super().__init__(parent);self.path=path;self.images=OrderedDict();self.wanted=();self.running=False;self.closed=False;self.error=False;self.cancel=Event();self.job_keys=()

    def get(self,time):
        if time not in self.images:return None
        self.images.move_to_end(time);return self.images[time]

    def request(self,times):
        if self.closed or self.error:return
        self.wanted=tuple(dict.fromkeys(times));missing=tuple(t for t in self.wanted if t not in self.images)
        if self.running:
            if not set(missing).issubset(self.job_keys):self.cancel.set()
            return
        if not missing:return
        self.cancel=Event();cancel=self.cancel;self.running=True;self.job_keys=missing[:40];keys=self.job_keys;path=self.path
        from .widgets import background
        background(lambda:decode(path,keys,cancel),self.complete,self.failure)

    def complete(self,images):
        self.running=False
        if self.closed:return
        self.images.update(images)
        while len(self.images)>self.LIMIT:self.images.popitem(last=False)
        self.changed.emit();self.request(self.wanted)

    def failure(self,message):
        self.running=False
        if self.closed:return
        self.error=True;self.failed.emit(message)

    def close(self):self.closed=True;self.cancel.set();self.wanted=();self.images.clear()
