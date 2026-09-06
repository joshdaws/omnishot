"""Editable recording metadata and deterministic local video composition.

Input observation is opt-in, scoped to a recording, and removed on stop. The
compositor watchdog removes its subscriptions if the recorder process exits.
"""
from __future__ import annotations
import bisect
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import ctypes
import base64
from functools import lru_cache
import cv2
import numpy as np
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QColor,QPen,QPainterPath,QFont,QLinearGradient
from . import backend
from .editor import qimage


class KeyNames:
    """Translate captured XKB keycodes using the configured keyboard layout."""
    def __init__(self):
        class Names(ctypes.Structure):
            _fields_=[(name,ctypes.c_char_p) for name in ("rules","model","layout","variant","options")]
        self.lib=ctypes.CDLL("libxkbcommon.so.0");lib=self.lib;ptr=ctypes.c_void_p
        for name,restype,args in [
            ("xkb_context_new",ptr,[ctypes.c_int]),("xkb_keymap_new_from_names",ptr,[ptr,ctypes.POINTER(Names),ctypes.c_int]),
            ("xkb_state_new",ptr,[ptr]),("xkb_state_update_key",ctypes.c_int,[ptr,ctypes.c_uint32,ctypes.c_int]),
            ("xkb_state_key_get_one_sym",ctypes.c_uint32,[ptr,ctypes.c_uint32]),
            ("xkb_keysym_get_name",ctypes.c_int,[ctypes.c_uint32,ctypes.c_char_p,ctypes.c_size_t]),
            ("xkb_state_mod_name_is_active",ctypes.c_int,[ptr,ctypes.c_char_p,ctypes.c_int]),
            ("xkb_state_unref",None,[ptr]),("xkb_keymap_unref",None,[ptr]),("xkb_context_unref",None,[ptr])]:
            fn=getattr(lib,name);fn.restype=restype;fn.argtypes=args
        try:layout=json.loads(backend.run(["hyprctl","getoption","input:kb_layout","-j"]))["str"].split(",")[0]
        except Exception:layout="us"
        self.context=lib.xkb_context_new(0);self.keymap=lib.xkb_keymap_new_from_names(self.context,ctypes.byref(Names(None,None,layout.encode(),None,None)),0);self.state=lib.xkb_state_new(self.keymap)
    def label(self,code,state,commands_only=False):
        self.lib.xkb_state_update_key(self.state,code,1 if state else 0)
        if state!=1:return ""
        sym=self.lib.xkb_state_key_get_one_sym(self.state,code);buf=ctypes.create_string_buffer(96);self.lib.xkb_keysym_get_name(sym,buf,len(buf));name=buf.value.decode()
        if name in {"Shift_L","Shift_R","Control_L","Control_R","Alt_L","Alt_R","Super_L","Super_R","ISO_Level3_Shift"}:return ""
        mods=[label for key,label in [(b"Control","Ctrl"),(b"Mod1","Alt"),(b"Mod4","Super"),(b"Shift","Shift")] if self.lib.xkb_state_mod_name_is_active(self.state,key,1<<3)>0]
        if commands_only and not any(m in mods for m in ("Ctrl","Alt","Super")):return ""
        name={"Return":"Enter","BackSpace":"Backspace","space":"Space","Escape":"Esc"}.get(name,name.upper() if len(name)==1 else name)
        return "+".join(mods+[name])
    def close(self):
        self.lib.xkb_state_unref(self.state);self.lib.xkb_keymap_unref(self.keymap);self.lib.xkb_context_unref(self.context)


