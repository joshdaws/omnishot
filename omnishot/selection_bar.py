"""All-In-One mode buttons and exact dimensions, drawn with native Qt controls."""
from . import ui_scale as ui
from .theme import color as theme_color
from PySide6.QtCore import Qt,QSize,QRectF,QPointF,QEvent
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor,QFont
from PySide6.QtWidgets import QWidget,QHBoxLayout,QBoxLayout,QToolButton,QLabel,QMenu

MODES=[('Area','Screenshot'),('Fullscreen','Fullscreen'),('Window','Window'),
       ('Scrolling','Scrolling'),('Timer','Self timer'),('OCR','Text (OCR)'),('Recording','Record video')]


def mode_icon(name,selected=False):
    pixmap=QPixmap(48,48);pixmap.fill(Qt.GlobalColor.transparent);pixmap.setDevicePixelRatio(2)
    p=QPainter(pixmap);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(theme_color('on_accent' if selected else 'foreground'),1.7));p.setBrush(Qt.BrushStyle.NoBrush)
    if name=='Area':
        for x,y,dx,dy in [(3,3,1,1),(21,3,-1,1),(3,21,1,-1),(21,21,-1,-1)]:
            p.drawLine(x,y,x+5*dx,y);p.drawLine(x,y,x,y+5*dy)
    elif name in ('Fullscreen','Window'):
        p.drawRoundedRect(QRectF(2.5,4,19,14),2,2)
        if name=='Fullscreen':p.drawLine(12,18,12,22);p.drawLine(8,22,16,22)
        else:
            for x in (6,9,12):p.drawPoint(x,7)
    elif name=='Scrolling':
        p.drawLine(12,3,12,20);p.drawLine(7,15,12,20);p.drawLine(17,15,12,20)
    elif name=='Timer':
        p.drawEllipse(QRectF(3,4,18,18));p.drawLine(12,7,12,13);p.drawLine(12,13,8,10);p.drawLine(10,1,14,1)
    elif name=='OCR':p.setFont(QFont('Inter',13));p.drawText(QRectF(0,0,24,24),Qt.AlignmentFlag.AlignCenter,'Aa')
    else:
        p.drawRoundedRect(QRectF(2,6,14,13),2,2);p.drawLine(16,10,22,6);p.drawLine(22,6,22,19);p.drawLine(22,19,16,15)
    p.end();return QIcon(pixmap)


class SelectionBar(QWidget):
    def __init__(self,selector):
        super().__init__(selector);self.selector=selector;self.buttons={}
        self.setObjectName('selectionBar')
        ui.set(self,"setStyleSheet",'''
            QWidget#selectionBar { background:transparent; }
            QWidget#selectionGroup { background:palette(window); border:1px solid palette(mid); border-radius:16px; }
            QToolButton { border:0; border-radius:10px; background:transparent; color:palette(window-text); padding:7px 4px; font-size:12px; }
            QToolButton:hover { background:palette(light); color:palette(window-text); }
            QToolButton:checked { background:palette(highlight); color:palette(highlighted-text); }
            QSpinBox { background:palette(base); border:0; border-radius:7px; padding:5px; color:palette(text); }
            QLabel { background:transparent; color:palette(placeholder-text); }
            QComboBox { background:palette(window); border:0; padding:5px; color:palette(text); }
        ''')
        self.layout=QBoxLayout(QBoxLayout.Direction.LeftToRight,self);ui.set(self.layout,"setContentsMargins",0,0,0,0);ui.set(self.layout,"setSpacing",12)
        modes=QWidget();modes.setObjectName('selectionGroup');row=QHBoxLayout(modes);ui.set(row,"setContentsMargins",8,5,8,5);ui.set(row,"setSpacing",2)
        for label,kind in MODES:
            b=QToolButton();b.setText(label);b.setIcon(mode_icon(label));ui.set(b,"setIconSize",QSize(24,24));b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            ui.set(b,"setFixedSize",76,62);b.setCheckable(True);b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip('Choose a window, then click to capture' if kind=='Window' else ('Capture this display' if kind=='Fullscreen' else f'{label} · use the selected area'))
            b.clicked.connect(lambda checked=False,k=kind:selector.choose_mode(k));row.addWidget(b);self.buttons[kind]=b
        scroll=self.buttons['Scrolling'];scroll.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def scroll_menu(point):
            menu=QMenu(scroll)
            menu.addAction('Vertical scrolling',lambda:selector.choose_mode('Scrolling'))
            menu.addAction('Horizontal scrolling',lambda:selector.choose_mode('Horizontal scrolling'))
            menu.exec(scroll.mapToGlobal(point))
        scroll.customContextMenuRequested.connect(scroll_menu);scroll.setToolTip('Scrolling capture · right-click for horizontal scrolling')
        dimensions=QWidget();dimensions.setObjectName('selectionGroup');fields=QHBoxLayout(dimensions);ui.set(fields,"setContentsMargins",14,14,14,14);ui.set(fields,"setSpacing",7)
        ui.set(selector.width_box,"setFixedWidth",77);ui.set(selector.height_box,"setFixedWidth",77)
        selector.width_box.setToolTip('Width in screen points');selector.height_box.setToolTip('Height in screen points')
        fields.addWidget(selector.width_box);fields.addWidget(QLabel('×'));fields.addWidget(selector.height_box);fields.addWidget(selector.aspect)
        selector.aspect.setToolTip('Lock selection aspect ratio');ui.set(selector.aspect,"setFixedWidth",78)
        self.layout.addWidget(modes);self.layout.addWidget(dimensions)
        selector.capture_mode.currentTextChanged.connect(self.update_mode);self.update_mode(selector.capture_mode.currentText())
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.PaletteChange:
            for label,kind in MODES:
                if kind in getattr(self,'buttons',{}):self.buttons[kind].setIcon(mode_icon(label,self.buttons[kind].isChecked()))

    def update_mode(self,kind):
        for label,key in MODES:
            button=self.buttons[key];button.setChecked(key==kind or key=='Scrolling' and kind=='Horizontal scrolling');button.setIcon(mode_icon(label,button.isChecked()))
    def fit(self,width):
        self.layout.setDirection(QBoxLayout.Direction.TopToBottom if width<ui.px(900) else QBoxLayout.Direction.LeftToRight)
        self.adjustSize()
