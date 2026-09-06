"""Lifecycle for the clean Hyprland mirror and GSR capture source."""
from __future__ import annotations
import os
import threading
from pathlib import Path
from . import backend

NATIVE = Path(__file__).resolve().parent.parent / "native"


class MirrorLease:
    lock=threading.RLock()
    loaded_path=None
    roles={}
    def __init__(self,role):self.role=role;self.enabled=False
    def start(self):
        with self.lock:
            if self.enabled:return
            if self.roles.get(self.role,0):
                self.roles[self.role]+=1;self.enabled=True;return
            if not (NATIVE/'clean-mirror.so').is_file():raise RuntimeError("OmniShot's capture components need rebuilding. Run install.sh from the OmniShot folder.")
            if not any(p.get('name')=='omnishot-clean-mirror' for p in backend.hypr('plugin list')):
                path=(NATIVE/'clean-mirror.so').resolve();backend.run(['hyprctl','plugin','load',path]);MirrorLease.loaded_path=path
            try:backend.run(['hyprctl','eval',f'hl.plugin.omnishot.{self.role}({os.getpid()})'])
            except Exception:
                try:self.unload_unused()
                except Exception:pass
                raise
            self.roles[self.role]=self.roles.get(self.role,0)+1;self.enabled=True
    def stop(self):
        with self.lock:
            if not self.enabled:self.unload_unused();return
            remaining=self.roles[self.role]-1
            if not remaining:backend.run(['hyprctl','eval',f'hl.plugin.omnishot.{self.role}(0)'])
            self.roles[self.role]=remaining;self.enabled=False
            self.unload_unused()
    def __enter__(self):
        self.start();return self
    def __exit__(self,exc_type,exc_value,traceback):
        self.stop()
    @classmethod
    def unload_unused(cls):
        if not any(cls.roles.values()) and MirrorLease.loaded_path:
            active=backend.run(['hyprctl','repl','return tostring(hl.plugin.omnishot.capture_active())']).decode().strip()
            if active=='false':
                backend.run(['hyprctl','plugin','unload',MirrorLease.loaded_path]);MirrorLease.loaded_path=None


class SelectionMirror(MirrorLease):
    def __init__(self):super().__init__('selection_capture')


class CursorMirror(MirrorLease):
    """Keep software pointers out of screencopy without excluding app surfaces."""
    def __init__(self):super().__init__('cursor_capture')


def monitor_bounds(monitor):
    width,height=monitor["width"],monitor["height"]
    if monitor.get("transform",0)%2:width,height=height,width
    return monitor["x"],monitor["y"],round(width/monitor["scale"]),round(height/monitor["scale"])


def capture_target(monitors, rect=None):
    """Choose a whole output or a region entirely contained on one output.

    Return None for a selection requiring the composite output source.
    """
    if not monitors:
        raise RuntimeError("No display is available for recording")
    for monitor in monitors:
        bounds=monitor_bounds(monitor);width,height=bounds[2:]
        if rect is None:
            if monitor.get("focused") or len(monitors) == 1:
                return monitor["name"], None, bounds
        else:
            x, y, w, h = rect
            if w < 2 or h < 2:
                raise ValueError("The recording area is too small")
            if x >= bounds[0] and y >= bounds[1] and x+w <= bounds[0]+width and y+h <= bounds[1]+height:
                return monitor["name"], (x-bounds[0], y-bounds[1], w, h), bounds
    if rect is None:
        return capture_target([monitors[0]])
    return None


class CleanCapture:
    def __init__(self, monitors, rect, cursor=False):
        self.target = capture_target(monitors, rect)
        self.encoder_rect=rect
        self.parts=[]
        if self.target is None:
            x,y,w,h=rect
            for monitor in monitors:
                mx,my,mw,mh=monitor_bounds(monitor)
                left,top=max(x,mx),max(y,my);right,bottom=min(x+w,mx+mw),min(y+h,my+mh)
                if right>left and bottom>top:
                    self.parts.append((monitor['name'],left-mx,top-my,right-left,bottom-top,left-x,top-y))
            if not self.parts:raise ValueError('The recording area does not overlap a connected display.')
            self.target=(None,None,tuple(rect))
            name=max(self.parts,key=lambda part:part[3]*part[4])[0]
            self.controls_bounds=monitor_bounds(next(m for m in monitors if m['name']==name))
            # GSR initializes its base source from the region's center before
            # the plugin draws. A center in a display gap needs a valid output
            # for that initialization; the plugin still captures the exact
            # original region, including the gap.
            cx,cy=x+w//2,y+h//2
            if not any(mx<=cx<mx+mw and my<=cy<my+mh for mx,my,mw,mh in map(monitor_bounds,monitors)):
                mx,my,mw,mh=self.controls_bounds
                self.encoder_rect=(mx+mw//2-w//2,my+mh//2-h//2,w,h)
        else:self.controls_bounds=self.target[2]
        self.cursor = cursor
        self.enabled = False
        self.lease = MirrorLease("clean_capture")

    def start(self):
        for name in ("clean-mirror.so", "clean-capture.so"):
            if not (NATIVE / name).is_file():
                raise RuntimeError("OmniShot's recording components need rebuilding. Run install.sh from the OmniShot folder.")
        self.lease.start()
        self.enabled = True
        return True

    def environment(self):
        env = dict(os.environ)
        # Do not inherit test sockets or a stale region from a parent process.
        for key in ("OMNISHOT_CAPTURE_SOCKET", "OMNISHOT_CAPTURE_REGION", "OMNISHOT_CAPTURE_OUTPUT", "OMNISHOT_CAPTURE_CURSOR", "OMNISHOT_CAPTURE_PARTS"):
            env.pop(key, None)
        if self.enabled:
            output, region, _ = self.target
            env['OMNISHOT_CAPTURE_CURSOR']="1" if self.cursor else "0"
            if self.parts:
                w,h=self.target[2][2:]
                env['OMNISHOT_CAPTURE_PARTS']='\n'.join([f'{w},{h}']+[
                    f'{name}\t{x},{y} {pw}x{ph}\t{dx},{dy}' for name,x,y,pw,ph,dx,dy in self.parts])
            else:env['OMNISHOT_CAPTURE_OUTPUT']=output
            if region:
                x, y, w, h = region
                env["OMNISHOT_CAPTURE_REGION"] = f"{x},{y} {w}x{h}"
        return env

    def stop(self):
        if self.enabled:
            self.lease.stop()
            self.enabled = False
