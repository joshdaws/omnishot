"""Pause-aware camera framing changes on the screen recording's source clock."""
import threading
import time


class CameraFraming:
    def __init__(self):
        self.events=[];self.pauses=[];self.pause_started=None;self.fullscreen=False;self.shape=None;self.placement=None;self.lock=threading.Lock()

    def set_fullscreen(self,value):
        with self.lock:
            if self.fullscreen==bool(value):return
            self.fullscreen=bool(value);self._append()

    def set_shape(self,value):
        if value not in ('Circle','Square','Rounded','Rectangle'):raise ValueError('Invalid camera shape')
        with self.lock:
            if self.shape==value:return
            self.shape=value;self._append()

    def _append(self):
        event=dict(t=time.monotonic(),fullscreen=self.fullscreen)
        if self.shape is not None:event['shape']=self.shape
        if self.placement is not None:event['placement']=list(self.placement)
        self.events.append(event)

    def set_placement(self,value):
        placement=tuple(value)
        with self.lock:
            if self.placement==placement:return
            self.placement=placement;self._append()

    def pause(self,value):
        with self.lock:
            if value and self.pause_started is None:self.pause_started=time.monotonic()
            elif not value and self.pause_started is not None:self.pauses.append((self.pause_started,time.monotonic()));self.pause_started=None

    def snapshot(self,origin):
        if origin is None:return []
        with self.lock:
            rows=list(self.events);pauses=list(self.pauses)
            if self.pause_started is not None:pauses.append((self.pause_started,time.monotonic()))
        result=[]
        for row in rows:
            t=row['t'];stamp=max(0,t-origin-sum(max(0,min(t,b)-max(origin,a)) for a,b in pauses if a<t))
            value={**row,'t':stamp}
            if result and abs(result[-1]['t']-stamp)<1e-7:result[-1]=value
            else:result.append(value)
        return result


def options_at(metadata,options,t):
    if not options.get('camera_recorded_framing',True) or options.get('camera_fullscreen'):return options
    changes=dict(camera_fullscreen=False)
    for event in metadata.get('camera_framing',[]):
        if event['t']>t:break
        changes['camera_fullscreen']=event['fullscreen']
        if 'shape' in event:changes['camera_shape']=event['shape']
        if 'placement' in event:changes['camera_placement']=event['placement']
    return {**options,**changes}
