"""Omarchy UI units, separate from Wayland scale and document/image coordinates."""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import tomllib
import weakref

from PySide6.QtCore import QSize,QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication,QWidget
from shiboken6 import isValid


@dataclass(frozen=True)
class Appearance:
    font_size: int = 12
    spacing: float = 1.0
    font_spacing: bool = True

    @property
    def factor(self):return self.spacing * (self.font_size / 12 if self.font_spacing else 1)


current = Appearance()
_bindings = weakref.WeakKeyDictionary()
_callbacks = weakref.WeakKeyDictionary()
_screens = None


def paths():
    config=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    theme=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'omarchy/current/theme/shell.toml'
    if not theme.exists():theme=config/'omarchy/current/theme/shell.toml'
    return theme,config/'omarchy/shell.toml'


def read(candidates=None):
    font={};spacing={}
    for path in paths() if candidates is None else candidates:
        try:
            with Path(path).open('rb') as file:data=tomllib.load(file)
        except FileNotFoundError:continue
        except (OSError,ValueError):return None
        for section,target in (('font',font),('spacing',spacing)):
            if isinstance(data.get(section),dict):target.update(data[section])
    try:
        size=max(1,int(font.get('base-size',12)))
        factor=float(spacing.get('scale',1))
        if not math.isfinite(factor) or factor<0:return None
        follows=spacing.get('scale-with-font',True)
        if isinstance(follows,str):follows=follows.lower() not in ('false','0','no','off')
        return Appearance(size,factor,bool(follows))
    except (ValueError,TypeError,OverflowError):return None


def px(value):return round(value*current.factor)

def size(width,height):return QSize(max(1,px(width)),max(1,px(height)))


def stylesheet(text):
    def declaration(match):
        prop,value=match.groups()
        factor=current.font_size/12 if prop.strip()=='font-size' else current.factor
        return prop+':'+re.sub(r'(-?\d+(?:\.\d+)?)px',lambda m:f'{round(float(m[1])*factor)}px',value)
    return re.sub(r'([\w-]+)\s*:([^;{}]+)',declaration,text)


def _apply(widget,method,args):
    if not isValid(widget):return
    if method=='setStyleSheet':values=[stylesheet(args[0])]
    else:values=[size(a.width(),a.height()) if isinstance(a,QSize) else px(a) for a in args]
    if method in ('resize','setMinimumSize') and isinstance(widget,QWidget) and widget.isWindow():
        screen=widget.screen() or QApplication.primaryScreen()
        if screen and len(values)==2:
            bounds=screen.availableGeometry()
            values=[min(values[0],round(bounds.width()*.95)),min(values[1],round(bounds.height()*.95))]
    getattr(widget,method)(*values)


def set(widget,method,*args):
    """Bind an explicit UI measurement to the active Omarchy spacing scale."""
    _bindings.setdefault(widget,{})[method]=args
    _apply(widget,method,args)


def watch(widget,method):
    """Refresh image thumbnails/placement after UI units change, not source pixels."""
    _callbacks.setdefault(widget,[]).append(method)


def apply(app,appearance):
    global current
    if appearance==current:return False
    current=appearance
    font=QFont(app.font());font.setPixelSize(current.font_size);app.setFont(font)
    for widget,methods in list(_bindings.items()):
        if not isValid(widget):continue
        for method,args in methods.items():_apply(widget,method,args)
    refresh_callbacks()
    return True


def refresh_callbacks():
    for widget,methods in list(_callbacks.items()):
        reference=weakref.ref(widget)
        def refresh(reference=reference,methods=tuple(methods)):
            widget=reference()
            if widget is not None and isValid(widget):
                for method in methods:getattr(widget,method)()
        # Run after the application stylesheet has been re-polished.
        QTimer.singleShot(0,refresh)


def fit_windows():
    global _screens
    screens=tuple((screen.name(),screen.availableGeometry().getRect()) for screen in QApplication.screens())
    if screens!=_screens:
        _screens=screens;refresh_callbacks()
    # Monitor scale changes alter available logical geometry. Qt handles DPR;
    # only keep ordinary UI windows within their new usable screen bounds.
    for widget,methods in list(_bindings.items()):
        if not isValid(widget) or 'resize' not in methods or not widget.isWindow():continue
        screen=widget.screen()
        if not screen:continue
        bounds=screen.availableGeometry()
        if QWidget.width(widget)>bounds.width() or QWidget.height(widget)>bounds.height():
            _apply(widget,'resize',methods['resize'])
