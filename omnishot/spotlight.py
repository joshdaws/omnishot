"""Editable spotlight aperture and dimming controls."""
from . import ui_scale as ui
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QWidget,QHBoxLayout,QSlider,QSpinBox,QLabel
from .controls import Choice

DEFAULTS=dict(spotlight_shape='Rounded rectangle',spotlight_radius=8,spotlight_alpha=155)

def aperture(rect,props):
    path=QPainterPath();shape=props.get('spotlight_shape','Rounded rectangle')
    if shape=='Ellipse':path.addEllipse(rect)
    elif shape=='Rectangle':path.addRect(rect)
    else:
        radius=max(0,props.get('spotlight_radius',8));path.addRoundedRect(rect,radius,radius)
    return path


class SpotlightControls(QWidget):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.drag_changed=False
        row=QHBoxLayout(self);ui.set(row,"setContentsMargins",0,0,0,0);ui.set(row,"setSpacing",4)
        self.shape=Choice();self.shape.addItems(['Rounded rectangle','Rectangle','Ellipse']);ui.set(self.shape,"setMaximumWidth",150);self.shape.setToolTip('Spotlight shape');self.shape.setAccessibleName('Spotlight shape')
        self.radius=QSpinBox();self.radius.setRange(0,500);self.radius.setValue(8);self.radius.setSuffix(' px');ui.set(self.radius,"setFixedWidth",72);self.radius.setToolTip('Spotlight corner radius');self.radius.setAccessibleName('Spotlight corner radius')
        self.opacity=QSlider(Qt.Orientation.Horizontal);self.opacity.setRange(0,255);self.opacity.setValue(155);ui.set(self.opacity,"setFixedWidth",90);self.opacity.setAccessibleName('Spotlight dimming')
        self.percent=QLabel();ui.set(self.percent,"setFixedWidth",35)
        for widget in (self.shape,self.radius,self.opacity,self.percent):row.addWidget(widget)
        self.refresh()
        self.shape.currentTextChanged.connect(self.apply);self.radius.valueChanged.connect(self.apply);self.opacity.valueChanged.connect(self.apply)
        self.opacity.sliderPressed.connect(lambda:setattr(self,'drag_changed',False));self.opacity.sliderReleased.connect(self.finish_drag)

    def values(self):return dict(spotlight_shape=self.shape.currentText(),spotlight_radius=self.radius.value(),spotlight_alpha=self.opacity.value())

    def refresh(self):
        self.radius.setEnabled(self.shape.currentText()=='Rounded rectangle')
        text=f'{round(self.opacity.value()/255*100)}%';self.percent.setText(text);self.opacity.setToolTip('Spotlight dimming: '+text)

    def load(self,props):
        for widget,value in ((self.shape,props.get('spotlight_shape','Rounded rectangle')),(self.radius,props.get('spotlight_radius',8)),(self.opacity,props.get('spotlight_alpha',155))):
            widget.blockSignals(True)
            if widget is self.shape:widget.setCurrentText(value)
            else:widget.setValue(round(value))
            widget.blockSignals(False)
        self.refresh()

    def apply(self,*args):
        self.refresh();changed=False
        for obj in self.editor.scene.selectedItems():
            if getattr(obj,'props',{}).get('kind')!='spotlight':continue
            values=self.values()
            if any(obj.props.get(key,DEFAULTS[key])!=value for key,value in values.items()):
                obj.props.update(values);obj.update();changed=True
        if changed:
            if self.opacity.isSliderDown():self.drag_changed=True
            else:self.editor.commit()

    def finish_drag(self):
        if self.drag_changed:self.drag_changed=False;self.editor.commit()
