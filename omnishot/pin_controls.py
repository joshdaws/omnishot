"""Hover controls that preserve the pinned image's content and input bounds."""
from PySide6.QtCore import Qt,QSize,QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QLabel
from .editor_toolbar import DragHandle,icon


class PinControls:
    def __init__(self,pin):
        self.pin=pin;self.hovered=False;self.position_timer=QTimer(pin);self.position_timer.setSingleShot(True);self.position_timer.timeout.connect(self.position_unlock)
        self.close=QPushButton('×',pin);self.close.setAccessibleName('Close pinned screenshot');self.close.setToolTip('Close pinned screenshot');self.close.clicked.connect(pin.close)
        self.lock=QPushButton(pin);self.lock.setIconSize(QSize(15,15));self.lock.clicked.connect(lambda:pin.set_clickthrough(not pin.locked))
        # Hyprland's no_focus excludes a whole top-level from hit testing, even
        # its interactive input region. A tiny sibling keeps unlocking clickable.
        self.unlock=QPushButton(pin);self.unlock.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.unlock.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.unlock.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.unlock.setWindowTitle(pin.normal_title.replace('OmniShot Pin','OmniShot Pin Unlock'))
        self.unlock.setIcon(icon('lock'));self.unlock.setIconSize(QSize(15,15));self.unlock.setAccessibleName('Unlock pinned screenshot');self.unlock.setToolTip('Unlock pinned screenshot')
        self.unlock.clicked.connect(lambda:QTimer.singleShot(0,pin.unlock));self.unlock.hide()
        self.scale=QLabel(pin);self.scale.setAlignment(Qt.AlignmentFlag.AlignCenter);self.scale.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.scale.setStyleSheet('QLabel { background:palette(window); color:palette(window-text); border-radius:8px; padding:2px 5px; font-size:10px; }')
        self.drag=DragHandle(pin);self.drag.setParent(pin);self.drag.setText('⋮ ▱ ⋮');self.drag.setFixedSize(52,22)
        self.drag.setToolTip('Drag Me — drag this image into another app. Hold Alt to keep it pinned.')
        self.drag.setStyleSheet('QPushButton { background:palette(window); color:palette(window-text); border:1px solid palette(mid); border-radius:6px; padding:0; } QPushButton:hover { background:palette(light); }')
        for button in (self.close,self.lock,self.unlock):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setStyleSheet('QPushButton { background:palette(window); color:palette(window-text); border:0; border-radius:10px; padding:0; } QPushButton:hover { background:palette(light); }')
        self.layout();self.sync()

    def layout(self):
        p=self.pin;small=min(p.width(),p.height());margin=6 if small>=60 else 2;size=max(8,min(22,(small-4)//2))
        self.close.setGeometry(margin,margin,size,size);self.lock.setGeometry(p.width()-margin-size,margin,size,size)
        self.unlock.setFixedSize(size,size)
        self.scale.setText(f'{p.width()/p.image.width()*100:.0f}%');self.scale.adjustSize();self.scale.move((p.width()-self.scale.width())//2,margin)
        self.drag.move((p.width()-self.drag.width())//2,p.height()-margin-self.drag.height())
        self.sync()

    def sync(self):
        p=self.pin;normal=self.hovered and not p.locked and not getattr(p,'dragging',False)
        self.close.setVisible(normal and p.width()>=50);self.scale.setVisible(normal and p.width()>=120)
        self.drag.setVisible(normal and p.width()>=64 and p.height()>=58)
        self.lock.setVisible(normal)
        if p.locked and p.isVisible():
            if not self.unlock.isVisible():self.schedule_position()
        else:self.unlock.hide()
        self.lock.setIcon(icon('unlock'));self.lock.setAccessibleName('Lock pinned screenshot');self.lock.setToolTip('Lock Mode — interact with apps underneath')
        for widget in (self.close,self.scale,self.drag,self.lock):widget.raise_()

    def position_unlock(self):
        if not self.pin.locked or not self.pin.isVisible():return
        from .widgets import place_window
        from . import backend
        import os
        try:
            client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==self.pin.windowTitle());x,y=client['at']
        except (RuntimeError,StopIteration):
            if QApplication.platformName()=='wayland':self.schedule_position();return
            x,y=self.pin.x(),self.pin.y()
        self.unlock.show()
        place_window(self.unlock,x+self.lock.x(),y+self.lock.y())

    def schedule_position(self):
        if self.pin.locked and self.pin.isVisible():self.position_timer.start(160)
