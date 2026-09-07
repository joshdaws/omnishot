"""Zoom animation selection and continuous joins between adjacent zooms."""
from . import ui_scale as ui
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QHBoxLayout,QToolButton,QButtonGroup


class AnimationChoice(QWidget):
    currentTextChanged=Signal(str)
    def __init__(self):
        super().__init__();self.buttons={};box=QHBoxLayout(self);ui.set(box,"setContentsMargins",0,0,0,0);ui.set(box,"setSpacing",6)
        self.group=QButtonGroup(self)
        for label in ('Smooth','Dynamic'):
            control=QToolButton();control.setText(label);control.setCheckable(True);ui.set(control,"setMinimumHeight",32);box.addWidget(control,1);self.group.addButton(control);self.buttons[label]=control
            control.clicked.connect(lambda checked=False,value=label:self.currentTextChanged.emit(value))
        self.buttons['Smooth'].setChecked(True)
    def currentText(self):return next(label for label,button in self.buttons.items() if button.isChecked())
    def setCurrentText(self,value):
        if value in self.buttons and value!=self.currentText():self.buttons[value].setChecked(True);self.currentTextChanged.emit(value)


def zoom_at(zooms,t,cursor=None,animation='Smooth'):
    active=next((z for z in zooms if z['start']<=t<z['end']),None)
    if active is None:return 1,.5,.5
    a,b=active['start'],active['end'];ramp=min(.22 if animation=='Dynamic' else .35,(b-a)/2)
    def target(z):
        focus=cursor if z.get('follow') and cursor else z
        return z['scale'],focus.get('x',.5),focus.get('y',.5)
    def ease(value):
        value=max(0,min(1,value))
        return 1-(1-value)**3 if animation=='Dynamic' else value*value*(3-2*value)
    previous=next((z for z in zooms if z is not active and abs(z['end']-a)<1e-7),None)
    following=next((z for z in zooms if z is not active and abs(z['start']-b)<1e-7),None)
    result=target(active)
    if previous and t<a+ramp:
        before=target(previous);weight=ease((t-a)/ramp)
        return tuple(x+(y-x)*weight for x,y in zip(before,result))
    weight=1
    if previous is None:weight=min(weight,(t-a)/ramp)
    if following is None:weight=min(weight,(b-t)/ramp)
    return 1+(result[0]-1)*ease(weight),result[1],result[2]
