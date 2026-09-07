"""Cancelable screenshot countdown while the source application keeps focus."""
from . import ui_scale as ui
import math,time
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QPushButton
from .overlay_keys import OverlayKeys


class CountdownKeys(OverlayKeys):
    actions={'ESCAPE':'cancel'}
    namespace='countdown'
    require_hover=False
    description='OmniShot screenshot countdown'


class CaptureCountdown(QWidget):
    cancelled=Signal()
    finished=Signal()
    def __init__(self,seconds):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.setWindowTitle('OmniShot Self Timer')
        self.terminal=False;self.deadline=time.monotonic()+max(0,min(86400,float(seconds)))
        row=QHBoxLayout(self);ui.set(row,"setContentsMargins",18,14,18,14);self.label=QLabel();row.addWidget(self.label)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.clicked.connect(self.close);row.addWidget(self.cancel_button)
        self.keys=CountdownKeys(self);self.keys.activated.connect(lambda _:self.close())
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.tick);self.label.setText(f'Capturing in {math.ceil(max(0,self.deadline-time.monotonic()))}…')
    def showEvent(self,event):
        super().showEvent(event);self.timer.start();QTimer.singleShot(120,self.keys.start)
    def tick(self):
        remaining=self.deadline-time.monotonic();self.label.setText(f'Capturing in {math.ceil(max(0,remaining))}…')
        if remaining<=0:self.terminal=True;self.close();self.finished.emit()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.close()
        else:super().keyPressEvent(event)
    def closeEvent(self,event):
        self.timer.stop();self.keys.stop()
        if not self.terminal:self.terminal=True;self.cancelled.emit()
        super().closeEvent(event)
