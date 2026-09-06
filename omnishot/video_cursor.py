"""Visual cursor inspector controls with stable source-pixel edit values."""
from PySide6.QtCore import Qt,Signal,QSize,QRectF,QPointF
from PySide6.QtGui import QIcon,QIconEngine,QPixmap,QPainter
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QSlider,QLabel,QPushButton,QToolButton,QButtonGroup
from .cursor_shape import paint_cursor


class CursorSize(QWidget):
    valueChanged=Signal(int)
    def __init__(self,value=28,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();row.addWidget(QLabel('Size'));row.addStretch();self.label=QLabel();row.addWidget(self.label);layout.addLayout(row)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(10,100);self.slider.setAccessibleName('Cursor size');layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self.changed);self.setValue(value)
    def value(self):return self.slider.value()
    def setValue(self,value):self.slider.setValue(round(value));self.sync_label()
    def sync_label(self):
        self.label.setText(f'{self.value()/28:.2g}×');self.slider.setAccessibleDescription(self.label.text())
        self.slider.setToolTip(f'{self.label.text()} · {self.value()} source pixels')
    def changed(self,value):self.sync_label();self.valueChanged.emit(value)


class CursorMotion(QWidget):
    toggled=Signal(bool)
    def __init__(self,smooth=True,parent=None):
        super().__init__(parent);layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.group=QButtonGroup(self);self.buttons={}
        for name,value in [('Natural',False),('Smooth',True)]:
            button=QPushButton(name);button.setCheckable(True);button.setAccessibleName(name+' cursor motion')
            button.setToolTip('Use the recorded cursor positions' if not value else 'Smooth the recorded cursor movement')
            self.group.addButton(button,int(value));self.buttons[name]=button;layout.addWidget(button)
        self.setChecked(smooth);self.group.idClicked.connect(lambda value:self.toggled.emit(bool(value)))
    def isChecked(self):return self.buttons['Smooth'].isChecked()
    def setChecked(self,value):
        changed=self.isChecked()!=bool(value);self.buttons['Smooth' if value else 'Natural'].setChecked(True)
        if changed:self.toggled.emit(bool(value))


class CursorIcon(QIconEngine):
    def __init__(self,style,fill,outline):super().__init__();self.style=style;self.fill=fill;self.outline=outline
    def clone(self):return CursorIcon(self.style,self.fill,self.outline)
    def pixmap(self,size,mode,state):
        image=QPixmap(size);image.fill(Qt.GlobalColor.transparent);p=QPainter(image);self.paint(p,QRectF(image.rect()),mode,state);p.end();return image
    def paint(self,p,r,mode,state):
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing);p.translate(r.x(),r.y());p.scale(r.width()/32,r.height()/32)
        if mode==QIcon.Mode.Disabled:p.setOpacity(.45)
        paint_cursor(p,QPointF(16,16) if self.style in ('Dot','Crosshair') else QPointF(7,4),22,self.style,self.fill,self.outline);p.restore()


class CursorStyle(QWidget):
    currentTextChanged=Signal(str)
    def __init__(self,value='Arrow',parent=None,compact=False):
        super().__init__(parent);self.compact=compact;self.group=QButtonGroup(self);self.buttons={};self.selected='';self.fill='#161821';self.outline='#ffffff'
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(6)
        self.setStyleSheet('QToolButton { border:2px solid transparent; border-radius:10px; padding:5px; background:palette(button); } QToolButton:hover { background:palette(light); } QToolButton:checked { border-color:palette(highlight); }')
        for name in ('Arrow','Rounded Arrow','Dot','Crosshair'):
            button=QToolButton();button.setCheckable(True);button.setFixedSize(48,48);button.setIconSize(QSize(32,32));button.setAccessibleName(name+' cursor');button.setToolTip(name)
            self.group.addButton(button);self.buttons[name]=button;row.addWidget(button);button.clicked.connect(lambda checked=False,n=name:self.setCurrentText(n))
        row.addStretch();self.set_colors(self.fill,self.outline);self.setCurrentText(value)
    def currentText(self):return self.selected
    def setCurrentText(self,value):
        if value not in self.buttons:return
        changed=self.selected!=value;self.selected=value;self.buttons[value].setChecked(True)
        # Keep legacy Crosshair projects visibly selected, while the normal
        # inspector presents the three styles in the reference workflow.
        self.buttons['Crosshair'].setVisible(not self.compact or value=='Crosshair')
        if changed:self.currentTextChanged.emit(value)
    def set_colors(self,fill,outline):
        self.fill=fill;self.outline=outline
        for name,button in self.buttons.items():button.setIcon(QIcon(CursorIcon(name,fill,outline)))
