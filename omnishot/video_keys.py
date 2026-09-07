"""Keystroke inspector controls and source-event presentation rules."""
from . import ui_scale as ui
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QSlider,QLabel,QRadioButton,QButtonGroup


class KeySize(QWidget):
    valueChanged=Signal(int)
    def __init__(self,value=20,parent=None):
        super().__init__(parent);layout=QHBoxLayout(self);ui.set(layout,"setContentsMargins",0,0,0,0)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(10,72);self.slider.setAccessibleName('Keystroke size');self.label=QLabel();ui.set(self.label,"setMinimumWidth",38)
        layout.addWidget(self.slider);layout.addWidget(self.label);self.slider.valueChanged.connect(self.changed);self.setValue(value)
    def value(self):return self.slider.value()
    def setValue(self,value):self.slider.setValue(round(value));self.changed(self.value())
    def changed(self,value):self.label.setText(f'{value/20:g}×');self.slider.setAccessibleDescription(self.label.text());self.valueChanged.emit(value)


class KeyMode(QWidget):
    toggled=Signal(bool)
    def __init__(self,commands=False,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self);ui.set(layout,"setContentsMargins",0,0,0,0);self.group=QButtonGroup(self)
        self.commands=QRadioButton('Show only command keys');self.all=QRadioButton('Show all keys')
        for button in (self.commands,self.all):self.group.addButton(button);layout.addWidget(button)
        self.commands.toggled.connect(self.toggled);self.setChecked(commands)
    def isChecked(self):return self.commands.isChecked()
    def setChecked(self,value):(self.commands if value else self.all).setChecked(True)


def command_event(event):
    """Old recordings have labels only; new metadata can retain classification."""
    if isinstance(event.get('command'),bool):return event['command']
    return any(part in ('Ctrl','Alt','Super','Cmd','Meta') for part in event.get('label','').split('+')[:-1])


def visible_keys(events,t,options,metadata):
    commands=options.get('key_commands_only',metadata.get('capture_options',{}).get('commands_only',False))
    return [e.get('label','') for e in events if e.get('kind')=='key' and e.get('state')==1 and 0<=t-e['t']<options.get('key_duration',1.3) and e.get('label') and not e.get('hidden') and (not commands or command_event(e))]


def key_colors(options):
    style=options.get('key_style','Custom' if 'key_color' in options or 'key_background' in options else 'Dark')
    if style=='Light':return '#e8ffffff','#202124'
    if style=='Dark':return '#d7141720','#ffffff'
    return options.get('key_background','#d7141720'),options.get('key_color','#ffffff')
