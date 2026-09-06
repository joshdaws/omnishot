"""Native annotation color panel with explicit, persistent favorite swatches."""
from .theme import color as theme_color
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QEvent
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient,QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,QSpinBox,QSlider,QPushButton,QToolButton,QMenu,QScrollArea

SWATCHES=['#15171d','#ff5b61','#ff8a34','#ffbc42','#53d49b','#26c6be','#60a5fa','#b48bfa','#ef4b9b','#ffffff']


def sample_screen():
    import subprocess
    result=subprocess.run(['hyprpicker','-f','hex','-b'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    if result.returncode==2:return b''  # The picker uses status 2 for Escape.
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace').strip() or 'The screen color picker failed')
    return result.stdout


def color_text(color):
    return color.name(QColor.NameFormat.HexRgb if color.alpha()==255 else QColor.NameFormat.HexArgb)


def favorite_colors(settings):
    from .backend import DEFAULTS
    values=settings.get('custom_colors',[c for c in settings.get('palette',[]) if c not in DEFAULTS['palette']])
    return list(dict.fromkeys(color_text(QColor(c)) for c in values if isinstance(c,str) and QColor(c).isValid()))


class ColorField(QWidget):
    changed=Signal(float,float)
    def __init__(self):
        super().__init__();self.hue=0.;self.saturation=1.;self.value=1.;self.setFixedSize(208,154)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setAccessibleName('Saturation and brightness');self.setCursor(Qt.CursorShape.CrossCursor)
    def paintEvent(self,event):
        p=QPainter(self);r=QRectF(self.rect());gradient=QLinearGradient(0,0,self.width(),0);gradient.setColorAt(0,QColor('white'));gradient.setColorAt(1,QColor.fromHsvF(self.hue,1,1));p.fillRect(r,gradient)
        shade=QLinearGradient(0,0,0,self.height());shade.setColorAt(0,QColor(0,0,0,0));shade.setColorAt(1,QColor('black'));p.fillRect(r,shade)
        p.setRenderHint(QPainter.RenderHint.Antialiasing);point=QPointF(self.saturation*(self.width()-1),(1-self.value)*(self.height()-1))
        p.setPen(QPen(QColor(0,0,0,150),3));p.drawEllipse(point,4,4);p.setPen(QPen(QColor('white'),1.5));p.drawEllipse(point,4,4)
    def choose(self,point):
        self.saturation=max(0,min(1,point.x()/max(1,self.width()-1)));self.value=1-max(0,min(1,point.y()/max(1,self.height()-1)));self.update();self.changed.emit(self.saturation,self.value)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.setFocus();self.choose(event.position())
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.MouseButton.LeftButton:self.choose(event.position())
    def keyPressEvent(self,event):
        step=.1 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else .01
        dx,dy={Qt.Key.Key_Left:(-step,0),Qt.Key.Key_Right:(step,0),Qt.Key.Key_Up:(0,step),Qt.Key.Key_Down:(0,-step)}.get(event.key(),(0,0))
        if dx or dy:
            self.saturation=max(0,min(1,self.saturation+dx));self.value=max(0,min(1,self.value+dy));self.update();self.changed.emit(self.saturation,self.value)
        else:super().keyPressEvent(event)


class ColorSwatch(QToolButton):
    def __init__(self,color):
        super().__init__();self.color=QColor(color);self.setFixedSize(24,24);self.setToolTip(color_text(self.color));self.setAccessibleName(color_text(self.color))
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme_color('accent') if self.hasFocus() else theme_color('border'),1));p.setBrush(theme_color('muted'));p.drawEllipse(QRectF(4,4,16,16))
        p.setBrush(self.color);p.drawEllipse(QRectF(4,4,16,16))
        if self.isDown():p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('white'),1.5));p.drawEllipse(QRectF(1,1,22,22))


