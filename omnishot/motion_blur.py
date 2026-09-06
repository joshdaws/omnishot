"""Time-local shutter sampling for editable cursor and framing motion.

No prior decoded/output frame is retained, so seeking and cut boundaries cannot
carry pixels from a different shot into the current one.
"""
import numpy as np

LEVELS=('None','Low','Medium','High')


def blur_level(options):
    value=options.get('motion_blur',2 if options.get('blur') else 0)
    try:return max(0,min(3,int(value)))
    except (ValueError,TypeError,OverflowError):return 0


def shutter_times(t,options):
    level=blur_level(options)
    if not level:return [t]
    lower=max(0.,float(options.get('start',0)))
    for a,b in options.get('cuts',[]):
        if b<=t:lower=max(lower,b)
        elif a<=t<b:return [t]
    fps=max(1.,float(options.get('fps',30)));speed=max(.01,float(options.get('speed',1)))
    begin=max(lower,t-level/3*speed/fps)
    if begin>=t:return [t]
    return np.linspace(begin,t,9).tolist()


def compose_motion(frame,t,metadata,options,camera,render):
    from .studio import cursor_at
    from .video_motion import zoom_at
    from .editor import qimage
    times=shutter_times(t,options)
    if len(times)==1:return render(frame,t,metadata,options,camera)
    h,w=frame.shape[:2]
    def state(seconds):
        cursor=cursor_at(metadata.get('cursor',[]),seconds)
        scale,x,y=zoom_at(options.get('zooms',[]),seconds,cursor,options.get('zoom_animation','Smooth'))
        x=max(.5/scale,min(1-.5/scale,x));y=max(.5/scale,min(1-.5/scale,y))
        # Compare the mapped source corners and cursor in output pixels.
        values=[(.5-x*scale)*w,(.5-y*scale)*h,scale*w,scale*h]
        if options.get('cursor',True) and cursor:values.extend((cursor['x']*w,cursor['y']*h))
        return values
    states=[state(seconds) for seconds in times]
    if all(len(s)==len(states[-1]) and max(abs(a-b) for a,b in zip(s,states[-1]))<.15 for s in states):
        return render(frame,t,metadata,options,camera)
    accumulation=None
    for seconds in times:
        image=render(frame,seconds,metadata,options,camera)
        pixels=np.asarray(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3)
        if accumulation is None:accumulation=pixels.astype(np.uint16)
        else:accumulation+=pixels
    accumulation+=len(times)//2;accumulation//=len(times)
    return qimage(accumulation.astype(np.uint8))