class Telemetry:
    def __init__(self,rect,keys=False,clicks=False,commands_only=True):
        self.rect=rect;self.keys=keys;self.clicks=clicks;self.commands_only=commands_only;self.samples=[];self.events=[]
        self.stop_event=threading.Event();self.thread=None;self.pauses=[];self.pause_started=None;self.error=None;self.locked=False
        self.data_lock=threading.RLock()
    def start(self):
        # No persistent keyboard binding or log is installed. Queue storage is
        # bounded, and an independent compositor timer watches the owner PID.
        code='''
if omnishot_capture then
  if omnishot_capture.key then omnishot_capture.key:remove() end
  for _,b in ipairs(omnishot_capture.buttons or {}) do b:remove() end
  if omnishot_capture.watch then omnishot_capture.watch:set_enabled(false) end
end
omnishot_capture={queue={},buttons={}}
local s=omnishot_capture
local function add(v)
  if #s.queue<256 then table.insert(s.queue,v) end
end
'''
        if self.keys:
            code+='''s.key=hl.on("input.keyboard.key",function(key,t,state)
  add("key,"..tostring(key)..","..tostring(state)..","..(s.paused and "1" or "0"))
end)
'''
        if self.clicks:
            occupied={(b.get("modmask",0),b.get("key","").casefold()) for b in backend.hypr("binds")}
            buttons=",".join(str(n) for n in (272,273,274) if (0,f"mouse:{n}") not in occupied)
            code+='''for _,n in ipairs({OMNISHOT_BUTTONS}) do
  table.insert(s.buttons,hl.bind("mouse:"..n,function()
    if s.paused then return end
    local p=hl.get_cursor_pos()
    for _,w in ipairs(hl.get_windows({mapped=true})) do
      if w.pid==OMNISHOT_OWNER and w.visible and (w.title=="OmniShot Recording Controls" or w.title=="OmniShot Camera Preview") then
        local a,z=w.at,w.size
        if p.x>=a.x and p.y>=a.y and p.x<a.x+z.x and p.y<a.y+z.y then return end
      end
    end
    add("click,"..n..","..p.x..","..p.y)
  end,{non_consuming=true,ignore_mods=true,transparent=true,description="OmniShot recording click marker"}))
end
'''
        code+=f'''s.owner={os.getpid()}
if not omnishot_capture_watch then
  omnishot_capture_watch=hl.timer(function()
    local current=omnishot_capture
    if current then
      local f=io.open("/proc/"..current.owner.."/stat","r")
      if f then f:close();return end
      if current.key then current.key:remove() end
      for _,b in ipairs(current.buttons or {{}}) do b:remove() end
      omnishot_capture=nil
    end
    omnishot_capture_watch:set_enabled(false)
  end,{{timeout=1000,type="repeat"}})
else omnishot_capture_watch:set_enabled(true) end
s.watch=omnishot_capture_watch
'''
        backend.run(["hyprctl","eval",code.replace("OMNISHOT_OWNER",str(os.getpid())).replace("OMNISHOT_BUTTONS",buttons if self.clicks else "")]);self.thread=threading.Thread(target=self._poll,name="omnishot-recording-pointer",daemon=True);self.thread.start()
    def _poll(self):
        names=KeyNames() if self.keys else None
        while not self.stop_event.wait(.035):
            try:
                reply=backend.run(["hyprctl","repl",'''local p=hl.get_cursor_pos(); local q=omnishot_capture and omnishot_capture.queue or {}; if omnishot_capture then omnishot_capture.queue={} end; return tostring(p.x)..","..tostring(p.y).."\\n"..table.concat(q,"\\n")'''],timeout=2).decode().strip()
                rows=reply.splitlines();now=time.monotonic();x,y=map(float,rows[0].split(","));rx,ry,rw,rh=self.rect
                if len(rows)>1 and backend.session_locked(backend.hypr("monitors")):
                    self.locked=True;self.error="Recording stopped because the session locked";break
                events=[]
                for row in rows[1:]:
                    parts=row.split(",")
                    if parts[0]=="key":
                        code,state=int(parts[1]),int(parts[2]);label=names.label(code,state,self.commands_only) if names else ""
                        if label and (len(parts)<4 or parts[3]!="1"):
                            from .video_keys import command_event
                            events.append({"t":now,"kind":"key","state":state,"label":label,"command":command_event({'label':label})})
                    elif parts[0]=="click":events.append({"t":now,"kind":"click","button":int(parts[1]),"x":(float(parts[2])-rx)/rw,"y":(float(parts[3])-ry)/rh})
                with self.data_lock:
                    # Drain modifier transitions while paused, but do not retain
                    # or checkpoint input that the user paused recording for.
                    if self.pause_started is None:
                        self.samples.append({"t":now,"x":(x-rx)/rw,"y":(y-ry)/rh});self.events.extend(events)
            except Exception as exc:self.error=str(exc);break
        if names:names.close()
    def pause(self,paused):
        with self.data_lock:
            if paused and self.pause_started is None:self.pause_started=time.monotonic()
            elif not paused and self.pause_started is not None:self.pauses.append([self.pause_started,time.monotonic()]);self.pause_started=None
        # Tag keys at delivery so an event queued during a pause cannot leak
        # into a checkpoint when polling resumes. Modifier state still drains.
        try:backend.run(["hyprctl","eval",f"if omnishot_capture and omnishot_capture.owner=={os.getpid()} then omnishot_capture.paused={'true' if paused else 'false'} end"],timeout=2)
        except (OSError,RuntimeError) as exc:self.error=str(exc)
    def stop(self,first_frame_time=None):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=3)
        try:backend.run(["hyprctl","eval",'''if omnishot_capture then local s=omnishot_capture; if s.key then s.key:remove() end; for _,b in ipairs(s.buttons) do b:remove() end; if s.watch then s.watch:set_enabled(false) end; omnishot_capture=nil end'''],timeout=3)
        except Exception:pass
        return self.snapshot(first_frame_time)[0]

    def snapshot(self,first_frame_time=None,after=(0,0)):
        """Return a consistent, pause-normalized delta without stopping capture."""
        with self.data_lock:
            now=time.monotonic();samples=self.samples[after[0]:];events=self.events[after[1]:]
            offsets=(len(self.samples),len(self.events));pauses=list(self.pauses)
            if self.pause_started is not None:pauses.append([self.pause_started,now])
            origin=first_frame_time or (self.samples[0]["t"] if self.samples else now)
        def normalize(rows):
            out=[]
            for row in rows:
                t=row["t"]
                if t<origin or any(a<=t<=b for a,b in pauses):continue
                p=dict(row);p["t"]=t-origin-sum(max(0,min(t,b)-max(origin,a)) for a,b in pauses if a<t);out.append(p)
            return out
        return {"version":1,"rect":self.rect,"cursor":normalize(samples),"events":normalize(events),"telemetry_error":self.error},offsets


