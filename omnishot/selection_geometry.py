"""Bounded capture geometry shared by frozen and live selection surfaces."""
from PySide6.QtCore import QRect


def move_selection(rect,dx,dy,bounds):
    x=min(max(rect.x()+dx,bounds.left()),bounds.right()+1-rect.width())
    y=min(max(rect.y()+dy,bounds.top()),bounds.bottom()+1-rect.height())
    return QRect(x,y,rect.width(),rect.height())


def fit_size(width,height,max_width,max_height,minimum=2,ratio=None,driver="width"):
    if ratio:
        width=width if driver=="width" else height*ratio
        width=min(max(width,max(minimum,minimum*ratio)),min(max_width,max_height*ratio))
        height=width/ratio
    else:
        width=min(max(width,minimum),max_width);height=min(max(height,minimum),max_height)
    return max(1,round(width)),max(1,round(height))


def size_selection(rect,width,height,bounds,ratio=None,driver="width",minimum=2):
    x=max(bounds.left(),min(rect.x(),bounds.right()+1-minimum))
    y=max(bounds.top(),min(rect.y(),bounds.bottom()+1-minimum))
    width,height=fit_size(width,height,bounds.right()+1-x,bounds.bottom()+1-y,minimum,ratio,driver)
    return QRect(x,y,width,height)


def resize_selection(rect,edge,dx,dy,bounds,ratio=None,minimum=2):
    horizontal="l" in edge or "r" in edge;vertical="t" in edge or "b" in edge
    ax=rect.x()+rect.width() if "l" in edge else rect.x() if "r" in edge else rect.x()+rect.width()/2
    ay=rect.y()+rect.height() if "t" in edge else rect.y() if "b" in edge else rect.y()+rect.height()/2
    max_width=ax-bounds.left() if "l" in edge else bounds.right()+1-ax if "r" in edge else 2*min(ax-bounds.left(),bounds.right()+1-ax)
    max_height=ay-bounds.top() if "t" in edge else bounds.bottom()+1-ay if "b" in edge else 2*min(ay-bounds.top(),bounds.bottom()+1-ay)
    width=rect.width()+(-dx if "l" in edge else dx if "r" in edge else 0)
    height=rect.height()+(-dy if "t" in edge else dy if "b" in edge else 0)
    driver="width" if horizontal and (not vertical or abs(dx)/rect.width()>=abs(dy)/rect.height()) else "height"
    width,height=fit_size(width,height,max_width,max_height,minimum,ratio,driver)
    x=ax-width if "l" in edge else ax if "r" in edge else ax-width/2
    y=ay-height if "t" in edge else ay if "b" in edge else ay-height/2
    return QRect(round(x),round(y),width,height)
