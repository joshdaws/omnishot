"""The selected zoom's inline level, tracking and manual framing controls."""
from . import ui_scale as ui
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import QWidget,QScrollArea,QLayout,QVBoxLayout,QHBoxLayout,QLabel,QSlider,QSpinBox,QToolButton,QButtonGroup
from .zoom_focus import ZoomFocus
from .widgets import button


class ZoomInspector(QScrollArea):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.timeline=editor.timeline;self.previous_page=0
        self.setWidgetResizable(True);self.setFrameShape(QScrollArea.Shape.NoFrame)
        from .timeline import SCROLLBAR_STYLE
        ui.set(self,"setStyleSheet",SCROLLBAR_STYLE)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page=QWidget();self.setWidget(page)
        box=QVBoxLayout(page);box.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize);ui.set(box,"setContentsMargins",14,8,14,12);ui.set(box,"setSpacing",12)
        heading=QHBoxLayout();heading.addWidget(QLabel('Zoom level'));self.level_value=QSpinBox();self.level_value.setRange(100,500);self.level_value.setSuffix('%');ui.set(self.level_value,"setFixedWidth",82);self.level_value.setAccessibleName('Zoom level percent');heading.addWidget(self.level_value);box.addLayout(heading)
        self.level=QSlider(Qt.Orientation.Horizontal);self.level.setRange(100,500);self.level.setAccessibleName('Zoom level');box.addWidget(self.level)
        self.apply_all=button('Apply Zoom Level to All',self.timeline.apply_zoom_level_to_all);box.addWidget(self.apply_all)
        box.addSpacing(12);box.addWidget(QLabel('Zoom mode'));row=QHBoxLayout();self.mode_group=QButtonGroup(self);self.modes={}
        for label,follow in [('Follow Cursor',True),('Manual',False)]:
            control=QToolButton();control.setText(label);control.setCheckable(True);ui.set(control,"setMinimumHeight",32);self.mode_group.addButton(control);self.modes[follow]=control;row.addWidget(control,1)
            control.clicked.connect(lambda checked=False,v=follow:self.timeline.change_zoom(follow=v))
        box.addLayout(row)
        self.focus=ZoomFocus();ui.set(self.focus,"setMinimumSize",0,140);ui.set(self.focus,"setFixedHeight",170);box.addWidget(self.focus)
        box.addSpacing(12);box.addWidget(QLabel('Animation'))
        self.animation=button('Animation Settings',lambda:editor.tool_buttons['Motion'].click());box.addWidget(self.animation);box.addStretch()
        self.level.valueChanged.connect(self.set_level);self.level_value.valueChanged.connect(self.set_level)
        self.focus.changed.connect(lambda scale,x,y:self.timeline.change_zoom(scale=scale,x=x,y=y))
        self.timeline.source_changed.connect(self.focus.set_image);self.timeline.selection_changed.connect(self.selected)
        self.timeline.edited.connect(self.sync)

    def set_level(self,value):
        zoom=self.timeline.selected_zoom()
        if zoom is not None and abs(zoom['scale']*100-value)>.01:self.timeline.change_zoom(scale=value/100)

    def sync(self):
        zoom=self.timeline.selected_zoom()
        if zoom is None:return
        for control in (self.level,self.level_value):
            with QSignalBlocker(control):control.setValue(round(zoom['scale']*100))
        follow=bool(zoom.get('follow',False));self.modes[follow].setChecked(True);self.focus.setVisible(not follow)
        self.focus.set_values(zoom['scale'],zoom.get('x',.5),zoom.get('y',.5));self.focus.set_image(self.timeline.source_image)

    def selected(self):
        e=self.editor
        if self.timeline.selected_zoom() is None:
            if e.inspector.currentWidget()==self:
                e.inspector.setCurrentIndex(self.previous_page)
                if self.previous_page<len(e.tool_buttons):list(e.tool_buttons.values())[self.previous_page].setChecked(True)
            return
        if e.inspector.currentWidget()!=self:self.previous_page=e.inspector.currentIndex()
        e.inspector.setCurrentWidget(self);e.tool_group.setExclusive(False)
        for control in e.tool_buttons.values():control.setChecked(False)
        e.tool_group.setExclusive(True);self.sync()