class ColorPicker(QWidget):
    changed=Signal(str)
    finished=Signal()
    screen_requested=Signal()
    def __init__(self,color,store,parent):
        super().__init__(parent,Qt.WindowType.Popup|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('OmniShot Annotation Color');self.store=store;self.color=QColor(color);self.hue=max(0,self.color.hsvHueF());self.closed=False
        self.setObjectName('annotationColorPicker');style='''
            QWidget#annotationColorPicker { background:palette(window); border:1px solid palette(mid); border-radius:12px; }
            QLabel { background:transparent; color:palette(placeholder-text); font-size:10px; }
            QLineEdit,QSpinBox { background:palette(base); border:1px solid palette(mid); border-radius:5px; padding:3px; font-size:11px; }
            QToolButton { padding:0; border:0; background:transparent; }
            QPushButton { font-size:11px; padding:6px; }
            QPushButton#primary:disabled { background:palette(mid); color:palette(placeholder-text); border:1px solid palette(mid); }
            QScrollArea { background:transparent; border:0; }
        '''
        self.setStyleSheet(style)
        outer=QHBoxLayout(self);outer.setContentsMargins(9,12,12,12);outer.setSpacing(10)
        swatches=QHBoxLayout();swatches.setSpacing(1);base=QVBoxLayout();base.setSpacing(1)
        self.base_buttons=[]
        for value in SWATCHES:
            b=ColorSwatch(value);b.clicked.connect(lambda checked=False,c=value:self.set_color(QColor(c)));base.addWidget(b);self.base_buttons.append(b)
        base.addStretch();swatches.addLayout(base)
        self.favorites=QWidget();self.favorites.setStyleSheet('background:transparent');self.favorites_layout=QVBoxLayout(self.favorites);self.favorites_layout.setContentsMargins(0,0,0,0);self.favorites_layout.setSpacing(1)
        scroll=QScrollArea();scroll.setWidget(self.favorites);scroll.setWidgetResizable(True);scroll.setFixedWidth(37);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        swatches.addWidget(scroll);outer.addLayout(swatches)
        right=QVBoxLayout();right.setSpacing(7);outer.addLayout(right);self.field=ColorField();right.addWidget(self.field)
        self.hue_slider=QSlider(Qt.Orientation.Horizontal);self.hue_slider.setRange(0,359);self.hue_slider.setAccessibleName('Hue');self.hue_slider.setToolTip('Hue')
        self.hue_slider.setStyleSheet('QSlider::groove:horizontal { height:8px; border-radius:4px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 red,stop:.167 yellow,stop:.333 lime,stop:.5 cyan,stop:.667 blue,stop:.833 magenta,stop:1 red); }')
        right.addWidget(self.hue_slider)
        self.alpha_slider=QSlider(Qt.Orientation.Horizontal);self.alpha_slider.setRange(0,100);self.alpha_slider.setAccessibleName('Opacity');self.alpha_slider.setToolTip('Opacity');right.addWidget(self.alpha_slider)
        row=QHBoxLayout();self.preview=ColorSwatch(color);self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus);self.preview.setAccessibleName('Current color');row.addWidget(self.preview);self.hex=QLineEdit();self.hex.setAccessibleName('Hex color');self.hex.setToolTip('Hexadecimal RGB color');self.hex.setMaxLength(7);self.hex.setValidator(QRegularExpressionValidator(QRegularExpression('#?[0-9a-fA-F]{6}'),self.hex));row.addWidget(self.hex)
        self.eyedropper=QToolButton();self.eyedropper.setText('⌖');self.eyedropper.setToolTip('Pick a color from the screen');self.eyedropper.setAccessibleName('Pick from screen');self.eyedropper.setFixedSize(28,25);row.addWidget(self.eyedropper);right.addLayout(row)
        values=QGridLayout();values.setSpacing(4);self.channels=[]
        for index,label in enumerate(('R','G','B','Alpha')):
            spin=QSpinBox();spin.setRange(0,100 if index==3 else 255);spin.setKeyboardTracking(False);spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons);spin.setFixedWidth(48);spin.setAccessibleName(label);spin.setToolTip('Opacity percent' if index==3 else label)
            values.addWidget(spin,0,index);caption=QLabel(label);caption.setAlignment(Qt.AlignmentFlag.AlignCenter);values.addWidget(caption,1,index);self.channels.append(spin)
        right.addLayout(values);self.save_button=QPushButton('+ Add to My Colors');self.save_button.setObjectName('primary');right.addWidget(self.save_button)
        self.message=QLabel();self.message.setWordWrap(True);self.message.setMaximumWidth(208);right.addWidget(self.message);right.addStretch()
        self.field.changed.connect(self.field_changed);self.hue_slider.valueChanged.connect(self.hue_changed);self.alpha_slider.valueChanged.connect(self.alpha_changed)
        for spin in self.channels:spin.valueChanged.connect(self.channels_changed)
        self.hex.editingFinished.connect(self.hex_changed);self.save_button.clicked.connect(self.add_favorite);self.eyedropper.clicked.connect(self.pick_screen)
        self.refresh_favorites();self.sync();self.adjustSize()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.PaletteChange and hasattr(self,"save_button"):self.sync()

    def sync(self):
        color=self.color;h=color.hsvHueF()
        if h>=0:self.hue=h
        self.field.hue=self.hue;self.field.saturation=color.hsvSaturationF();self.field.value=color.valueF();self.field.update()
        for widget,value in [(self.hue_slider,min(359,round(self.hue*360))),(self.alpha_slider,round(color.alphaF()*100)),*zip(self.channels,[color.red(),color.green(),color.blue(),round(color.alphaF()*100)])]:
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        self.preview.color=QColor(color);self.preview.setToolTip(color_text(color));self.preview.update()
        self.hex.setText(color.name()[1:].upper())
        self.alpha_slider.setStyleSheet(f'QSlider::groove:horizontal {{ height:8px; border-radius:4px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {theme_color("border").name()},stop:1 {color.name()}); }}')
        self.save_button.setEnabled(color_text(color) not in favorite_colors(self.store.settings))
    def set_color(self,color):
        if not color.isValid():return
        changed=color!=self.color;self.color=QColor(color);self.sync()
        if changed:self.changed.emit(color_text(self.color))
    def field_changed(self,saturation,value):self.set_color(QColor.fromHsvF(self.hue,saturation,value,self.color.alphaF()))
    def hue_changed(self,value):
        self.hue=value/360;self.set_color(QColor.fromHsvF(self.hue,self.color.hsvSaturationF(),self.color.valueF(),self.color.alphaF()))
    def alpha_changed(self,value):
        color=QColor(self.color);color.setAlphaF(value/100);self.set_color(color)
    def channels_changed(self):self.set_color(QColor(self.channels[0].value(),self.channels[1].value(),self.channels[2].value(),round(self.channels[3].value()*255/100)))
    def hex_changed(self):
        if self.hex.hasAcceptableInput():
            color=QColor('#'+self.hex.text().lstrip('#'));color.setAlpha(self.color.alpha());self.set_color(color)
        else:self.hex.setText(self.color.name()[1:].upper())
    def persist(self,values):
        old=self.store.settings.get('custom_colors');self.store.settings['custom_colors']=values
        try:self.store.save_settings()
        except Exception as exc:
            if old is None:self.store.settings.pop('custom_colors',None)
            else:self.store.settings['custom_colors']=old
            self.message.setText(f'Could not save colors: {exc}');return
        self.message.clear();self.refresh_favorites();self.sync()
    def add_favorite(self):
        values=favorite_colors(self.store.settings);value=color_text(self.color)
        if value not in values:self.persist(values+[value])
    def refresh_favorites(self):
        while self.favorites_layout.count():
            item=self.favorites_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.favorite_buttons=[]
        for value in favorite_colors(self.store.settings):
            b=ColorSwatch(value);b.clicked.connect(lambda checked=False,c=value:self.set_color(QColor(c)));b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda point,c=value,button=b:self.favorite_menu(button,point,c));self.favorites_layout.addWidget(b);self.favorite_buttons.append(b)
        for _ in range(max(0,10-len(self.favorite_buttons))):
            empty=QLabel('◌');empty.setAlignment(Qt.AlignmentFlag.AlignCenter);empty.setFixedSize(24,24);empty.setStyleSheet('color:palette(mid);');self.favorites_layout.addWidget(empty)
        self.favorites_layout.addStretch()
    def favorite_menu(self,button,point,value):
        menu=QMenu(self);menu.addAction('Remove from My Colors',lambda:self.persist([c for c in favorite_colors(self.store.settings) if c!=value]));menu.exec(button.mapToGlobal(point))
    def pick_screen(self):self.close();self.screen_requested.emit()
    def closeEvent(self,event):
        if not self.closed:self.closed=True;self.finished.emit()
        super().closeEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.close()
        else:super().keyPressEvent(event)
