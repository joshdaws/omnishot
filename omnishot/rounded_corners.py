"""Editable window corner contours, including Hyprland's superellipse power."""
import math
from functools import lru_cache
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath


def rounded_path(rect,radius,power=2):
    radius=float(radius);power=float(power)
    if not math.isfinite(radius):radius=0
    if not math.isfinite(power):power=2
    radius=max(0,min(radius,rect.width()/2,rect.height()/2));power=max(1,min(10,power))
    return QPainterPath(_outline(*rect.getRect(),radius,power))


@lru_cache(maxsize=128)
def _outline(x,y,w,h,r,power):
    path=QPainterPath();rect=QRectF(x,y,w,h)
    if not r:path.addRect(rect);return path
    if power==2:path.addRoundedRect(rect,r,r);return path
    path.moveTo(x+r,y)
    for cx,cy,start in [(x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)]:
        for i in range(65):
            angle=start+i*math.pi/128;c=math.cos(angle);s=math.sin(angle)
            path.lineTo(cx+r*math.copysign(abs(c)**(2/power),c),cy+r*math.copysign(abs(s)**(2/power),s))
    path.closeSubpath();return path