def smooth_cursor(samples,strength=.75):
    if not samples:return []
    out=[dict(samples[0])]
    for sample in samples[1:]:
        prev=out[-1];dt=max(.001,sample["t"]-prev["t"]);alpha=1-math.exp(-dt/max(.005,strength*.12))
        out.append({"t":sample["t"],"x":prev["x"]+alpha*(sample["x"]-prev["x"]),"y":prev["y"]+alpha*(sample["y"]-prev["y"])})
    return out


def cursor_at(samples,t):
    if not samples:return None
    index=bisect.bisect_right(samples,t,key=lambda p:p["t"])-1
    if index<0:return samples[0]
    if index>=len(samples)-1:return samples[-1]
    a,b=samples[index],samples[index+1];f=(t-a["t"])/max(.0001,b["t"]-a["t"])
    return {"x":a["x"]+(b["x"]-a["x"])*f,"y":a["y"]+(b["y"]-a["y"])*f}


def smart_zooms(events,duration=2.8,scale=1.8,limit=None):
    result=[]
    for event in events:
        if event.get("kind")!="click" or event.get("hidden"):continue
        t=event["t"]
        if t<0 or not 0<=event.get('x',-1)<=1 or not 0<=event.get('y',-1)<=1 or (limit is not None and t>=limit):continue
        if result and t<result[-1]["end"]-.3:continue
        a=max(0,t-.45,result[-1]["end"] if result else 0);b=min(t+duration,limit) if limit is not None else t+duration
        if b<=a:continue
        result.append({"start":a,"end":b,"scale":scale,"x":event["x"],"y":event["y"],"follow":True})
    return result


from .video_motion import zoom_at


@lru_cache(maxsize=3)
def background_image(data):
    return QImage.fromData(base64.b64decode(data))


def edited_events(metadata,opts):
    events=metadata.get("events",[]);edits=opts.get("event_edits",{})
    if not edits:return events
    return sorted(({**event,**{k:v for k,v in edits.get(str(i),{}).items() if k in ("t","label","hidden")}} for i,event in enumerate(events)),key=lambda e:e["t"])


