"""Resize a local annotation rectangle while preserving its opposite anchor."""
from PySide6.QtCore import QRectF


def resize_rect(width,height,edge,point,proportional=False):
    horizontal='l' in edge or 'r' in edge;vertical='t' in edge or 'b' in edge
    fixed_x=width if 'l' in edge else 0.;fixed_y=height if 't' in edge else 0.
    dx=point.x()-fixed_x if horizontal else width;dy=point.y()-fixed_y if vertical else height
    sx=-1 if dx<0 or (dx==0 and 'l' in edge) else 1;sy=-1 if dy<0 or (dy==0 and 't' in edge) else 1
    if proportional:
        scale=max(abs(dx)/width,abs(dy)/height) if horizontal and vertical else abs(dx)/width if horizontal else abs(dy)/height
        scale=max(scale,8/width,8/height);w,h=width*scale,height*scale
    else:w,h=max(8,abs(dx)) if horizontal else width,max(8,abs(dy)) if vertical else height
    x=fixed_x-w if horizontal and sx<0 else fixed_x if horizontal else (width-w)/2
    y=fixed_y-h if vertical and sy<0 else fixed_y if vertical else (height-h)/2
    return QRectF(x,y,w,h)
