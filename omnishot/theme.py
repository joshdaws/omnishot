"""One application appearance, derived from Omarchy's current palette.

Omarchy atomically replaces its current/theme directory. Polling the small
palette file also handles that replacement, old symlink layouts and in-place
edits, without installing a shell hook or changing the user's theme.
"""
from pathlib import Path
import os
import re
import tomllib
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from . import ui_scale as ui


def paths():
    return (Path.home()/'.local/state/omarchy/current/theme/colors.toml',
            Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'omarchy/current/theme/colors.toml')


def blend(a,b,amount):
    a,b=QColor(a),QColor(b)
    return QColor.fromRgbF(*(x+(y-x)*amount for x,y in zip(a.getRgbF()[:3],b.getRgbF()[:3]))).name()


def contrast(background):
    def luminance(value):
        channels=QColor(value).getRgbF()[:3]
        return sum(weight*(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4) for c,weight in zip(channels,(.2126,.7152,.0722)))
    l=luminance(background)
    return '#000000' if (l+.05)/.05 >= 1.05/(l+.05) else '#ffffff'


def tokens(data):
    valid={k:v for k,v in data.items() if isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}
    if not all(key in valid for key in ('background','foreground','accent')):
        raise ValueError('An Omarchy palette needs background, foreground and accent colors')
    bg,fg,accent=(valid[k] for k in ('background','foreground','accent'))
    return dict(background=bg,foreground=fg,accent=accent,on_accent=contrast(accent),
                surface=valid.get('lighter_background',blend(bg,fg,.07)),
                base=valid.get('dark_background',blend(bg,'#000000',.1)),
                border=blend(bg,fg,.3),muted=valid.get('dark_foreground',blend(bg,fg,.65)),
                hover=blend(bg,fg,.13),selection=valid.get('selection',blend(bg,accent,.3)),
                red=valid.get('red',accent),yellow=valid.get('yellow',accent))


def read_palette(candidates=None):
    for path in paths() if candidates is None else candidates:
        try:
            with Path(path).open('rb') as file:data=tomllib.load(file)
            return tokens(data)
        except (OSError,ValueError):continue
    return None


_current=read_palette()


def color(name):
    if _current:return QColor(_current[name])
    # Outside Omarchy, inherit Qt's palette rather than inventing a second theme.
    role={'background':'Window','foreground':'WindowText','accent':'Highlight','on_accent':'HighlightedText',
          'surface':'AlternateBase','base':'Base','border':'Mid','muted':'PlaceholderText',
          'hover':'Button','selection':'Highlight','red':'Highlight','yellow':'Highlight'}[name]
    return QApplication.palette().color(getattr(QPalette.ColorRole,role))


STYLE='''
QWidget { background:palette(window); color:palette(window-text); font-size:12px; }
QMainWindow,QDialog { background:palette(window); }
QToolBar { border:none; spacing:5px; padding:9px; background:palette(alternate-base); }
QToolButton,QPushButton { border:1px solid palette(mid); background:palette(button); border-radius:6px; padding:7px 11px; }
QToolButton:hover,QPushButton:hover { background:palette(light); border-color:palette(highlight); }
QToolButton:checked,QPushButton:checked { background:palette(highlight); color:palette(highlighted-text); border-color:palette(highlight); }
QPushButton#primary { background:palette(highlight); border:1px solid palette(highlight); color:palette(highlighted-text); font-weight:600; }
QPushButton:disabled,QToolButton:disabled { color:palette(placeholder-text); background:palette(alternate-base); }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox { padding:5px; border:1px solid palette(mid); border-radius:5px; background:palette(base); selection-background-color:palette(highlight); selection-color:palette(highlighted-text); }
QCheckBox::indicator,QRadioButton::indicator { width:14px; height:14px; }
QScrollBar:vertical { width:14px; }
QScrollBar:horizontal { height:14px; }
QListWidget { background:palette(base); border:1px solid palette(mid); border-radius:8px; }
QListWidget::item { padding:10px; border-bottom:1px solid palette(alternate-base); }
QListWidget::item:selected { background:palette(highlight); color:palette(highlighted-text); }
QMenu { padding:6px; border:1px solid palette(mid); }
QMenu::item { padding:7px 24px; }
QMenu::item:selected { background:palette(highlight); color:palette(highlighted-text); border-radius:4px; }
QStatusBar,QLabel#muted { color:palette(placeholder-text); }
QSlider::groove:horizontal { height:5px; background:palette(mid); }
QSlider::handle:horizontal { width:13px; margin:-5px 0; background:palette(highlight); border-radius:6px; }
QToolTip { background:palette(window); color:palette(window-text); border:1px solid palette(highlight); }
'''


class ThemeManager(QObject):
    changed=Signal()
    def __init__(self,app,candidates=None,appearance_candidates=None):
        super().__init__(app);self.app=app;self.candidates=candidates;self.applied=None
        self.appearance_candidates=appearance_candidates if appearance_candidates is not None else ([Path(p).with_name('shell.toml') for p in candidates] if candidates is not None else None)
        self.reload()
        app.setStyleSheet(ui.stylesheet(STYLE))
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.reload);self.timer.start()

    def reload(self):
        global _current
        appearance=ui.read(self.appearance_candidates)
        resized=ui.apply(self.app,appearance) if appearance is not None else False
        ui.fit_windows()
        current=read_palette(self.candidates)
        # Keep the last valid palette if a theme is being generated or edited.
        if current is None or current==self.applied:
            if resized:
                self.app.setStyleSheet(ui.stylesheet(STYLE));self.changed.emit()
            return resized
        _current=current;self.applied=current
        palette=QPalette(self.app.palette())
        mapping={'Window':'background','WindowText':'foreground','Base':'base','Text':'foreground',
                 'AlternateBase':'surface','Button':'surface','ButtonText':'foreground',
                 'Highlight':'accent','HighlightedText':'on_accent','PlaceholderText':'muted',
                 'Mid':'border','Light':'hover','Dark':'border','Shadow':'border','Midlight':'surface',
                 'ToolTipBase':'background','ToolTipText':'foreground','Link':'accent','LinkVisited':'accent','Accent':'accent'}
        for role,key in mapping.items():palette.setColor(getattr(QPalette.ColorRole,role),QColor(current[key]))
        for role in ('WindowText','Text','ButtonText'):
            palette.setColor(QPalette.ColorGroup.Disabled,getattr(QPalette.ColorRole,role),QColor(current['muted']))
        self.app.setPalette(palette)
        # Re-polish stylesheet surfaces and repaint custom-drawn controls.
        self.app.setStyleSheet(ui.stylesheet(STYLE))
        for widget in self.app.allWidgets():widget.update()
        self.changed.emit();return True