def compose_frame(frame,t,metadata,opts,camera=None):
    """Render all effects before encoding, shared by preview and final export."""
    from .motion_blur import compose_motion
    canvas=compose_motion(frame,t,metadata,opts,None,lambda frame,t,metadata,opts,_:compose_screen(frame,t,metadata,opts)[0])
    zoom=zoom_at(opts.get('zooms',[]),t,cursor_at(metadata.get('cursor',[]),t),opts.get('zoom_animation','Smooth'))[0]
    return compose_scene(canvas,t,metadata,opts,camera,zoom)


def compose_sharp_frame(frame,t,metadata,opts,camera=None):
    canvas,zoom=compose_screen(frame,t,metadata,opts)
    return compose_scene(canvas,t,metadata,opts,camera,zoom)


def compose_screen(frame,t,metadata,opts):
    h,w=frame.shape[:2];canvas=qimage(frame);p=QPainter(canvas);p.setRenderHint(QPainter.RenderHint.Antialiasing);events=edited_events(metadata,opts)
    cursor=cursor_at(metadata.get("cursor",[]),t)
    if cursor and opts.get("cursor",True) and 0<=cursor["x"]<=1 and 0<=cursor["y"]<=1:
        from .cursor_shape import paint_cursor
        from .video_clicks import press_scale
        size=opts.get("cursor_size",28)*(press_scale(events,t) if opts.get('click_press',False) else 1)
        paint_cursor(p,QPointF(cursor["x"]*w,cursor["y"]*h),size,opts.get("cursor_style","Arrow"),opts.get("cursor_color","#161821"),opts.get("cursor_outline","white"))
    if opts.get("clicks",True):
        for event in events:
            age=t-event["t"]
            duration=max(.1,opts.get("click_duration",.5))
            if event.get("kind")=="click" and 0<=age<duration and not event.get("hidden"):
                color=QColor(opts.get("click_color","#ff6565"));color.setAlphaF(color.alphaF()*(1-age/duration)*.8);radius=opts.get("click_size",24)*(1+age/duration*.5)
                p.setPen(QPen(color,3));p.setBrush(color if opts.get("click_style")=="filled" else Qt.BrushStyle.NoBrush);p.drawEllipse(QPointF(event["x"]*w,event["y"]*h),radius,radius)
    p.end();zoom,zx,zy=zoom_at(opts.get("zooms",[]),t,cursor,opts.get("zoom_animation","Smooth"))
    if zoom>1:
        cw,ch=w/zoom,h/zoom;x=max(0,min(w-cw,zx*w-cw/2));y=max(0,min(h-ch,zy*h-ch/2));canvas=canvas.copy(round(x),round(y),round(cw),round(ch)).scaled(w,h,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
    return canvas,zoom


def compose_scene(canvas,t,metadata,opts,camera,zoom):
    from .camera_framing import options_at
    opts=options_at(metadata,opts,t)
    w,h=canvas.width(),canvas.height();events=edited_events(metadata,opts)
    width=int(opts.get("width",w)) or w;content_h=round(h*width/w);padding=int(opts.get("padding",0));ow=width+2*padding;oh=content_h+2*padding
    aspect=opts.get("aspect","Original")
    if aspect!="Original":
        a,b=map(float,aspect.split(":"));ow=max(ow,round(oh*a/b));oh=max(oh,round(ow*b/a))
    ow+=ow%2;oh+=oh%2;output=QImage(ow,oh,QImage.Format.Format_RGB888);output.fill(QColor(opts.get("background","#25324b")))
    p=QPainter(output);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    if opts.get("background2"):
        gradient=QLinearGradient(0,0,ow,oh);gradient.setColorAt(0,QColor(opts["background"]));gradient.setColorAt(1,QColor(opts["background2"]));p.fillRect(output.rect(),gradient)
    if opts.get("background_image_data"):
        bg=background_image(opts["background_image_data"])
        if not bg.isNull():
            ratio=max(ow/bg.width(),oh/bg.height());sw=ow/ratio;sh=oh/ratio;p.drawImage(QRectF(output.rect()),bg,QRectF((bg.width()-sw)/2,(bg.height()-sh)/2,sw,sh))
    align=opts.get("align","Center");x=padding if "Left" in align else ow-width-padding if "Right" in align else (ow-width)/2;y=padding if "Top" in align else oh-content_h-padding if "Bottom" in align else (oh-content_h)/2
    r=QRectF(x,y,width,content_h);radius=opts.get("radius",12) if padding else 0
    if padding and opts.get("shadow",True):
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(15,0,-1):p.setBrush(QColor(0,0,0,3));p.drawRoundedRect(r.adjusted(-i,-i*.4,i,i),radius+i,radius+i)
    clip=QPainterPath();clip.addRoundedRect(r,radius,radius);p.setClipPath(clip);p.drawImage(r,canvas);p.setClipping(False)
    if camera is not None and opts.get("camera",True):
        from .video_position import camera_rect
        shape=opts.get("camera_shape","Circle");r=camera_rect(ow,oh,camera.shape[0]/camera.shape[1],opts,zoom)
        mask=QPainterPath()
        if shape=="Circle" and not opts.get("camera_fullscreen"):mask.addEllipse(r)
        else:
            radius=opts.get("camera_radius",18) if shape in ("Rounded","Square") and not opts.get("camera_fullscreen") else 0
            mask.addRoundedRect(r,radius,radius)
        if opts.get("camera_shadow",True) and not opts.get("camera_fullscreen"):
            p.setPen(Qt.PenStyle.NoPen)
            for spread in range(12,0,-1):
                p.setBrush(QColor(0,0,0,4));shadow_rect=r.adjusted(-spread,-spread/2,spread,spread)
                if shape=="Circle":p.drawEllipse(shadow_rect)
                else:p.drawRoundedRect(shadow_rect,opts.get("camera_radius",18)+spread if shape in ("Rounded","Square") else spread,opts.get("camera_radius",18)+spread if shape in ("Rounded","Square") else spread)
        camera_image=qimage(camera)
        if opts.get("camera_mirror"):camera_image=camera_image.flipped(Qt.Orientation.Horizontal)
        source_ratio=camera_image.width()/camera_image.height();target_ratio=r.width()/r.height()
        sw=camera_image.height()*target_ratio if source_ratio>target_ratio else camera_image.width()
        sh=camera_image.width()/target_ratio if source_ratio<target_ratio else camera_image.height()
        source=QRectF((camera_image.width()-sw)/2,(camera_image.height()-sh)/2,sw,sh)
        p.setClipPath(mask);p.drawImage(r,camera_image,source);p.setClipping(False)
    if opts.get("keys",True):
        from .video_keys import visible_keys,key_colors
        keys=visible_keys(events,t,opts,metadata)
        if keys:
            label="  ".join(keys[-5:]);font=QFont(opts.get("key_font","sans-serif"),opts.get("key_size",20));font.setBold(True);p.setFont(font)
            label=p.fontMetrics().elidedText(label,Qt.TextElideMode.ElideLeft,max(1,ow-76));bounds=p.fontMetrics().boundingRect(label);bw=min(ow-40,bounds.width()+36);bh=bounds.height()+20
            position=opts.get("key_position","Bottom Center");x=20 if "Left" in position else ow-bw-20 if "Right" in position else (ow-bw)/2;y=24 if "Top" in position else oh-bh-24 if 'Bottom' in position else (oh-bh)/2;r=QRectF(x,y,bw,bh)
            background,foreground=key_colors(opts)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(background));p.drawRoundedRect(r,12,12);p.setPen(QColor(foreground));p.drawText(r,Qt.AlignmentFlag.AlignCenter,label)
    p.end();return output


def kept_segments(start,end,cuts):
    segments=[];cursor=start
    for a,b in sorted(cuts):
        if b<=cursor or a>=end:continue
        if a>cursor:segments.append((cursor,min(a,end)))
        cursor=max(cursor,b)
    if cursor<end:segments.append((cursor,end))
    return segments


def export_studio(source,destination,metadata,opts,progress=None,cancel=None):
    capture=cv2.VideoCapture(str(source))
    if not capture.isOpened():raise ValueError("Cannot open source recording")
    source_fps=capture.get(cv2.CAP_PROP_FPS) or 30;duration=capture.get(cv2.CAP_PROP_FRAME_COUNT)/source_fps
    start=opts.get("start",0);end=min(opts.get("end",0) or duration,duration);fps=opts.get("fps",30);speed=opts.get("speed",1)
    segments=kept_segments(start,end,opts.get("cuts",[]));counts=[max(0,int((b-a)*fps/speed)) for a,b in segments];total=sum(counts)
    if not total:capture.release();raise ValueError("The edit contains no frames")
    first_time=next(a for (a,b),count in zip(segments,counts) if count)
    times=(a+i*speed/fps for (a,b),count in zip(segments,counts) for i in range(count))
    meta=dict(metadata);meta["cursor"]=smooth_cursor(metadata.get("cursor",[]),opts.get("smoothing",.75)) if opts.get("smoothing") else metadata.get("cursor",[])
    meta["events"]=edited_events(metadata,opts);opts=dict(opts);opts.pop("event_edits",None)
    capture.set(cv2.CAP_PROP_POS_MSEC,first_time*1000);ok,frame=capture.read()
    if not ok:capture.release();raise ValueError("Could not decode recording")
    first=compose_frame(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),first_time,meta,opts);w,h=first.width(),first.height()
    destination=Path(destination);partial=destination.with_name(destination.stem+".partial"+destination.suffix)
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24","-video_size",f"{w}x{h}","-framerate",str(fps),"-i","pipe:0","-ss",str(start),"-i",str(source),"-map","0:v"]
    if opts.get("hardware"):
        cmd[5:5]=["-vaapi_device",opts.get("render_device","/dev/dri/renderD128")]
        cmd.extend(["-vf","format=nv12,hwupload","-c:v","h264_vaapi","-qp","22"])
    else:cmd.extend(["-c:v","libx264","-crf","20","-preset","fast","-pix_fmt","yuv420p"])
    af=[]
    if opts.get("cuts"):
        expr="+".join(f"between(t,{max(0,a-start)},{max(0,b-start)})" for a,b in opts["cuts"] if b>start)
        if expr:af.extend([f"aselect='not({expr})'","asetpts=N/SR/TB"])
    if speed!=1:af.append(f"atempo={speed}")
    from .video_audio_tracks import export_audio_args
    cmd.extend(export_audio_args(opts,1,af))
    cmd.extend(["-c:a","aac","-shortest","-movflags","+faststart",str(partial)])
    camera=cv2.VideoCapture(str(metadata["camera_path"])) if metadata.get("camera_path") else None
    try:
        with tempfile.TemporaryFile() as log:
            process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            try:
                last_index=-2
                for i,t in enumerate(times):
                    if cancel and cancel.is_set():raise InterruptedError("Export cancelled")
                    index=int(t*source_fps)
                    if index!=last_index:
                        if index!=last_index+1:capture.set(cv2.CAP_PROP_POS_FRAMES,index)
                        ok,frame=capture.read()
                        if not ok:raise RuntimeError(f"Could not decode frame {index}")
                        last_index=index
                    camera_frame=None
                    if camera and camera.isOpened():
                        camera.set(cv2.CAP_PROP_POS_MSEC,max(0,t-metadata.get("camera_offset",0))*1000);valid,cam=camera.read()
                        if valid:camera_frame=cv2.cvtColor(cam,cv2.COLOR_BGR2RGB)
                    rendered=compose_frame(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),t,meta,opts,camera_frame)
                    pixels=np.asarray(rendered.bits(),dtype=np.uint8).reshape(h,rendered.bytesPerLine())[:,:w*3].reshape(h,w,3).copy()
                    process.stdin.write(pixels.tobytes())
                    if progress and i%max(1,int(fps/3))==0:progress(int(i/total*100))
                process.stdin.close()
                while process.poll() is None:
                    if cancel and cancel.is_set():raise InterruptedError("Export cancelled")
                    try:process.wait(timeout=.2)
                    except subprocess.TimeoutExpired:pass
                code=process.returncode
                if code:log.seek(0);raise RuntimeError(log.read().decode(errors="replace")[-2000:])
            except Exception:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                log.seek(0);message=log.read().decode(errors="replace")[-2000:]
                if message:raise RuntimeError(message)
                raise
        partial.replace(destination)
        if progress:progress(100)
    finally:
        capture.release()
        if camera:camera.release()
        partial.unlink(missing_ok=True)
